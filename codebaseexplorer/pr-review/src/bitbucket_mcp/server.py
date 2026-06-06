"""FastMCP server exposing Bitbucket Bitbucket-MCP tools (Bitbucket-MCP).

Works across every repo in the workspace: pass the repo slug to each tool.
Run locally:  uv run bitbucket-mcp
Run via uvx:  uvx bitbucket-mcp
"""

from __future__ import annotations

import asyncio
import atexit
import logging
from collections import OrderedDict
from dataclasses import asdict
from typing import Any

from fastmcp import FastMCP

from . import analysis as _an
from .client import BitbucketClient
from .config import Settings, load_settings
from .diffutil import collect_pr_diff
from .review import (
    Finding,
    ReviewContext,
    format_review_metadata,
    post_findings,
    review_context_to_dict,
    review_pull_request as _review_pr,
)
from .review import prepare_review as build_review_context
from .worktree import WorktreeManager

log = logging.getLogger("bitbucket_mcp.server")

# Bound the anchor cache so a long-lived process doesn't grow without limit.
_CACHE_MAX = 64

mcp: FastMCP = FastMCP(
    name="bitbucket-mcp",
    instructions=(
        "Tools for reviewing Bitbucket Cloud pull requests across an org's repos. "
        "Every tool takes a `repo` slug. Use get_pull_request + get_pr_diff to read a "
        "change (diff is fetched file-by-file so large PRs aren't truncated), "
        "create_worktree to check the branch out locally for dependency/regression "
        "analysis, and add_review_comment for inline feedback."
    ),
)

_settings: Settings | None = None
_client: BitbucketClient | None = None
_worktrees: WorktreeManager | None = None
# Bounded LRU of the latest review context per (repo, pr_id) so
# post_review_comments can validate comment lines against the computed anchors.
# Validity is tied to the PR's source commit (see post_review_comments).
_review_cache: "OrderedDict[tuple[str, int], ReviewContext]" = OrderedDict()


def _cache_put(repo: str, pr_id: int, ctx: ReviewContext) -> None:
    key = (repo, pr_id)
    _review_cache[key] = ctx
    _review_cache.move_to_end(key)
    while len(_review_cache) > _CACHE_MAX:
        _review_cache.popitem(last=False)


def _cfg() -> Settings:
    global _settings
    if _settings is None:
        _settings = load_settings()
        logging.basicConfig(level=getattr(logging, _settings.log_level, logging.WARNING))
    return _settings


def _client_() -> BitbucketClient:
    global _client
    if _client is None:
        _client = BitbucketClient(_cfg())
    return _client


def _wt() -> WorktreeManager:
    global _worktrees
    if _worktrees is None:
        _worktrees = WorktreeManager(_cfg())
    return _worktrees


@mcp.tool
async def list_repositories() -> list[dict[str, Any]]:
    """List all repositories in the workspace (slug + name)."""
    repos = await _client_().list_repositories()
    return [{"slug": r.get("slug"), "name": r.get("name")} for r in repos]


@mcp.tool
async def list_open_pull_requests(repo: str, state: str = "OPEN") -> list[dict[str, Any]]:
    """List PRs for a repo (state: OPEN, MERGED, DECLINED, SUPERSEDED)."""
    prs = await _client_().list_pull_requests(repo, state=state)
    return [
        {
            "id": p.get("id"),
            "title": p.get("title"),
            "author": (p.get("author") or {}).get("display_name"),
            "source": (p.get("source") or {}).get("branch", {}).get("name"),
            "destination": (p.get("destination") or {}).get("branch", {}).get("name"),
        }
        for p in prs
    ]


@mcp.tool
async def get_pull_request(repo: str, pr_id: int) -> dict[str, Any]:
    """PR metadata: title, description, author, branches, state, source commit."""
    pr = await _client_().get_pull_request(repo, pr_id)
    return {
        "id": pr.get("id"),
        "title": pr.get("title"),
        "description": pr.get("description"),
        "state": pr.get("state"),
        "author": (pr.get("author") or {}).get("display_name"),
        "source_branch": (pr.get("source") or {}).get("branch", {}).get("name"),
        "destination_branch": (pr.get("destination") or {}).get("branch", {}).get("name"),
        "source_commit": (pr.get("source") or {}).get("commit", {}).get("hash"),
        "url": (pr.get("links") or {}).get("html", {}).get("href"),
    }


