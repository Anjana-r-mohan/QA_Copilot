"""Git worktree management for reviewing PR branches against local code.

Multi-repo aware: each repo slug maps to a local clone (provided via
BITBUCKET_REPO_PATHS, or cloned on demand under BITBUCKET_REPOS_ROOT using the
configured token). A worktree checks the PR branch out into an isolated dir so a
review agent can read files, resolve dependencies, grep, and build the exact PR
code without disturbing the main clone.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
from collections import defaultdict
from dataclasses import dataclass

from .config import Settings

log = logging.getLogger("bitbucket_mcp.worktree")


class GitError(RuntimeError):
    pass


def _safe_slug(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "-", name)


@dataclass
class Worktree:
    repo: str
    branch: str
    path: str


# Subprocess env that forbids git from prompting or invoking credential helpers.
# Without these, a failed auth header silently falls through to the user's global
# helper (osxkeychain / libsecret), which then prompts on the MCP client's tty.
_NO_PROMPT_ENV = {
    **os.environ,
    "GIT_TERMINAL_PROMPT": "0",  # never prompt for username/password
    "GCM_INTERACTIVE": "Never",  # Git Credential Manager: non-interactive
    "GIT_ASKPASS": "/bin/echo",  # neutralise any inherited GIT_ASKPASS helper
    "SSH_ASKPASS": "/bin/echo",
}

# git -c options to disable credential helpers for one invocation. Applied to
# network calls so a stale/insufficient auth header surfaces as a clean error
# instead of silently falling through to the OS keychain.
_NO_HELPER_CONFIG = [
    "-c",
    "credential.helper=",  # clear inherited helpers (osxkeychain etc.)
    "-c",
    "credential.interactive=false",
]


async def _git(cwd: str, *args: str, config: list[str] | None = None) -> str:
    """Run git in `cwd`. `config` injects `-c key=val` pairs *before* the
    subcommand — used to pass the auth header for network ops so the token never
    lands in `.git/config`. Subprocess env disables interactive prompts so a bad
    token fails fast instead of hanging on stdin."""
    proc = await asyncio.create_subprocess_exec(
        "git",
        "-C",
        cwd,
        *(config or []),
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=_NO_PROMPT_ENV,
    )
    out, err = await proc.communicate()
    if proc.returncode != 0:
        raise GitError(
            f"git {' '.join(args)} failed ({proc.returncode}): "
            f"{err.decode(errors='replace').strip()}"
        )
    return out.decode(errors="replace").strip()


class WorktreeManager:
    def __init__(self, settings: Settings) -> None:
        self._s = settings
        # Per-repo locks serialize clone/fetch/worktree mutations so concurrent
        # tools on the same repo don't race on .git/index.lock or reset --hard.
        # Different repos still run in parallel.
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    def _lock(self, repo: str) -> asyncio.Lock:
        return self._locks[repo]

    async def _git_net(self, cwd: str, *args: str) -> str:
        """git network op (clone/fetch).

        HTTPS transport: injects `-c http.extraHeader=...` with the API token
        and disables credential helpers/prompts so a bad token raises a clear
        `GitError` instead of hanging on a tty prompt.

        SSH transport: relies on the user's SSH key (loaded ssh-agent or
        `~/.ssh/id_*`); no header injection, helpers irrelevant.
        """
        if self._s.git_transport == "ssh":
            return await _git(cwd, *args)
        config = [*self._s.git_auth_config(), *_NO_HELPER_CONFIG]
        return await _git(cwd, *args, config=config)

    async def _origin_matches(self, path: str, repo: str) -> bool:
        """True if the git repo at `path` has an origin pointing at this repo.

        Accepts either a regular clone (`.git` directory) or a submodule /
        secondary worktree (`.git` file containing a `gitdir:` pointer).
        """
        if not os.path.exists(os.path.join(path, ".git")):
            return False
        try:
            url = await _git(path, "remote", "get-url", "origin")
        except GitError:
            return False
        url = url.rstrip("/")
        if url.endswith(".git"):
            url = url[:-4]
        return url.endswith(f"/{self._s.workspace}/{repo}") or url.endswith(f":{self._s.workspace}/{repo}")

    async def _discover(self, repo: str) -> str | None:
        """Scan repos_root for an existing clone whose origin matches `repo`."""
        root = self._s.repos_root
        if not os.path.isdir(root):
            return None
        # Fast path: directory named after the slug.
        slug_dir = os.path.join(root, _safe_slug(repo))
        if await self._origin_matches(slug_dir, repo):
            return slug_dir
        # Otherwise match by remote URL (dir name may differ from slug).
        for name in sorted(os.listdir(root)):
            cand = os.path.join(root, name)
            if cand != slug_dir and await self._origin_matches(cand, repo):
                return cand
        return None

    async def _ensure_clone(self, repo: str) -> str:
        """Resolve a local clone path for `repo`.

        Order: explicit config map -> discovered clone under repos_root
        (matched by origin URL) -> clone on demand (if auto_clone). A full
        (non-shallow) clone is required so merge-base diffs have shared history.
        """
        # 1. Explicit path from config. Accept `.git` as a directory (regular
        # clone) or a file (submodule / linked worktree).
        configured = self._s.repo_paths.get(repo)
        if configured:
            if os.path.exists(os.path.join(configured, ".git")):
                return configured
            raise GitError(
                f"BITBUCKET_REPO_PATHS['{repo}'] = '{configured}' is not a git clone."
            )

        # 2. Discover an existing clone under repos_root.
        found = await self._discover(repo)
        if found:
            return found

        # 3. Clone on demand.
        if not self._s.auto_clone:
            raise GitError(
                f"No local clone for '{repo}'. Add it to BITBUCKET_REPO_PATHS, place a "
                f"clone under {self._s.repos_root}, or set BITBUCKET_AUTO_CLONE=true."
            )
        os.makedirs(self._s.repos_root, exist_ok=True)
        dest = os.path.join(self._s.repos_root, _safe_slug(repo))
        await self._git_net(self._s.repos_root, "clone", self._s.clone_url(repo), dest)
        return dest

    async def create(self, repo: str, branch: str, *, refresh: bool = True) -> Worktree:
        """Check `branch` out into a worktree.

        With `refresh=True` (default) the branch is fetched and the worktree is
        hard-reset to `origin/<branch>` — use when the PR may have new commits.
        With `refresh=False` an existing worktree is reused as-is (no network);
        read-only analysis tools use this to avoid redundant fetch + reset.
        """
        async with self._lock(repo):
            clone = await self._ensure_clone(repo)

            wt_dir = os.path.join(self._s.worktree_root, _safe_slug(repo))
            os.makedirs(wt_dir, exist_ok=True)
            dest = os.path.join(wt_dir, _safe_slug(branch))

            if os.path.exists(dest):
                if refresh:
                    await self._git_net(clone, "fetch", "origin", branch)
                    await _git(dest, "checkout", branch)
                    await _git(dest, "reset", "--hard", f"origin/{branch}")
                return Worktree(repo=repo, branch=branch, path=dest)

            await self._git_net(clone, "fetch", "origin", branch)
            await _git(clone, "worktree", "add", "--force", dest, branch)
            return Worktree(repo=repo, branch=branch, path=dest)

    async def ensure(self, repo: str, branch: str) -> Worktree:
        """Reuse an existing checkout without re-fetching; create it if absent."""
        return await self.create(repo, branch, refresh=False)

    async def create_at(self, repo: str, ref: str, label: str) -> Worktree:
        """Check out an arbitrary ref (e.g. a merge-base SHA) in a detached worktree.

        Used to build a 'base' tree for run-tests-base-vs-PR comparisons.
        """
        async with self._lock(repo):
            clone = await self._ensure_clone(repo)
            wt_dir = os.path.join(self._s.worktree_root, _safe_slug(repo))
            os.makedirs(wt_dir, exist_ok=True)
            dest = os.path.join(wt_dir, _safe_slug(label))
            if os.path.exists(dest):
                await _git(dest, "checkout", "--detach", ref)
                await _git(dest, "reset", "--hard", ref)
            else:
                await _git(clone, "worktree", "add", "--detach", "--force", dest, ref)
            return Worktree(repo=repo, branch=ref, path=dest)

    async def merge_base_sha(self, repo: str, source_branch: str, dest_branch: str) -> str:
        async with self._lock(repo):
            clone = await self._ensure_clone(repo)
            await self._git_net(clone, "fetch", "origin", source_branch, dest_branch)
            return await _git(
                clone, "merge-base", f"origin/{dest_branch}", f"origin/{source_branch}"
            )

    async def remove(self, repo: str, branch: str) -> None:
        async with self._lock(repo):
            clone = await self._ensure_clone(repo)
            dest = os.path.join(self._s.worktree_root, _safe_slug(repo), _safe_slug(branch))
            try:
                await _git(clone, "worktree", "remove", "--force", dest)
            except GitError:
                if os.path.isdir(dest):
                    shutil.rmtree(dest, ignore_errors=True)
                await _git(clone, "worktree", "prune")

    async def list(self, repo: str) -> str:
        clone = await self._ensure_clone(repo)
        return await _git(clone, "worktree", "list")

    async def merge_base_diff(
        self,
        repo: str,
        source_branch: str,
        dest_branch: str,
        *,
        path: str | None = None,
        context: int = 3,
    ) -> str:
        """Reproduce Bitbucket's PR diff locally with matching line numbers.

        Bitbucket shows a PR as changes relative to the *merge base* of source
        and destination, so `git diff <merge-base> origin/<source>` yields the
        same new-side line numbers the inline-comment API expects (`inline.to`).
        No size limit applies, so this is the fallback for oversized files.
        """
        async with self._lock(repo):
            clone = await self._ensure_clone(repo)
            await self._git_net(clone, "fetch", "origin", source_branch, dest_branch)
            try:
                base = await _git(
                    clone, "merge-base", f"origin/{dest_branch}", f"origin/{source_branch}"
                )
            except GitError:
                # Shallow clone may lack the common ancestor — deepen and retry.
                await self._git_net(
                    clone, "fetch", "--unshallow", "origin", source_branch, dest_branch
                )
                base = await _git(
                    clone, "merge-base", f"origin/{dest_branch}", f"origin/{source_branch}"
                )
            args = ["diff", f"--unified={context}", base, f"origin/{source_branch}"]
            if path:
                args += ["--", path]
            return await _git(clone, *args)
