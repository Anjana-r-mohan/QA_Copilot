"""Review orchestrator: combine the API diff (authoritative line anchors) with a
local worktree (deep analysis), and post inline comments back at the right line.

Division of labour:
- Bitbucket API  -> what changed + the exact line numbers inline comments must use.
- Local worktree -> reading full files, resolving deps, running checks/regression.
- Local merge-base diff -> fallback for files the API truncates (oversized/binary),
  with line numbers that still match Bitbucket.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from .client import BitbucketClient
from .diffutil import collect_pr_diff, parse_added_lines
from .worktree import WorktreeManager


@dataclass
class ReviewFileContext:
    path: str
    status: str
    lines_added: int
    lines_removed: int
    diff: str | None  # unified diff (API or local fallback)
    diff_source: str  # "api" | "local-merge-base" | "none"
    anchor_lines: list[int] = field(default_factory=list)  # valid inline.to lines
    note: str = ""


@dataclass
class ReviewContext:
    repo: str
    pr_id: int
    title: str
    source_branch: str
    destination_branch: str
    source_commit: str | None
    worktree_path: str
    user_query: str = ""
    files: list[ReviewFileContext] = field(default_factory=list)


async def prepare_review(
    client: BitbucketClient,
    worktrees: WorktreeManager,
    repo: str,
    pr_id: int,
    *,
    context: int = 3,
    checkout: bool = True,
    user_query: str = "",
) -> ReviewContext:
    """Assemble everything an agent needs to review a PR in one pass.

    Pulls the PR's per-file diffs from the API (with anchor lines), fills in
    oversized/binary files from a local merge-base diff, and checks the branch
    out into a worktree for local analysis.
    """
    pr = await client.get_pull_request(repo, pr_id)
    source = (pr.get("source") or {}).get("branch", {}).get("name")
    dest = (pr.get("destination") or {}).get("branch", {}).get("name")
    source_commit = (pr.get("source") or {}).get("commit", {}).get("hash")

    api = await collect_pr_diff(client, repo, pr_id, context=context)

    worktree_path = ""
    if checkout and source:
        wt = await worktrees.create(repo, source)
        worktree_path = wt.path

    files: list[ReviewFileContext] = []
    for fd in api.files:
        diff_text = fd.diff
        diff_source = "api" if fd.diff else "none"

        # Fall back to local merge-base diff for anything the API dropped.
        if fd.diff is None and not fd.binary and source and dest:
            try:
                local = await worktrees.merge_base_diff(
                    repo, source, dest, path=fd.path, context=context
                )
                if local.strip():
                    diff_text = local
                    diff_source = "local-merge-base"
            except Exception as exc:  # noqa: BLE001
                fd.note = (fd.note + f"; local diff failed: {exc}").strip("; ")

        anchors = parse_added_lines(diff_text).get(fd.path, []) if diff_text else []
        files.append(
            ReviewFileContext(
                path=fd.path,
                status=fd.status,
                lines_added=fd.lines_added,
                lines_removed=fd.lines_removed,
                diff=diff_text,
                diff_source=diff_source,
                anchor_lines=anchors,
                note=fd.note,
            )
        )

    return ReviewContext(
        repo=repo,
        pr_id=pr_id,
        title=pr.get("title", ""),
        source_branch=source or "",
        destination_branch=dest or "",
        source_commit=source_commit,
        worktree_path=worktree_path,
        user_query=user_query,
        files=files,
    )


@dataclass
class Finding:
    path: str
    line: int
    body: str


async def post_findings(
    client: BitbucketClient,
    repo: str,
    pr_id: int,
    findings: list[Finding],
    *,
    summary: str | None = None,
    validate_against: ReviewContext | None = None,
) -> dict[str, Any]:
    """Post inline comments for each finding, plus an optional summary comment.

    If `validate_against` is given, findings whose (path, line) is not a valid
    anchor are downgraded to file-level comments so Bitbucket doesn't reject or
    misplace them.
    """
    anchor_map: dict[str, set[int]] = {}
    if validate_against:
        anchor_map = {f.path: set(f.anchor_lines) for f in validate_against.files}

    posted: list[dict[str, Any]] = []
    for f in findings:
        line: int | None = f.line
        if anchor_map and f.line not in anchor_map.get(f.path, set()):
            line = None  # not an added line -> file-level comment
        res = await client.add_comment(
            repo, pr_id, f.body, file_path=f.path, line=line
        )
        posted.append(
            {"id": res.get("id"), "path": f.path, "line": line, "inline": line is not None}
        )

    summary_res = None
    if summary:
        summary_res = await client.add_comment(repo, pr_id, summary)

    return {
        "comments_posted": len(posted),
        "comments": posted,
        "summary_comment_id": (summary_res or {}).get("id"),
    }


def review_context_to_dict(ctx: ReviewContext) -> dict[str, Any]:
    return asdict(ctx)


def format_review_metadata(ctx: ReviewContext) -> str:
    """One-block audit header to prepend to any review summary.

    Lets the reviewer verify:
    - which commit was reviewed (so they can check if new commits landed after)
    - what the original reviewer query was
    - whether the temporary worktree was cleaned up
    """
    commit = ctx.source_commit or "unknown"
    short = commit[:7] if len(commit) > 7 else commit
    lines = [
        "---",
        "**Review metadata**",
        f"- **PR**: #{ctx.pr_id} — {ctx.title}",
        f"- **Reviewed commit**: `{short}` (`{ctx.source_branch}` → `{ctx.destination_branch}`)",
    ]
    if ctx.user_query:
        lines.append(f"- **Reviewer query**: {ctx.user_query}")
    lines.append("---")
    return "\n".join(lines)


# --- Autonomous orchestrator --------------------------------------------------

# Map an annotation severity to a Code Insights annotation_type default.
def _annotation(path: str, line: int, summary: str, severity: str, kind: str) -> dict[str, Any]:
    return {
        "external_id": f"bitbucket-mcp-{path}-{line}",
        "title": summary[:100],
        "annotation_type": kind,  # VULNERABILITY | CODE_SMELL | BUG
        "summary": summary,
        "severity": severity,  # CRITICAL | HIGH | MEDIUM | LOW
        "path": path,
        "line": line,
    }


async def review_pull_request(
    client: BitbucketClient,
    worktrees: WorktreeManager,
    repo: str,
    pr_id: int,
    *,
    findings: list[dict[str, Any]] | None = None,
    summary: str | None = None,
    report_id: str = "bitbucket-mcp",
    fail_report: bool = False,
    require_green_ci: bool = False,
    user_query: str = "",
) -> dict[str, Any]:
    """Capstone: gate on CI, then publish findings as a Code Insights report.

    `findings`: [{"path","line","summary","severity","kind"}]. When provided they
    are posted as line-level annotations under a single report on the PR's source
    commit (cleaner than many inline comments). An optional `summary` is posted as
    a normal PR comment. Set `require_green_ci` to refuse publishing on a red build.
    The worktree for `repo`/source-branch is removed automatically after publishing.
    """
    pr = await client.get_pull_request(repo, pr_id)
    commit = (pr.get("source") or {}).get("commit", {}).get("hash")
    source_branch = (pr.get("source") or {}).get("branch", {}).get("name", "")
    dest_branch = (pr.get("destination") or {}).get("branch", {}).get("name", "")

    statuses = await client.get_commit_statuses(repo, commit) if commit else []
    ci = [{"key": s.get("key"), "state": s.get("state")} for s in statuses]
    red = any(s.get("state") in ("FAILED", "ERROR") for s in statuses)
    if require_green_ci and red:
        return {"published": False, "reason": "CI not green", "ci": ci}

    # Build a lightweight ReviewContext just for the metadata header.
    meta_ctx = ReviewContext(
        repo=repo,
        pr_id=pr_id,
        title=pr.get("title", ""),
        source_branch=source_branch,
        destination_branch=dest_branch,
        source_commit=commit,
        worktree_path="",
        user_query=user_query,
    )
    metadata_header = format_review_metadata(meta_ctx)

    published_annotations = 0
    if findings and commit:
        await client.create_report(
            repo,
            commit,
            report_id,
            title="Bitbucket-MCP",
            details=f"{len(findings)} finding(s) from automated review.",
            report_type="BUG",
            result="FAILED" if fail_report else "PASSED",
        )
        annotations = [
            _annotation(
                f["path"],
                int(f["line"]),
                f.get("summary", ""),
                f.get("severity", "MEDIUM"),
                f.get("kind", "CODE_SMELL"),
            )
            for f in findings
        ]
        posted = await client.add_annotations(repo, commit, report_id, annotations)
        published_annotations = len(posted)

    summary_id = None
    full_summary = "\n\n".join(filter(None, [metadata_header, summary]))
    if full_summary:
        res = await client.add_comment(repo, pr_id, full_summary)
        summary_id = res.get("id")

    # Clean up the worktree so no temp files are left after the review.
    worktree_cleaned = False
    if source_branch:
        try:
            await worktrees.remove(repo, source_branch)
            worktree_cleaned = True
        except Exception:  # noqa: BLE001
            pass

    return {
        "published": True,
        "commit": commit,
        "ci": ci,
        "annotations_posted": published_annotations,
        "report_id": report_id if findings else None,
        "summary_comment_id": summary_id,
        "worktree_cleaned": worktree_cleaned,
        "metadata": metadata_header,
    }