@mcp.tool
async def get_pr_diff(repo: str, pr_id: int, context: int = 3) -> dict[str, Any]:
    """Full PR diff fetched file-by-file (avoids Bitbucket's whole-diff truncation).

    Oversized or binary files are flagged in `truncated_files`; use
    create_worktree + read the files locally to diff those.
    """
    pr = await collect_pr_diff(_client_(), repo, pr_id, context=context)
    return {
        "files": [asdict(f) for f in pr.files],
        "truncated_files": pr.truncated_files,
        "file_count": len(pr.files),
    }


@mcp.tool
async def get_file_diff(repo: str, pr_id: int, path: str, context: int = 3) -> str:
    """Raw unified diff for a single file in a PR."""
    return await _client_().get_pull_request_diff(repo, pr_id, path=path, context=context)


@mcp.tool
async def list_pull_request_comments(repo: str, pr_id: int) -> list[dict[str, Any]]:
    """Existing PR comments (avoid posting duplicate feedback)."""
    raw = await _client_().list_pull_request_comments(repo, pr_id)
    return [
        {
            "id": c.get("id"),
            "author": (c.get("user") or {}).get("display_name"),
            "content": (c.get("content") or {}).get("raw"),
            "inline": c.get("inline"),
        }
        for c in raw
        if not c.get("deleted")
    ]


@mcp.tool
async def add_review_comment(
    repo: str,
    pr_id: int,
    content: str,
    file_path: str | None = None,
    line: int | None = None,
    line_from: int | None = None,
) -> dict[str, Any]:
    """Post a comment. Provide file_path + line for an inline comment on the new
    side; pass line_from instead to anchor to a removed line on the old side."""
    res = await _client_().add_comment(
        repo, pr_id, content, file_path=file_path, line=line, line_from=line_from
    )
    return {"id": res.get("id"), "created": True}


@mcp.tool
async def approve_pull_request(repo: str, pr_id: int) -> dict[str, Any]:
    """Approve a PR (requires a write:pullrequest scoped token)."""
    await _client_().approve(repo, pr_id)
    return {"approved": True}


@mcp.tool
async def local_diff(repo: str, source_branch: str, destination_branch: str, path: str | None = None, context: int = 3) -> str:
    """Local merge-base diff (matches Bitbucket line numbers, no size limit).

    Use for oversized/binary files the API can't diff, or to cross-check the API.
    """
    return await _wt().merge_base_diff(
        repo, source_branch, destination_branch, path=path, context=context
    )


@mcp.tool
async def prepare_review(repo: str, pr_id: int, context: int = 3, checkout: bool = True, user_query: str = "") -> dict[str, Any]:
    """One-shot review context combining both powers.

    Returns, per changed file: the diff (from the API, or a local merge-base diff
    if the API truncated it), the valid inline `anchor_lines`, and the checked-out
    `worktree_path` for deep/regression analysis. Comment with post_review_comments.

    Pass `user_query` to record the reviewer's original question in the review
    metadata — it is surfaced in any summary posted to Bitbucket and in the
    `metadata` field of the returned context so the reviewer can audit what was asked.
    """
    ctx = await build_review_context(
        _client_(), _wt(), repo, pr_id,
        context=context, checkout=checkout, user_query=user_query,
    )
    # Stash for validation when posting, keyed by (repo, pr_id).
    _cache_put(repo, pr_id, ctx)
    result = review_context_to_dict(ctx)
    result["metadata"] = format_review_metadata(ctx)
    return result


