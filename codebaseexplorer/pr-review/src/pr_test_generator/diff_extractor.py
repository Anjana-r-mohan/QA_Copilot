"""Diff Extractor module.

Fetches the diffstat from the Bitbucket Cloud REST API v2.0, categorizes
file changes (added, modified, removed, renamed), and returns structured
FileChange objects with grouped counts by change type.

Handles pagination by following the "next" key in responses, up to a
maximum of 10,000 files.

Also fetches raw file content at base and head commits, handling binary
files, oversized files (>1MB), and 404 errors gracefully.
"""

from __future__ import annotations

import logging
from collections import Counter
from typing import Any

from models import FileChange, FileChangeType

from .bitbucket_client import BitbucketClient, BitbucketClientError

log = logging.getLogger("pr_test_generator.diff_extractor")

# Maximum number of files to fetch across all pages
_MAX_FILES = 10_000

# Maximum file size in bytes (1 MB)
_MAX_FILE_SIZE = 1_048_576  # 1 MB

# Binary file extensions to skip
_BINARY_EXTENSIONS = frozenset({
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".webp", ".svg",
    ".pdf", ".zip", ".tar", ".gz", ".bz2", ".7z", ".rar",
    ".jar", ".aar", ".so", ".class", ".dex",
    ".exe", ".dll", ".dylib", ".o", ".a",
    ".mp3", ".mp4", ".wav", ".avi", ".mov", ".mkv",
    ".ttf", ".otf", ".woff", ".woff2", ".eot",
    ".sqlite", ".db", ".bin", ".dat",
    ".keystore", ".jks", ".p12", ".pfx",
})

# Mapping from Bitbucket API status strings to FileChangeType enum
_STATUS_MAP: dict[str, FileChangeType] = {
    "added": FileChangeType.ADDED,
    "modified": FileChangeType.MODIFIED,
    "removed": FileChangeType.REMOVED,
    "renamed": FileChangeType.RENAMED,
}


