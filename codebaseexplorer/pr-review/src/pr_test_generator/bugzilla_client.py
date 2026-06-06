"""Bugzilla REST API client for the PR Test Generator.

Supports resolving a Bugzilla bug URL to a Bitbucket PR link by:
1. Fetching bug details to verify the bug exists and is FIXED.
2. Fetching bug comments to extract the first Bitbucket PR link.

Bugzilla base URL: https://bugzilla.bizom.in
API key: read from BUGZILLA_API_KEY environment variable or Settings.
"""

from __future__ import annotations

import logging
import re
from typing import Any

import httpx

log = logging.getLogger("pr_test_generator.bugzilla_client")

# Base URL for the Bizom Bugzilla instance
BUGZILLA_BASE_URL = "https://bugzilla.bizom.in"

# Pattern to extract bug ID from a Bugzilla show_bug URL:
#   https://bugzilla.bizom.in/show_bug.cgi?id=153576
_BUGZILLA_URL_PATTERN = re.compile(
    r"^https://bugzilla\.bizom\.in/show_bug\.cgi\?id=(?P<bug_id>\d+)$"
)

# Pattern to find a Bitbucket PR URL anywhere inside comment text
_BITBUCKET_PR_PATTERN = re.compile(
    r"https://bitbucket\.org/[A-Za-z0-9_\-]+/[A-Za-z0-9_\-.]+/pull-requests/\d+"
)


class BugzillaError(Exception):
    """Raised when a Bugzilla API call fails."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        self.status_code = status_code
        super().__init__(message)


class BugNotFoundError(BugzillaError):
    """Raised when the bug ID does not exist in Bugzilla."""
    pass


class BugNotFixedError(BugzillaError):
    """Raised when the bug exists but its resolution is not FIXED."""

    def __init__(self, bug_id: int, status: str, resolution: str) -> None:
        self.bug_id = bug_id
        self.status = status
        self.resolution = resolution
        super().__init__(
            f"Bug {bug_id} is not fixed (status={status!r}, resolution={resolution!r}). "
            "Only FIXED bugs are processed."
        )


class PRLinkNotFoundError(BugzillaError):
    """Raised when no Bitbucket PR link is found in the bug's comments."""

    def __init__(self, bug_id: int) -> None:
        self.bug_id = bug_id
        super().__init__(
            f"No Bitbucket PR link found in any comment of bug {bug_id}."
        )


def parse_bugzilla_url(url: str) -> int | None:
    """Extract the bug ID from a Bugzilla show_bug URL.

    Args:
        url: Candidate URL string.

    Returns:
        Integer bug ID if the URL matches the Bugzilla pattern, else None.
    """
    match = _BUGZILLA_URL_PATTERN.match(url.strip())
    if match:
        return int(match.group("bug_id"))
    return None


