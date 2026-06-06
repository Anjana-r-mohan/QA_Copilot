"""Thin async client over the Bitbucket Cloud REST API 2.0.

Auth: Basic auth with an Atlassian email + scoped API token. App passwords are
deprecated and not used.

Large diffs: Bitbucket caps a single file's diff at 2000 changed lines or
100 KB, the whole diff at 8000 lines, and 200 files. This client paginates the
diffstat, fetches diffs per-file (with `path` and `context`), and exposes raw
file contents so callers can diff oversized files locally instead.
"""

from __future__ import annotations

import asyncio
import logging
import random
from typing import Any

import httpx

from .config import Settings

log = logging.getLogger("bitbucket_mcp.client")

# Mirror Bitbucket's documented per-file diff limits so callers can decide when
# to fall back to local (worktree) diffing.
MAX_FILE_DIFF_BYTES = 102_400  # 100 KB
MAX_FILE_DIFF_LINES = 2_000

# Retry policy for transient Bitbucket failures (rate limits, 5xx).
_RETRY_STATUSES = {429, 500, 502, 503, 504}
_MAX_ATTEMPTS = 4
_BACKOFF_BASE = 0.5  # seconds; doubled each attempt, plus jitter
_BACKOFF_CAP = 30.0


class BitbucketError(RuntimeError):
    """An HTTP error from Bitbucket, mapped to an actionable message."""

    def __init__(self, status: int, hint: str, detail: str = "") -> None:
        self.status = status
        self.hint = hint
        msg = f"Bitbucket {status}: {hint}"
        if detail:
            msg += f" ({detail})"
        super().__init__(msg)


_STATUS_HINTS = {
    401: "unauthorized — check BITBUCKET_EMAIL / BITBUCKET_API_TOKEN and that the token hasn't expired",
    403: "forbidden — token is missing a required scope (see PERMISSIONS.md)",
    404: "not found — wrong workspace/repo slug or PR id, or no access to it",
    429: "rate limited — too many requests; retries exhausted",
}


def _map_error(exc: httpx.HTTPStatusError) -> BitbucketError:
    status = exc.response.status_code
    hint = _STATUS_HINTS.get(status, exc.response.reason_phrase or "request failed")
    detail = (exc.response.text or "")[:200].replace("\n", " ").strip()
    return BitbucketError(status, hint, detail)