class DiffExtractorError(Exception):
    """Error raised when diffstat fetching or processing fails."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        self.status_code = status_code
        super().__init__(message)


class DiffExtractor:
    """Fetches and categorizes file changes from a Bitbucket PR diffstat.

    Uses the Bitbucket diffstat endpoint to retrieve the list of changed
    files, maps each entry to a FileChange object with the appropriate
    FileChangeType, and provides grouped counts by change type.
    """

    def __init__(self, client: BitbucketClient) -> None:
        self._client = client

    async def fetch_diffstat(
        self, workspace: str, repo_slug: str, pr_id: int
    ) -> list[FileChange]:
        """Fetch the full diffstat for a pull request with pagination.

        Follows pagination links (the "next" key in responses) until all
        files are retrieved or the 10,000-file cap is reached.

        Args:
            workspace: The Bitbucket workspace slug.
            repo_slug: The repository slug.
            pr_id: The pull request numeric ID.

        Returns:
            A list of FileChange objects (without content — content fetching
            is handled separately).

        Raises:
            DiffExtractorError: If the API returns an unexpected non-success
                response (other than 429/5xx which are handled by the client).
            BitbucketClientError: For auth, rate-limit, or transient errors
                propagated from the BitbucketClient.
        """
        file_changes: list[FileChange] = []
        url: str | None = (
            f"/repositories/{workspace}/{repo_slug}/pullrequests/{pr_id}/diffstat"
        )

        while url is not None and len(file_changes) < _MAX_FILES:
            try:
                response = await self._client.request("GET", url)
            except BitbucketClientError as exc:
                raise DiffExtractorError(
                    f"Failed to fetch diffstat for {workspace}/{repo_slug} "
                    f"PR#{pr_id}: {exc}",
                    status_code=exc.status_code,
                ) from exc

            data: dict[str, Any] = response.json()
            values: list[dict[str, Any]] = data.get("values", [])

            for entry in values:
                if len(file_changes) >= _MAX_FILES:
                    log.warning(
                        "Reached maximum file limit (%d) for %s/%s PR#%d",
                        _MAX_FILES,
                        workspace,
                        repo_slug,
                        pr_id,
                    )
                    break

                file_change = self._parse_entry(entry)
                if file_change is not None:
                    file_changes.append(file_change)

            # Follow pagination
            url = data.get("next")

        log.info(
            "Fetched %d file changes for %s/%s PR#%d",
            len(file_changes),
            workspace,
            repo_slug,
            pr_id,
        )

        return file_changes

    def get_grouped_counts(
        self, file_changes: list[FileChange]
    ) -> dict[FileChangeType, int]:
        """Return the count of files grouped by change type.

        The sum of all counts equals the total number of items in the list.

        Args:
            file_changes: List of FileChange objects to aggregate.

        Returns:
            A dictionary mapping each FileChangeType to its count.
        """
        counter: Counter[FileChangeType] = Counter()
        for fc in file_changes:
            counter[fc.change_type] += 1
        return dict(counter)

    async def fetch_file_contents(
        self,
        workspace: str,
        repo_slug: str,
        file_changes: list[FileChange],
        base_commit: str,
        head_commit: str,
    ) -> list[FileChange]:
        """Fetch raw file content at base and head commits for all changed files.

        For each FileChange:
        - Fetches content at head_commit (for added, modified, renamed files)
        - Fetches content at base_commit (for modified, removed, renamed files)
        - Sets base_content = "" for newly added files
        - Skips binary files (detected via file extension or Content-Type header)
        - Skips files exceeding 1MB (Content-Length header or body size)
        - Handles 404 by logging a warning and setting content to None

        Args:
            workspace: The Bitbucket workspace slug.
            repo_slug: The repository slug.
            file_changes: List of FileChange objects to populate with content.
            base_commit: The base commit hash (destination branch head).
            head_commit: The head commit hash (source branch head).

        Returns:
            The same list of FileChange objects with base_content and
            head_content populated (or None if unavailable).
        """
        for fc in file_changes:
            # Skip binary files based on file extension
            if self._is_binary_extension(fc.path):
                log.info(
                    "Skipping binary file (extension): %s",
                    fc.path,
                )
                continue

            # Fetch head content for all non-removed files
            if fc.change_type != FileChangeType.REMOVED:
                fc.head_content = await self._fetch_file_at_commit(
                    workspace, repo_slug, head_commit, fc.path
                )
            else:
                fc.head_content = None

            # Fetch base content for modified, removed, and renamed files
            if fc.change_type == FileChangeType.ADDED:
                fc.base_content = ""
            elif fc.change_type in (
                FileChangeType.MODIFIED,
                FileChangeType.REMOVED,
                FileChangeType.RENAMED,
            ):
                # For renamed files, fetch base content from old_path
                base_path = fc.old_path if fc.change_type == FileChangeType.RENAMED and fc.old_path else fc.path
                fc.base_content = await self._fetch_file_at_commit(
                    workspace, repo_slug, base_commit, base_path
                )

        return file_changes

    async def _fetch_file_at_commit(
        self,
        workspace: str,
        repo_slug: str,
        commit: str,
        file_path: str,
    ) -> str | None:
        """Fetch raw file content at a specific commit.

        Returns the file content as a string, or None if the file is
        unavailable (404), binary (Content-Type), or exceeds 1MB.

        Args:
            workspace: The Bitbucket workspace slug.
            repo_slug: The repository slug.
            commit: The commit hash to fetch the file at.
            file_path: The path to the file in the repository.

        Returns:
            The file content as a string, or None if unavailable/skipped.
        """
        url = f"/repositories/{workspace}/{repo_slug}/src/{commit}/{file_path}"

        try:
            response = await self._client.request("GET", url)
        except BitbucketClientError as exc:
            if exc.status_code == 404:
                log.warning(
                    "File not found (404) at %s@%s: %s",
                    file_path,
                    commit[:12],
                    exc,
                )
                return None
            # Re-raise other errors (auth, rate-limit, transient)
            raise

        # Check Content-Type for binary content
        content_type = response.headers.get("content-type", "")
        if not self._is_text_content_type(content_type):
            log.info(
                "Skipping binary file (Content-Type: %s): %s@%s",
                content_type,
                file_path,
                commit[:12],
            )
            return None

        # Check file size via Content-Length header or response body
        content_length = response.headers.get("content-length")
        if content_length is not None:
            try:
                size = int(content_length)
                if size > _MAX_FILE_SIZE:
                    log.warning(
                        "Skipping file exceeding 1MB (%d bytes): %s@%s",
                        size,
                        file_path,
                        commit[:12],
                    )
                    return None
            except (ValueError, TypeError):
                pass

        # Get the text content
        text = response.text

        # Check actual body size if Content-Length was absent
        if content_length is None and len(text.encode("utf-8")) > _MAX_FILE_SIZE:
            log.warning(
                "Skipping file exceeding 1MB (body size %d bytes): %s@%s",
                len(text.encode("utf-8")),
                file_path,
                commit[:12],
            )
            return None

        return text

    @staticmethod
    def _is_binary_extension(file_path: str) -> bool:
        """Check if a file has a known binary extension.

        Args:
            file_path: The file path to check.

        Returns:
            True if the file has a binary extension, False otherwise.
        """
        # Extract extension (lowercase)
        dot_idx = file_path.rfind(".")
        if dot_idx == -1:
            return False
        ext = file_path[dot_idx:].lower()
        return ext in _BINARY_EXTENSIONS

    @staticmethod
    def _is_text_content_type(content_type: str) -> bool:
        """Check if a Content-Type header indicates text content.

        Considers text/*, application/json, application/xml, and similar
        as text content. Everything else is treated as binary.

        Args:
            content_type: The Content-Type header value.

        Returns:
            True if the content is text-based, False otherwise.
        """
        if not content_type:
            # If no Content-Type, assume text (Bitbucket may omit it for source files)
            return True

        ct_lower = content_type.lower().split(";")[0].strip()

        # Text types
        if ct_lower.startswith("text/"):
            return True

        # Common text-like application types
        text_application_types = {
            "application/json",
            "application/xml",
            "application/javascript",
            "application/x-javascript",
            "application/typescript",
            "application/x-yaml",
            "application/yaml",
            "application/x-sh",
            "application/x-httpd-php",
            "application/xhtml+xml",
            "application/sql",
            "application/graphql",
            "application/ld+json",
        }
        if ct_lower in text_application_types:
            return True

        # Catch-all for application/*+xml, application/*+json
        if ct_lower.startswith("application/") and (
            ct_lower.endswith("+xml") or ct_lower.endswith("+json")
        ):
            return True

        return False

    def _parse_entry(self, entry: dict[str, Any]) -> FileChange | None:
        """Parse a single diffstat entry into a FileChange object.

        Args:
            entry: A dictionary from the diffstat "values" array.

        Returns:
            A FileChange object, or None if the entry has an unrecognized
            status (logged as a warning).
        """
        status_str: str = entry.get("status", "").lower()
        change_type = _STATUS_MAP.get(status_str)

        if change_type is None:
            log.warning(
                "Unrecognized diffstat status %r, skipping entry: %s",
                status_str,
                entry,
            )
            return None

        # Extract paths from the "new" and "old" objects
        new_obj: dict[str, Any] | None = entry.get("new")
        old_obj: dict[str, Any] | None = entry.get("old")

        new_path: str = ""
        old_path: str | None = None

        if new_obj is not None:
            new_path = new_obj.get("path", "")

        if old_obj is not None:
            old_path = old_obj.get("path")

        # For renamed files: path is the new path, old_path is the previous path
        if change_type == FileChangeType.RENAMED:
            path = new_path
            # old_path already set from old_obj
        elif change_type == FileChangeType.REMOVED:
            # Removed files may not have a "new" entry; use old path
            path = new_path if new_path else (old_path or "")
            old_path = old_path  # keep it for reference
        else:
            path = new_path
            old_path = None  # only relevant for renames

        return FileChange(
            path=path,
            change_type=change_type,
            old_path=old_path if change_type == FileChangeType.RENAMED else None,
        )
