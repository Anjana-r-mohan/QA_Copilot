"""Input resolver for the PR Test Generator.

Determines whether user input is a Bugzilla bug URL or a Bitbucket PR URL,
and resolves it to a Bitbucket PR link ready for analysis.

Resolution logic:
- If the URL matches https://bugzilla.bizom.in/show_bug.cgi?id=<id>:
    1. Extract the bug ID.
    2. Fetch bug from Bugzilla — verify it exists and resolution == FIXED.
    3. Scan comments for the first Bitbucket PR URL.
    4. Also extract the "Fix Description" section from comments.
    5. Return the PR URL + BugzillaContext for further analysis.
- Otherwise, assume it is a Bitbucket PR URL and return it as-is.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

from .bugzilla_client import (
    BugNotFixedError,
    BugNotFoundError,
    BugzillaClient,
    BugzillaError,
    PRLinkNotFoundError,
    parse_bugzilla_url,
)

log = logging.getLogger("pr_test_generator.input_resolver")


@dataclass
class BugzillaContext:
    """Holds Bugzilla bug metadata relevant for discrepancy analysis."""

    bug_id: int
    bug_summary: str
    fix_description: str | None = None
    bug_url: str = ""


def _get_bugzilla_api_key() -> str:
    """Read the Bugzilla API key from the environment.

    Returns:
        The API key string (may be empty if not set).
    """
    return os.environ.get("BUGZILLA_API_KEY", "").strip()


def resolve_input_to_pr_link(raw_input: str) -> str:
    """Resolve a user-supplied URL to a Bitbucket PR link.

    Accepts either:
    - A Bugzilla bug URL: https://bugzilla.bizom.in/show_bug.cgi?id=<id>
    - A Bitbucket PR URL: https://bitbucket.org/...

    For Bugzilla URLs, the bug must be FIXED and contain a Bitbucket PR
    link in its comments. Any other Bugzilla state raises a descriptive
    ValueError so the caller can surface it clearly to the user.

    Args:
        raw_input: The raw URL string entered by the user.

    Returns:
        A Bitbucket PR URL string ready for analysis.

    Raises:
        ValueError: For any resolution failure (bug not found, not fixed,
            no PR link found, missing API key, or API errors).
    """
    pr_link, _ = resolve_input_to_pr_link_with_context(raw_input)
    return pr_link


def resolve_input_to_pr_link_with_context(
    raw_input: str,
) -> tuple[str, BugzillaContext | None]:
    """Resolve a user-supplied URL to a Bitbucket PR link, plus optional Bugzilla context.

    Like ``resolve_input_to_pr_link`` but also returns a ``BugzillaContext``
    object when the input is a Bugzilla URL so callers can use the Fix
    Description for discrepancy analysis.

    Args:
        raw_input: The raw URL string entered by the user.

    Returns:
        A tuple of (bitbucket_pr_link, BugzillaContext | None).
        BugzillaContext is None when the input is a direct Bitbucket PR URL.

    Raises:
        ValueError: For any resolution failure.
    """
    url = raw_input.strip()

    bug_id = parse_bugzilla_url(url)

    if bug_id is None:
        # Not a Bugzilla URL — pass through as a Bitbucket PR link
        log.debug("Input is not a Bugzilla URL, treating as Bitbucket PR link: %s", url)
        return url, None

    # ---- Bugzilla path ----
    log.info("Detected Bugzilla URL, resolving bug %d to PR link...", bug_id)

    api_key = _get_bugzilla_api_key()
    if not api_key:
        raise ValueError(
            "BUGZILLA_API_KEY environment variable is not set. "
            "Set it to your Bugzilla API key to resolve Bugzilla bug URLs."
        )

    try:
        with BugzillaClient(api_key=api_key) as client:
            pr_link = client.resolve_pr_link(bug_id)

            # Fetch bug summary for context
            bug = client.get_bug(bug_id)
            bug_summary = bug.get("summary", "")

            # Try to extract the Fix Description from comments
            fix_description = client.get_fix_description(bug_id)

    except BugNotFoundError as exc:
        raise ValueError(f"Bugzilla bug {bug_id} does not exist: {exc}") from exc
    except BugNotFixedError as exc:
        raise ValueError(str(exc)) from exc
    except PRLinkNotFoundError as exc:
        raise ValueError(str(exc)) from exc
    except BugzillaError as exc:
        raise ValueError(f"Bugzilla API error while resolving bug {bug_id}: {exc}") from exc

    log.info("Resolved bug %d → PR link: %s", bug_id, pr_link)

    context = BugzillaContext(
        bug_id=bug_id,
        bug_summary=bug_summary,
        fix_description=fix_description,
        bug_url=url,
    )
    return pr_link, context
