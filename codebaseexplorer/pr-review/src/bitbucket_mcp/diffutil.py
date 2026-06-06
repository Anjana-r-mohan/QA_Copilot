"""Large-diff handling.

Bitbucket caps diffs (per file: 2000 lines / 100 KB; whole diff: 8000 lines;
200 files). For a robust review we never rely on the single whole-PR diff call.
Instead we enumerate files via diffstat, then fetch each file's diff on its own.
Files that exceed the per-file cap are flagged so the caller can diff them
locally in a worktree or skip binaries.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from typing import Any

from .client import MAX_FILE_DIFF_BYTES, MAX_FILE_DIFF_LINES, BitbucketClient

# Concurrent per-file diff fetches. Bounded so big PRs don't hammer the API into
# rate limits; tune against Bitbucket's limits if needed.
_DIFF_CONCURRENCY = 6

_HUNK_RE = re.compile(r"@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")


def parse_added_lines(diff_text: str) -> dict[str, list[int]]:
    """Map each file to the new-side line numbers that were added ('+').

    These are the safe anchor points for an inline comment (`inline.to`),
    because they exist in the destination file shown in the PR. Works on both
    the Bitbucket API diff and a local merge-base diff, since both use standard
    unified-diff hunk headers.
    """
    result: dict[str, list[int]] = {}
    current: str | None = None
    new_ln = 0
    for line in diff_text.splitlines():
        if line.startswith("+++ "):
            path = line[4:].strip()
            if path.startswith("b/"):
                path = path[2:]
            current = None if path == "/dev/null" else path
            if current is not None:
                result.setdefault(current, [])
        elif line.startswith("@@"):
            m = _HUNK_RE.search(line)
            new_ln = int(m.group(1)) if m else 0
        elif current is None:
            continue
        elif line.startswith("+") and not line.startswith("+++"):
            result[current].append(new_ln)
            new_ln += 1
        elif line.startswith("-") and not line.startswith("---"):
            continue  # removed line: advances old side only
        elif line.startswith("\\"):
            continue  # "\ No newline at end of file"
        else:  # context line
            new_ln += 1
    return result


@dataclass
class FileDiff:
    path: str
    status: str  # added / modified / removed / renamed
    lines_added: int
    lines_removed: int
    diff: str | None = None  # None when oversized/binary -> use local fallback
    oversized: bool = False
    binary: bool = False
    note: str = ""


@dataclass
class PrDiff:
    files: list[FileDiff] = field(default_factory=list)
    truncated_files: list[str] = field(default_factory=list)  # need local diffing


def _diffstat_path(entry: dict[str, Any]) -> str | None:
    new = entry.get("new") or {}
    old = entry.get("old") or {}
    return new.get("path") or old.get("path")


async def collect_pr_diff(
    client: BitbucketClient,
    repo: str,
    pr_id: int,
    *,
    context: int = 3,
    per_file_byte_cap: int = MAX_FILE_DIFF_BYTES,
    concurrency: int = _DIFF_CONCURRENCY,
) -> PrDiff:
    """Fetch a PR's diff file-by-file, flagging anything over the cap.

    Per-file diffs are fetched concurrently behind a semaphore so a large PR
    isn't a long chain of serial round-trips. File order is preserved.
    """
    stats = await client.list_pull_request_files(repo, pr_id)
    sem = asyncio.Semaphore(concurrency)

    async def fetch_one(entry: dict[str, Any]) -> FileDiff | None:
        path = _diffstat_path(entry)
        if not path:
            return None
        added = entry.get("lines_added") or 0
        removed = entry.get("lines_removed") or 0
        fd = FileDiff(
            path=path,
            status=entry.get("status", "modified"),
            lines_added=added,
            lines_removed=removed,
        )

        # Predict oversize from diffstat before spending a request.
        if added + removed > MAX_FILE_DIFF_LINES:
            fd.oversized = True
            fd.note = f"{added + removed} changed lines exceeds {MAX_FILE_DIFF_LINES}; diff locally"
            return fd

        try:
            async with sem:
                text = await client.get_pull_request_diff(
                    repo, pr_id, path=path, context=context
                )
        except Exception as exc:  # noqa: BLE001 - record and continue
            fd.note = f"diff fetch failed: {exc}"
            return fd

        if "Binary files" in text and "differ" in text:
            fd.binary = True
            fd.note = "binary file"
        elif len(text.encode("utf-8")) > per_file_byte_cap:
            fd.oversized = True
            fd.note = f"diff over {per_file_byte_cap} bytes; diff locally"
        else:
            fd.diff = text
        return fd

    fds = await asyncio.gather(*(fetch_one(e) for e in stats))

    result = PrDiff()
    for fd in fds:
        if fd is None:
            continue
        result.files.append(fd)
        if fd.diff is None and not fd.binary:
            result.truncated_files.append(fd.path)
    return result