class BitbucketClient:
    """Client scoped to a single workspace; repo slug passed per call."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._http = httpx.AsyncClient(
            base_url=settings.base_url,
            auth=settings.basic_auth,
            headers={"Accept": "application/json"},
            timeout=60.0,
            follow_redirects=True,
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    def _repo(self, repo: str) -> str:
        return f"/repositories/{self._settings.workspace}/{repo}"

    async def _request(
        self, method: str, path: str, *, params: Any | None = None, json: Any | None = None
    ) -> httpx.Response:
        """Issue one request with retry+backoff on 429/5xx; map errors to BitbucketError."""
        last_exc: httpx.HTTPStatusError | None = None
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            resp = await self._http.request(method, path, params=params or None, json=json)
            if resp.status_code in _RETRY_STATUSES and attempt < _MAX_ATTEMPTS:
                delay = self._retry_delay(resp, attempt)
                log.warning(
                    "%s %s -> %d, retry %d/%d in %.1fs",
                    method, path, resp.status_code, attempt, _MAX_ATTEMPTS - 1, delay,
                )
                await asyncio.sleep(delay)
                continue
            try:
                resp.raise_for_status()
            except httpx.HTTPStatusError as exc:
                last_exc = exc
                break
            log.debug("%s %s -> %d", method, path, resp.status_code)
            return resp
        raise _map_error(last_exc)  # type: ignore[arg-type]

    @staticmethod
    def _retry_delay(resp: httpx.Response, attempt: int) -> float:
        retry_after = resp.headers.get("Retry-After")
        if retry_after:
            try:
                return min(float(retry_after), _BACKOFF_CAP)
            except ValueError:
                pass
        return min(_BACKOFF_BASE * (2 ** (attempt - 1)) + random.uniform(0, 0.25), _BACKOFF_CAP)

    async def _get(self, path: str, **params: Any) -> dict[str, Any]:
        resp = await self._request("GET", path, params=params)
        return resp.json()

    async def _get_text(self, path: str, **params: Any) -> str:
        resp = await self._request("GET", path, params=params)
        return resp.text

    async def _post(self, path: str, json: Any | None = None) -> dict[str, Any]:
        resp = await self._request("POST", path, json=json)
        return resp.json() if resp.content else {}

    async def _put(self, path: str, json: Any | None = None) -> dict[str, Any]:
        resp = await self._request("PUT", path, json=json)
        return resp.json() if resp.content else {}

    async def _delete(self, path: str) -> None:
        await self._request("DELETE", path)

    async def _paginate(self, path: str, **params: Any) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        next_url: str | None = path
        first_params: dict[str, Any] | None = {"pagelen": 100, **params}
        while next_url:
            data = await self._get(next_url, **(first_params or {}))
            items.extend(data.get("values", []))
            next_url = data.get("next")  # absolute URL; httpx handles it
            first_params = None
        return items

    # --- Repositories --------------------------------------------------

    async def list_repositories(self) -> list[dict[str, Any]]:
        """All repos in the workspace (useful for org-wide review)."""
        return await self._paginate(f"/repositories/{self._settings.workspace}")

    # --- Pull requests -------------------------------------------------

    async def get_pull_request(self, repo: str, pr_id: int) -> dict[str, Any]:
        return await self._get(f"{self._repo(repo)}/pullrequests/{pr_id}")

    async def list_pull_requests(self, repo: str, state: str = "OPEN") -> list[dict[str, Any]]:
        return await self._paginate(f"{self._repo(repo)}/pullrequests", state=state)

    async def get_pull_request_diff(
        self, repo: str, pr_id: int, *, path: str | None = None, context: int = 3
    ) -> str:
        """Unified diff. Pass `path` to limit to one file (avoids whole-diff caps)."""
        params: dict[str, Any] = {"context": context}
        if path:
            params["path"] = path
        return await self._get_text(
            f"{self._repo(repo)}/pullrequests/{pr_id}/diff", **params
        )

    async def list_pull_request_files(self, repo: str, pr_id: int) -> list[dict[str, Any]]:
        """Diffstat: per-file status + line counts (paginated, handles >200 files)."""
        return await self._paginate(f"{self._repo(repo)}/pullrequests/{pr_id}/diffstat")

    async def list_pull_request_comments(self, repo: str, pr_id: int) -> list[dict[str, Any]]:
        return await self._paginate(f"{self._repo(repo)}/pullrequests/{pr_id}/comments")

    async def add_comment(
        self,
        repo: str,
        pr_id: int,
        content: str,
        *,
        file_path: str | None = None,
        line: int | None = None,
        line_from: int | None = None,
    ) -> dict[str, Any]:
        """Post a comment. `line` anchors to the new side (`inline.to`); pass
        `line_from` instead to anchor to a removed line on the old side
        (`inline.from`) when there is no new-side line."""
        payload: dict[str, Any] = {"content": {"raw": content}}
        if file_path is not None:
            inline: dict[str, Any] = {"path": file_path}
            if line is not None:
                inline["to"] = line  # line in the new (destination) file
            elif line_from is not None:
                inline["from"] = line_from  # removed line in the old file
            payload["inline"] = inline
        return await self._post(
            f"{self._repo(repo)}/pullrequests/{pr_id}/comments", payload
        )

    async def reply_comment(
        self, repo: str, pr_id: int, parent_id: int, content: str
    ) -> dict[str, Any]:
        """Reply to an existing comment (threaded conversation)."""
        payload = {"content": {"raw": content}, "parent": {"id": parent_id}}
        return await self._post(f"{self._repo(repo)}/pullrequests/{pr_id}/comments", payload)

    async def resolve_comment(self, repo: str, pr_id: int, comment_id: int) -> dict[str, Any]:
        return await self._post(
            f"{self._repo(repo)}/pullrequests/{pr_id}/comments/{comment_id}/resolve"
        )

    # --- Approvals / review state -------------------------------------

    async def approve(self, repo: str, pr_id: int) -> dict[str, Any]:
        return await self._post(f"{self._repo(repo)}/pullrequests/{pr_id}/approve")

    async def unapprove(self, repo: str, pr_id: int) -> None:
        await self._delete(f"{self._repo(repo)}/pullrequests/{pr_id}/approve")

    async def request_changes(self, repo: str, pr_id: int) -> dict[str, Any]:
        return await self._post(f"{self._repo(repo)}/pullrequests/{pr_id}/request-changes")

    # --- Lifecycle -----------------------------------------------------

    async def merge_pull_request(
        self,
        repo: str,
        pr_id: int,
        *,
        merge_strategy: str = "merge_commit",
        message: str | None = None,
        close_source_branch: bool | None = None,
    ) -> dict[str, Any]:
        """Merge a PR. merge_strategy: merge_commit | squash | fast_forward."""
        payload: dict[str, Any] = {"merge_strategy": merge_strategy}
        if message is not None:
            payload["message"] = message
        if close_source_branch is not None:
            payload["close_source_branch"] = close_source_branch
        return await self._post(f"{self._repo(repo)}/pullrequests/{pr_id}/merge", payload)

    async def decline_pull_request(
        self, repo: str, pr_id: int, message: str | None = None
    ) -> dict[str, Any]:
        payload = {"message": message} if message else None
        return await self._post(f"{self._repo(repo)}/pullrequests/{pr_id}/decline", payload)

    async def list_pull_request_commits(self, repo: str, pr_id: int) -> list[dict[str, Any]]:
        return await self._paginate(f"{self._repo(repo)}/pullrequests/{pr_id}/commits")

    async def get_pull_request_activity(self, repo: str, pr_id: int) -> list[dict[str, Any]]:
        return await self._paginate(f"{self._repo(repo)}/pullrequests/{pr_id}/activity")

    # --- PR tasks ------------------------------------------------------

    async def create_task(
        self, repo: str, pr_id: int, content: str, *, comment_id: int | None = None
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"content": {"raw": content}}
        if comment_id is not None:
            payload["comment"] = {"id": comment_id}
        return await self._post(f"{self._repo(repo)}/pullrequests/{pr_id}/tasks", payload)

    async def list_tasks(self, repo: str, pr_id: int) -> list[dict[str, Any]]:
        return await self._paginate(f"{self._repo(repo)}/pullrequests/{pr_id}/tasks")

    async def resolve_task(self, repo: str, pr_id: int, task_id: int) -> dict[str, Any]:
        return await self._put(
            f"{self._repo(repo)}/pullrequests/{pr_id}/tasks/{task_id}", {"state": "RESOLVED"}
        )

    # --- Commit / build statuses (CI gating) --------------------------

    async def get_commit_statuses(self, repo: str, commit: str) -> list[dict[str, Any]]:
        """All build/CI statuses reported on a commit."""
        return await self._paginate(f"{self._repo(repo)}/commit/{commit}/statuses")

    # --- Code Insights: reports + annotations -------------------------

    async def create_report(
        self,
        repo: str,
        commit: str,
        report_id: str,
        *,
        title: str,
        details: str = "",
        report_type: str = "BUG",  # SECURITY | COVERAGE | TEST | BUG
        result: str = "PASSED",  # PASSED | FAILED | PENDING
        reporter: str = "Bitbucket-MCP",
        data: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Create/update a Code Insights report (idempotent by report_id)."""
        payload: dict[str, Any] = {
            "title": title,
            "details": details,
            "report_type": report_type,
            "result": result,
            "reporter": reporter,
        }
        if data:
            payload["data"] = data
        return await self._put(
            f"{self._repo(repo)}/commit/{commit}/reports/{report_id}", payload
        )

    async def add_annotations(
        self, repo: str, commit: str, report_id: str, annotations: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Bulk-add annotations (line-level findings). Chunked at 100 per request."""
        out: list[dict[str, Any]] = []
        base = f"{self._repo(repo)}/commit/{commit}/reports/{report_id}/annotations"
        for i in range(0, len(annotations), 100):
            res = await self._post(base, annotations[i : i + 100])
            if isinstance(res, dict) and res.get("values"):
                out.extend(res["values"])
        return out

    # --- Source files (raw) -------------------------------------------

    async def get_file_at(self, repo: str, commit: str, path: str) -> str:
        """Raw file content at a commit. Used to diff oversized files locally."""
        return await self._get_text(f"{self._repo(repo)}/src/{commit}/{path}")