async def _fresh_context(repo: str, pr_id: int) -> ReviewContext:
    """Return cached anchors only if still valid for the PR's current source
    commit; otherwise re-derive them (the PR was updated since prepare_review)."""
    cached = _review_cache.get((repo, pr_id))
    pr = await _client_().get_pull_request(repo, pr_id)
    current = (pr.get("source") or {}).get("commit", {}).get("hash")
    if cached is not None and cached.source_commit == current:
        return cached
    log.info("anchor cache stale for %s#%d (commit changed); re-deriving", repo, pr_id)
    ctx = await build_review_context(_client_(), _wt(), repo, pr_id, checkout=False)
    _cache_put(repo, pr_id, ctx)
    return ctx


@mcp.tool
async def post_review_comments(repo: str, pr_id: int, comments: list[dict[str, Any]], summary: str | None = None) -> dict[str, Any]:
    """Post inline review comments at specific lines, plus an optional summary.

    Each comment: {"path": str, "line": int, "body": str}. Anchors are validated
    against the PR's current source commit (re-derived if the PR changed since
    prepare_review); lines that aren't a valid anchor are downgraded to
    file-level comments so Bitbucket won't reject or misplace them.

    The review metadata header (reviewed commit, user query) is automatically
    prepended to the summary comment. The worktree is cleaned up after posting.
    """
    ctx = await _fresh_context(repo, pr_id)
    findings = [Finding(path=c["path"], line=int(c["line"]), body=c["body"]) for c in comments]

    metadata_header = format_review_metadata(ctx)
    full_summary = "\n\n".join(filter(None, [metadata_header, summary]))

    result = await post_findings(
        _client_(), repo, pr_id, findings,
        summary=full_summary or None, validate_against=ctx,
    )

    # Clean up worktree — no temp files left after posting.
    worktree_cleaned = False
    if ctx.source_branch:
        try:
            await _wt().remove(repo, ctx.source_branch)
            worktree_cleaned = True
        except Exception:  # noqa: BLE001
            pass

    result["worktree_cleaned"] = worktree_cleaned
    result["metadata"] = metadata_header
    return result


@mcp.tool
async def create_worktree(repo: str, branch: str) -> dict[str, Any]:
    """Check a PR branch out into an isolated worktree for local analysis.

    Clones the repo on demand if no local clone is configured. Returns the path;
    read files there to inspect dependencies and run regression checks.
    """
    wt = await _wt().create(repo, branch)
    return {"repo": wt.repo, "branch": wt.branch, "path": wt.path}


@mcp.tool
async def cleanup_worktree(repo: str, branch: str) -> dict[str, Any]:
    """Remove a previously created review worktree."""
    await _wt().remove(repo, branch)
    return {"removed": True, "repo": repo, "branch": branch}


@mcp.tool
async def list_worktrees(repo: str) -> str:
    """List active git worktrees for a repo's local clone."""
    return await _wt().list(repo)


# --- Lifecycle / review state ----------------------------------------------


@mcp.tool
async def merge_pull_request(repo: str, pr_id: int, merge_strategy: str = "merge_commit", message: str | None = None, close_source_branch: bool | None = None) -> dict[str, Any]:
    """Merge a PR. merge_strategy: merge_commit | squash | fast_forward."""
    return await _client_().merge_pull_request(
        repo, pr_id, merge_strategy=merge_strategy, message=message,
        close_source_branch=close_source_branch,
    )


@mcp.tool
async def decline_pull_request(repo: str, pr_id: int, message: str | None = None) -> dict[str, Any]:
    """Decline (reject) a PR."""
    return await _client_().decline_pull_request(repo, pr_id, message=message)


@mcp.tool
async def request_changes(repo: str, pr_id: int) -> dict[str, Any]:
    """Mark the PR as needing changes (the reviewer 'request changes' state)."""
    return await _client_().request_changes(repo, pr_id)


@mcp.tool
async def unapprove_pull_request(repo: str, pr_id: int) -> dict[str, Any]:
    """Withdraw a previous approval."""
    await _client_().unapprove(repo, pr_id)
    return {"unapproved": True}


