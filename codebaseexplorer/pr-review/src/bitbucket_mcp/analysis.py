"""Worktree-powered analysis — the capabilities the API alone can't provide.

Everything here runs against a checked-out worktree: running the project's own
lint/test/build commands, searching the tree, finding callers of changed
symbols, and comparing test results between the PR and its merge base (true
regression detection).
"""

from __future__ import annotations

import asyncio
import re
import shutil
from dataclasses import dataclass, field
from typing import Any

from .client import BitbucketClient
from .diffutil import collect_pr_diff
from .worktree import WorktreeManager

_OUTPUT_CAP = 20_000  # chars kept from command output (head+tail)


def _cap(text: str) -> str:
    if len(text) <= _OUTPUT_CAP:
        return text
    half = _OUTPUT_CAP // 2
    return text[:half] + "\n...[truncated]...\n" + text[-half:]


@dataclass
class CommandResult:
    command: str
    cwd: str
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool = False


async def run_command(cwd: str, command: str, *, timeout: int = 600) -> CommandResult:
    """Run a shell command in a worktree dir, capturing output (capped)."""
    proc = await asyncio.create_subprocess_shell(
        command,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return CommandResult(
            command=command,
            cwd=cwd,
            exit_code=proc.returncode if proc.returncode is not None else -1,
            stdout=_cap(out.decode(errors="replace")),
            stderr=_cap(err.decode(errors="replace")),
        )
    except asyncio.TimeoutError:
        proc.kill()
        return CommandResult(command, cwd, -1, "", f"timed out after {timeout}s", timed_out=True)


async def search_code(cwd: str, pattern: str, *, max_results: int = 200) -> list[dict[str, Any]]:
    """Search the worktree (ripgrep if available, else git grep)."""
    if shutil.which("rg"):
        cmd = f"rg --line-number --no-heading --color never -e {_shquote(pattern)}"
    else:
        cmd = f"git grep -n -e {_shquote(pattern)}"
    res = await run_command(cwd, cmd, timeout=60)
    hits: list[dict[str, Any]] = []
    for line in res.stdout.splitlines():
        m = re.match(r"^(.*?):(\d+):(.*)$", line)
        if m:
            hits.append({"path": m.group(1), "line": int(m.group(2)), "text": m.group(3)})
        if len(hits) >= max_results:
            break
    return hits


def _shquote(s: str) -> str:
    return "'" + s.replace("'", "'\\''") + "'"


# Heuristic patterns for "what was defined/changed" across common languages.
_DEF_PATTERNS = [
    r"def\s+([A-Za-z_]\w*)",  # python
    r"class\s+([A-Za-z_]\w*)",  # python/js/java
    r"function\s+([A-Za-z_]\w*)",  # js
    r"func\s+([A-Za-z_]\w*)",  # go
    r"(?:public|private|protected|static|\s)+[\w<>\[\]]+\s+([A-Za-z_]\w*)\s*\(",  # java/c#
    r"(?:const|let|var)\s+([A-Za-z_]\w*)\s*=",  # js consts
]


def changed_symbols(diff_text: str) -> list[str]:
    """Extract symbol names from *added* lines of a unified diff."""
    names: set[str] = set()
    for line in diff_text.splitlines():
        if not line.startswith("+") or line.startswith("+++"):
            continue
        body = line[1:]
        for pat in _DEF_PATTERNS:
            for m in re.finditer(pat, body):
                names.add(m.group(1))
    # Drop noise (very short / common keywords).
    return sorted(n for n in names if len(n) > 2)


@dataclass
class ImpactReport:
    symbols: list[str] = field(default_factory=list)
    references: dict[str, list[dict[str, Any]]] = field(default_factory=dict)


async def impact_analysis(
    client: BitbucketClient,
    worktrees: WorktreeManager,
    repo: str,
    pr_id: int,
    *,
    source_branch: str,
) -> ImpactReport:
    """Find call sites across the tree for symbols changed in the PR."""
    api = await collect_pr_diff(client, repo, pr_id)
    all_diff = "\n".join(f.diff or "" for f in api.files)
    symbols = changed_symbols(all_diff)

    wt = await worktrees.ensure(repo, source_branch)
    report = ImpactReport(symbols=symbols)
    for sym in symbols[:50]:  # bound the work
        report.references[sym] = await search_code(wt.path, rf"\b{re.escape(sym)}\b", max_results=50)
    return report


@dataclass
class RegressionResult:
    test_command: str
    base_exit_code: int
    pr_exit_code: int
    regressed: bool
    base_output: str
    pr_output: str


async def run_tests_base_vs_pr(
    client: BitbucketClient,
    worktrees: WorktreeManager,
    repo: str,
    pr_id: int,
    test_command: str,
    *,
    timeout: int = 1800,
) -> RegressionResult:
    """Run the test command on the merge base and on the PR head, and compare.

    `regressed` is True when tests pass on the base but fail on the PR — the
    clearest signal that the change introduced a regression.
    """
    pr = await client.get_pull_request(repo, pr_id)
    source = (pr.get("source") or {}).get("branch", {}).get("name")
    dest = (pr.get("destination") or {}).get("branch", {}).get("name")

    base_sha = await worktrees.merge_base_sha(repo, source, dest)
    base_wt = await worktrees.create_at(repo, base_sha, f"base-{pr_id}")
    pr_wt = await worktrees.create(repo, source)

    base_res = await run_command(base_wt.path, test_command, timeout=timeout)
    pr_res = await run_command(pr_wt.path, test_command, timeout=timeout)

    regressed = base_res.exit_code == 0 and pr_res.exit_code != 0
    return RegressionResult(
        test_command=test_command,
        base_exit_code=base_res.exit_code,
        pr_exit_code=pr_res.exit_code,
        regressed=regressed,
        base_output=_cap(base_res.stdout + "\n" + base_res.stderr),
        pr_output=_cap(pr_res.stdout + "\n" + pr_res.stderr),
    )