class BugzillaClient:
    """Synchronous (via httpx) client for the Bugzilla REST API.

    Uses a single shared httpx.Client with a configurable timeout.
    The API key is appended as a query parameter on every request.
    """

    def __init__(self, api_key: str, timeout: float = 30.0) -> None:
        self._api_key = api_key
        self._http = httpx.Client(
            base_url=BUGZILLA_BASE_URL,
            timeout=timeout,
            follow_redirects=True,
        )

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._http.close()

    def __enter__(self) -> "BugzillaClient":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Issue a GET request, appending the API key automatically.

        Args:
            path: URL path relative to BUGZILLA_BASE_URL.
            params: Additional query parameters.

        Returns:
            Parsed JSON response body as a dict.

        Raises:
            BugzillaError: On any non-2xx HTTP response.
        """
        merged: dict[str, Any] = {"api_key": self._api_key}
        if params:
            merged.update(params)

        response = self._http.get(path, params=merged)

        if response.status_code == 404:
            raise BugNotFoundError(
                f"Bugzilla returned 404 for {path}",
                status_code=404,
            )

        if response.status_code >= 400:
            detail = (response.text or "")[:200].strip()
            raise BugzillaError(
                f"Bugzilla API error {response.status_code} for {path}: {detail}",
                status_code=response.status_code,
            )

        data = response.json()

        # Bugzilla returns {"error": true, "message": "..."} even on HTTP 200
        # for application-level errors (e.g., invalid API key, unknown bug).
        if data.get("error"):
            code = data.get("code")
            message = data.get("message", "Unknown Bugzilla error")
            if code == 101:  # Bug #NNN does not exist
                raise BugNotFoundError(message)
            raise BugzillaError(f"Bugzilla error (code={code}): {message}")

        return data

    def get_bug(self, bug_id: int) -> dict[str, Any]:
        """Fetch bug metadata: id, status, summary, resolution.

        Args:
            bug_id: Numeric Bugzilla bug ID.

        Returns:
            Dict with keys: id, status, summary, resolution.

        Raises:
            BugNotFoundError: If the bug does not exist.
            BugzillaError: On other API failures.
        """
        data = self._get(
            f"/rest/bug/{bug_id}",
            params={"include_fields": "id,status,summary,resolution"},
        )
        bugs = data.get("bugs", [])
        if not bugs:
            raise BugNotFoundError(f"Bug {bug_id} not found in Bugzilla response.")
        return bugs[0]

    def get_comments(self, bug_id: int) -> list[dict[str, Any]]:
        """Fetch all comments for a bug.

        Args:
            bug_id: Numeric Bugzilla bug ID.

        Returns:
            List of comment dicts, each with at least a 'text' key.

        Raises:
            BugNotFoundError: If the bug does not exist.
            BugzillaError: On other API failures.
        """
        data = self._get(f"/rest/bug/{bug_id}/comment")
        bugs_data = data.get("bugs", {})
        bug_comments = bugs_data.get(str(bug_id), {})
        return bug_comments.get("comments", [])

    def get_fix_description(self, bug_id: int) -> str | None:
        """Extract the 'Fix Description' section from bug comments.

        Searches all comments for a block starting with the keyword
        'Fix Description' (case-insensitive) and returns the text that
        follows it, up to the next recognised section heading or end of
        comment.

        Args:
            bug_id: Numeric Bugzilla bug ID.

        Returns:
            The extracted fix description text, or None if not found.
        """
        import re

        # Match exactly "Fix Description" (case-sensitive) as a section header,
        # optionally followed by a colon. Captures text up to the next known
        # section heading or end of comment.
        _FIX_DESC_RE = re.compile(
            r"Fix Description\s*:?\s*\n?(.*?)(?=\n\s*(?:Root Cause Analysis|Steps to Reproduce|Notes?|References?|Attachments?)\s*:|$)",
            re.DOTALL,
        )

        comments = self.get_comments(bug_id)
        for comment in comments:
            text = comment.get("text", "")
            match = _FIX_DESC_RE.search(text)
            if match:
                description = match.group(1).strip()
                if description:
                    log.info(
                        "Bug %d: found Fix Description (%d chars)",
                        bug_id,
                        len(description),
                    )
                    return description

        log.info("Bug %d: no 'Fix Description' section found in comments", bug_id)
        return None

    def resolve_pr_link(self, bug_id: int) -> str:
        """Resolve a bug ID to a Bitbucket PR link.

        Steps:
        1. Fetch bug details — raise if not found.
        2. Check resolution == "FIXED" — raise BugNotFixedError otherwise.
        3. Fetch comments — search for the first Bitbucket PR URL.
        4. Return the PR URL or raise PRLinkNotFoundError.

        Args:
            bug_id: Numeric Bugzilla bug ID.

        Returns:
            The first Bitbucket PR URL found in any comment.

        Raises:
            BugNotFoundError: If the bug does not exist.
            BugNotFixedError: If the bug's resolution is not FIXED.
            PRLinkNotFoundError: If no PR link is found in the comments.
            BugzillaError: On other API failures.
        """
        # Step 1 & 2: Fetch bug and verify FIXED
        bug = self.get_bug(bug_id)
        status = bug.get("status", "")
        resolution = bug.get("resolution", "")

        log.info(
            "Bug %d: status=%r resolution=%r summary=%r",
            bug_id,
            status,
            resolution,
            bug.get("summary", ""),
        )

        if resolution.upper() != "FIXED":
            raise BugNotFixedError(bug_id, status, resolution)

        # Step 3: Search comments for a Bitbucket PR link
        comments = self.get_comments(bug_id)
        log.info("Bug %d: found %d comment(s), searching for PR link...", bug_id, len(comments))

        for comment in comments:
            text = comment.get("text", "")
            match = _BITBUCKET_PR_PATTERN.search(text)
            if match:
                pr_link = match.group(0)
                log.info("Bug %d: found PR link in comment: %s", bug_id, pr_link)
                return pr_link

        raise PRLinkNotFoundError(bug_id)