@mcp.tool
async def list_pr_commits(repo: str, pr_id: int) -> list[dict[str, Any]]:
    """Commits in a PR, chronological."""
    commits = await _client_().list_pull_request_commits(repo, pr_id)
    return [{"hash": c.get("hash"), "message": (c.get("message") or "").strip(), "author": (c.get("author") or {}).get("raw")} for c in commits]


@mcp.tool
async def get_pr_activity(repo: str, pr_id: int) -> list[dict[str, Any]]:
    """PR activity timeline (approvals, updates, comments)."""
    return await _client_().get_pull_request_activity(repo, pr_id)


@mcp.tool
async def reply_to_comment(repo: str, pr_id: int, parent_comment_id: int, content: str) -> dict[str, Any]:
    """Reply to an existing comment (threaded)."""
    res = await _client_().reply_comment(repo, pr_id, parent_comment_id, content)
    return {"id": res.get("id")}


@mcp.tool
async def resolve_comment(repo: str, pr_id: int, comment_id: int) -> dict[str, Any]:
    """Resolve a comment thread."""
    return await _client_().resolve_comment(repo, pr_id, comment_id)


@mcp.tool
async def create_task(repo: str, pr_id: int, content: str, comment_id: int | None = None) -> dict[str, Any]:
    """Create an actionable PR task (optionally attached to a comment)."""
    res = await _client_().create_task(repo, pr_id, content, comment_id=comment_id)
    return {"id": res.get("id")}


@mcp.tool
async def list_tasks(repo: str, pr_id: int) -> list[dict[str, Any]]:
    """List PR tasks and their state."""
    tasks = await _client_().list_tasks(repo, pr_id)
    return [{"id": t.get("id"), "state": t.get("state"), "content": (t.get("content") or {}).get("raw")} for t in tasks]


@mcp.tool
async def resolve_task(repo: str, pr_id: int, task_id: int) -> dict[str, Any]:
    """Mark a PR task resolved."""
    return await _client_().resolve_task(repo, pr_id, task_id)


# --- CI gating ---------------------------------------------------------------


@mcp.tool
async def get_commit_statuses(repo: str, commit: str) -> list[dict[str, Any]]:
    """Build/CI statuses reported on a commit (use the PR source commit)."""
    statuses = await _client_().get_commit_statuses(repo, commit)
    return [{"key": s.get("key"), "state": s.get("state"), "name": s.get("name"), "url": s.get("url")} for s in statuses]


# --- Code Insights -----------------------------------------------------------


@mcp.tool
async def publish_report(repo: str, commit: str, report_id: str, title: str, details: str = "", report_type: str = "BUG", result: str = "PASSED") -> dict[str, Any]:
    """Create/update a Code Insights report on a commit (idempotent by report_id)."""
    return await _client_().create_report(repo, commit, report_id, title=title, details=details, report_type=report_type, result=result)


@mcp.tool
async def add_annotations(repo: str, commit: str, report_id: str, annotations: list[dict[str, Any]]) -> dict[str, Any]:
    """Bulk-add line-level findings to a report.

    Each annotation: {path, line, summary, annotation_type (VULNERABILITY|CODE_SMELL|BUG),
    severity (CRITICAL|HIGH|MEDIUM|LOW), external_id?}.
    """
    posted = await _client_().add_annotations(repo, commit, report_id, annotations)
    return {"posted": len(posted)}


# --- Worktree analysis -------------------------------------------------------


def _require_exec() -> None:
    if not _cfg().allow_exec:
        raise PermissionError(
            "Arbitrary command execution is disabled. Set BITBUCKET_ALLOW_EXEC=true to "
            "enable run_in_worktree / run_tests_base_vs_pr (executes shell with full env "
            "and network — only enable for trusted repos)."
        )


@mcp.tool
async def run_in_worktree(repo: str, branch: str, command: str, timeout: int = 600) -> dict[str, Any]:
    """Run a shell command (lint/test/build) inside the checked-out PR branch.

    Disabled unless BITBUCKET_ALLOW_EXEC=true (runs arbitrary shell)."""
    _require_exec()
    wt = await _wt().create(repo, branch)
    res = await _an.run_command(wt.path, command, timeout=timeout)
    return {"exit_code": res.exit_code, "timed_out": res.timed_out, "stdout": res.stdout, "stderr": res.stderr, "cwd": res.cwd}


