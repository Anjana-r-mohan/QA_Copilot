"""Settings for PR Test Generator.

Credential loading precedence:
1. Environment variables (highest priority)
2. File specified by BITBUCKET_MCP_ENV_FILE
3. .env file found by walking up from the current working directory

Startup validation terminates the process if required credentials are missing.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from dotenv import find_dotenv, load_dotenv


@dataclass(frozen=True)
class Settings:
    """Application settings loaded from environment."""

    email: str
    api_token: str
    output_dir: Path
    bugzilla_api_key: str = ""

    @property
    def basic_auth(self) -> tuple[str, str]:
        """HTTP Basic Auth credentials tuple for Bitbucket API."""
        return (self.email, self.api_token)


def _load_env_file() -> None:
    """Load environment variables from a .env file.

    Resolution order:
    1. BITBUCKET_MCP_ENV_FILE — explicit absolute path to an env file.
    2. Walk up from cwd looking for a .env file (find_dotenv with usecwd=True).

    Existing environment variables always take precedence (override=False).
    """
    explicit = os.environ.get("BITBUCKET_MCP_ENV_FILE")
    if explicit:
        path = Path(explicit)
        if path.is_file():
            load_dotenv(str(path), override=True)
        return

    found = find_dotenv(usecwd=True)
    if found:
        load_dotenv(found, override=True)


def _validate_credentials() -> tuple[str, str]:
    """Validate that required credentials are present.

    Returns:
        Tuple of (email, api_token).

    Raises:
        SystemExit: If either credential is missing or empty.
    """
    email = os.environ.get("BITBUCKET_EMAIL", "").strip()
    api_token = os.environ.get("BITBUCKET_API_TOKEN", "").strip()

    missing: list[str] = []
    if not email:
        missing.append("BITBUCKET_EMAIL")
    if not api_token:
        missing.append("BITBUCKET_API_TOKEN")

    if missing:
        vars_str = ", ".join(missing)
        print(
            f"ERROR: Missing required credentials: {vars_str}\n"
            f"\n"
            f"To configure credentials:\n"
            f"  1. Set environment variables BITBUCKET_EMAIL and BITBUCKET_API_TOKEN, or\n"
            f"  2. Set BITBUCKET_MCP_ENV_FILE to point to an env file containing them, or\n"
            f"  3. Create a .env file in this directory or any parent directory.\n"
            f"\n"
            f"BITBUCKET_EMAIL: Your Atlassian account email address.\n"
            f"BITBUCKET_API_TOKEN: A scoped API token from\n"
            f"  https://id.atlassian.com/manage-profile/security/api-tokens",
            file=sys.stderr,
        )
        sys.exit(1)

    return email, api_token


def load_settings() -> Settings:
    """Load and validate application settings.

    Loads .env file (if available), validates credentials, and returns
    a frozen Settings instance. Terminates the process if credentials
    are missing.
    """
    _load_env_file()

    email, api_token = _validate_credentials()

    output_dir = Path(os.environ.get("OUTPUT_DIR", "./output"))
    bugzilla_api_key = os.environ.get("BUGZILLA_API_KEY", "").strip()

    return Settings(
        email=email,
        api_token=api_token,
        output_dir=output_dir,
        bugzilla_api_key=bugzilla_api_key,
    )
