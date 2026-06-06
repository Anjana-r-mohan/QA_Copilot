"""Configuration loaded from environment variables.

Auth: Atlassian **API token with scopes** (app passwords are deprecated and
removed in 2026). Basic auth using your Atlassian *email* (not the Bitbucket
username) + the API token.

    BITBUCKET_EMAIL=you@example.com
    BITBUCKET_API_TOKEN=<api-token>

Required scopes are listed in PERMISSIONS.md.
"""

from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass, field

from dotenv import find_dotenv, load_dotenv


@dataclass(frozen=True)
class Settings:
    base_url: str
    workspace: str

    # Auth: Atlassian API token (Basic auth).
    email: str  # Atlassian account email (Basic auth username)
    api_token: str  # scoped API token (Basic auth password)

    # Local clones for worktree-based review, keyed by repo slug.
    # If a slug is missing, it is cloned on demand under repos_root.
    repo_paths: dict[str, str] = field(default_factory=dict)
    repos_root: str = ""
    worktree_root: str = ""
    auto_clone: bool = True  # clone missing repos on demand (set False to require local clones)
    allow_exec: bool = False  # gate run_command (arbitrary shell); off by default
    log_level: str = "WARNING"
    # "https" (default): clone/fetch over HTTPS with the API token injected per-call.
    # "ssh": use the user's SSH key (bitbucket.org:22) for git ops. REST API still
    # uses the API token regardless.
    git_transport: str = "https"

    @property
    def basic_auth(self) -> tuple[str, str]:
        return (self.email, self.api_token)

    def auth_header(self) -> dict[str, str]:
        """No extra header — Basic auth is applied by httpx via `auth=`."""
        return {}

    def git_auth_header(self) -> str:
        """The `Authorization` header value git should send for clone/fetch
        over HTTPS. Empty when `git_transport == "ssh"` (SSH key carries auth).

        Returned so it can be injected per-invocation via `-c http.extraHeader`,
        keeping the credential out of `.git/config` on disk.
        """
        token = base64.b64encode(f"{self.email}:{self.api_token}".encode()).decode()
        return f"Basic {token}"

    def git_auth_config(self) -> list[str]:
        """`git -c ...` args carrying the auth header for network operations.
        Empty for SSH transport — the user's SSH key authenticates."""
        if self.git_transport == "ssh":
            return []
        return ["-c", f"http.extraHeader=Authorization: {self.git_auth_header()}"]

    def clone_url(self, repo: str) -> str:
        """Clone URL — HTTPS by default, SSH when `git_transport == "ssh"`.

        HTTPS path carries no embedded credentials; auth is injected per
        invocation via `git_auth_config()`. SSH path uses the user's key.
        """
        if self.git_transport == "ssh":
            return f"git@bitbucket.org:{self.workspace}/{repo}.git"
        return f"https://bitbucket.org/{self.workspace}/{repo}.git"


def _load_dotenv_if_present() -> None:
    """Load a `.env` file into os.environ so the MCP client doesn't have to
    embed secrets in its `env` block. Resolution order:

    1. `BITBUCKET_MCP_ENV_FILE` — explicit absolute path (lets the MCP config name
       the file without changing the spawned process's `cwd`).
    2. `find_dotenv(usecwd=True)` — walks up from the current working directory
       (useful when the MCP client sets `cwd` to the project root).

    Existing environment variables always win (`override=False`), so values set
    in the MCP `env` block still take precedence over the `.env` file.
    """
    explicit = os.environ.get("BITBUCKET_MCP_ENV_FILE")
    if explicit:
        load_dotenv(explicit, override=True)
        return
    found = find_dotenv(usecwd=True)
    if found:
        load_dotenv(found, override=True)


def load_settings() -> Settings:
    _load_dotenv_if_present()

    workspace = os.environ.get("BITBUCKET_WORKSPACE")
    if not workspace:
        raise RuntimeError("Missing required environment variable: BITBUCKET_WORKSPACE")

    email = os.environ.get("BITBUCKET_EMAIL")
    api_token = os.environ.get("BITBUCKET_API_TOKEN")

    if not (email and api_token):
        raise RuntimeError(
            "No credentials found. Set BITBUCKET_EMAIL (your Atlassian account "
            "email) and BITBUCKET_API_TOKEN (scoped API token from "
            "https://id.atlassian.com/manage-profile/security/api-tokens). "
            "See PERMISSIONS.md."
        )

    # Optional JSON map: {"repo-slug": "/abs/path/to/clone"}
    repo_paths: dict[str, str] = {}
    raw_map = os.environ.get("BITBUCKET_REPO_PATHS")
    if raw_map:
        repo_paths = json.loads(raw_map)

    repos_root = os.environ.get(
        "BITBUCKET_REPOS_ROOT", os.path.join(os.getcwd(), ".bitbucket-mcp-repos")
    )
    worktree_root = os.environ.get(
        "BITBUCKET_WORKTREE_ROOT", os.path.join(os.getcwd(), ".pr-worktrees")
    )

    def _flag(name: str, default: bool) -> bool:
        raw = os.environ.get(name)
        if raw is None:
            return default
        return raw.lower() not in ("0", "false", "no")

    git_transport = os.environ.get("BITBUCKET_GIT_TRANSPORT", "https").lower()
    if git_transport not in ("https", "ssh"):
        raise RuntimeError(
            f"BITBUCKET_GIT_TRANSPORT must be 'https' or 'ssh', got '{git_transport}'."
        )

    return Settings(
        base_url=os.environ.get("BITBUCKET_BASE_URL", "https://api.bitbucket.org/2.0"),
        workspace=workspace,
        email=email,
        api_token=api_token,
        repo_paths=repo_paths,
        repos_root=repos_root,
        worktree_root=worktree_root,
        auto_clone=_flag("BITBUCKET_AUTO_CLONE", True),
        allow_exec=_flag("BITBUCKET_ALLOW_EXEC", False),
        log_level=os.environ.get("LOG_LEVEL", "WARNING").upper(),
        git_transport=git_transport,
    )