@mcp.tool
async def search_code(repo: str, branch: str, pattern: str, max_results: int = 200) -> list[dict[str, Any]]:
    """Search the checked-out PR tree (ripgrep/git grep). Returns path/line/text."""
    wt = await _wt().ensure(repo, branch)
    return await _an.search_code(wt.path, pattern, max_results=max_results)


@mcp.tool
async def impact_analysis(repo: str, pr_id: int) -> dict[str, Any]:
    """Find call sites across the tree for symbols changed in the PR."""
    pr = await _client_().get_pull_request(repo, pr_id)
    source = (pr.get("source") or {}).get("branch", {}).get("name")
    rep = await _an.impact_analysis(_client_(), _wt(), repo, pr_id, source_branch=source)
    return {"symbols": rep.symbols, "references": rep.references}


@mcp.tool
async def run_tests_base_vs_pr(repo: str, pr_id: int, test_command: str, timeout: int = 1800) -> dict[str, Any]:
    """Run tests on the merge base and the PR head; flag regressions.

    Disabled unless BITBUCKET_ALLOW_EXEC=true (runs arbitrary shell)."""
    _require_exec()
    r = await _an.run_tests_base_vs_pr(_client_(), _wt(), repo, pr_id, test_command, timeout=timeout)
    return {"regressed": r.regressed, "base_exit_code": r.base_exit_code, "pr_exit_code": r.pr_exit_code, "base_output": r.base_output, "pr_output": r.pr_output}


@mcp.tool
async def read_pr_file(repo: str, commit: str, path: str) -> str:
    """Read a file's full contents at a commit (e.g. the PR source commit)."""
    return await _client_().get_file_at(repo, commit, path)


# --- Capstone orchestrator ---------------------------------------------------


@mcp.tool
async def review_pull_request(repo: str, pr_id: int, findings: list[dict[str, Any]] | None = None, summary: str | None = None, report_id: str = "bitbucket-mcp", fail_report: bool = False, require_green_ci: bool = False, user_query: str = "") -> dict[str, Any]:
    """Publish a full review: gate on CI, post findings as a Code Insights report, add a summary comment.

    findings: [{"path","line","summary","severity","kind"}] (kind = VULNERABILITY|CODE_SMELL|BUG).
    The review metadata (reviewed commit, user_query) is prepended to the summary comment and
    the worktree is automatically removed after publishing.
    """
    return await _review_pr(
        _client_(), _wt(), repo, pr_id,
        findings=findings, summary=summary, report_id=report_id,
        fail_report=fail_report, require_green_ci=require_green_ci,
        user_query=user_query,
    )


@mcp.tool
async def health_check() -> dict[str, Any]:
    """Validate the token + workspace access at call time.

    Turns silent misconfiguration (bad/expired token, wrong workspace, missing
    scope) into an explicit, actionable result instead of a later failure.
    """
    cfg = _cfg()
    auth_mode = "basic-api-token"
    try:
        repos = await _client_().list_repositories()
    except Exception as exc:  # noqa: BLE001 - surface the reason to the caller
        return {"ok": False, "workspace": cfg.workspace, "auth": auth_mode, "error": str(exc)}
    return {
        "ok": True,
        "workspace": cfg.workspace,
        "auth": auth_mode,
        "repo_count": len(repos),
        "exec_enabled": cfg.allow_exec,
    }


def _shutdown() -> None:
    """Close the shared httpx client on process exit (no leaked connections)."""
    if _client is None:
        return
    try:
        asyncio.run(_client.aclose())
    except Exception:  # noqa: BLE001 - best-effort cleanup at exit
        pass


def main() -> None:
    """Console entry point (stdio transport)."""
    atexit.register(_shutdown)
    mcp.run()


if __name__ == "__main__":
    main()
