"""End-to-end integration tests for the PR analysis pipeline.

Tests the full pipeline from PRAnalyzer.analyze() through to output file
generation, using mocked Bitbucket API responses. Verifies:
- Output filename matches {repo_slug}-PR{pr_id}-test-cases.md
- Metadata header contains PR link, branches, changed file count
- Test cases are grouped by file
- Test case IDs are sequential (TC-1, TC-2, ...)

Validates: Requirements 8.2, 8.5, 7.2, 7.3
"""

from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from pr_test_generator.analyzer import PRAnalyzer
from pr_test_generator.bitbucket_client import BitbucketClient
from pr_test_generator.settings import Settings


# --- Mock API Response Data ---

_WORKSPACE = "my-team"
_REPO_SLUG = "mobile-app"
_PR_ID = 123
_PR_LINK = f"https://bitbucket.org/{_WORKSPACE}/{_REPO_SLUG}/pull-requests/{_PR_ID}"

_HEAD_COMMIT = "abc123def456"
_BASE_COMMIT = "789xyz000111"

_PR_METADATA_RESPONSE = {
    "title": "Add login screen with test tags",
    "author": {"display_name": "Jane Developer"},
    "source": {
        "branch": {"name": "feature/login-screen"},
        "commit": {"hash": _HEAD_COMMIT},
    },
    "destination": {
        "branch": {"name": "develop"},
        "commit": {"hash": _BASE_COMMIT},
    },
}

_DIFFSTAT_RESPONSE = {
    "values": [
        {
            "status": "added",
            "new": {"path": "app/src/main/java/com/example/LoginScreen.kt"},
            "old": None,
        },
        {
            "status": "modified",
            "new": {"path": "app/src/main/java/com/example/HomeScreen.kt"},
            "old": {"path": "app/src/main/java/com/example/HomeScreen.kt"},
        },
    ],
    "next": None,
}

# File content for the added file — contains Compose testTag and R.id locators
_LOGIN_SCREEN_CONTENT = """\
package com.example

import androidx.compose.ui.Modifier
import androidx.compose.ui.test.testTag

class LoginScreen {
    fun render() {
        val emailField = R.id.email_input
        Button(
            modifier = Modifier.testTag("login_button"),
            onClick = { performLogin() }
        ) {
            Text("Login")
        }
        TextField(
            modifier = Modifier.testTag("password_field"),
            contentDescription = "Enter your password"
        )
    }
}
"""

# File content for the modified file — head version has a navigation call added
_HOME_SCREEN_HEAD_CONTENT = """\
package com.example

class HomeScreen {
    fun render() {
        val title = R.id.home_title
        Button(onClick = { navigate("settings") }) {
            Text("Settings")
        }
    }
}
"""

# File content for the modified file — base version without navigation
_HOME_SCREEN_BASE_CONTENT = """\
package com.example

class HomeScreen {
    fun render() {
        val title = R.id.home_title
        Text("Welcome Home")
    }
}
"""


# --- Fixtures ---


@pytest.fixture
def mock_settings(tmp_path: Path) -> Settings:
    """Create Settings pointing to a temporary output directory."""
    return Settings(
        email="test@example.com",
        api_token="fake-token",
        output_dir=tmp_path / "output",
    )


@pytest.fixture
def mock_client(mock_settings: Settings) -> BitbucketClient:
    """Create a BitbucketClient with mocked request method."""
    client = BitbucketClient(mock_settings)
    return client


def _build_mock_request(workspace: str, repo_slug: str, pr_id: int):
    """Build an async mock that routes API paths to canned responses."""

    async def mock_request(method: str, url: str, **kwargs) -> httpx.Response:
        """Route mocked API calls to canned responses based on URL path."""
        # PR metadata endpoint
        if url == f"/repositories/{workspace}/{repo_slug}/pullrequests/{pr_id}":
            return httpx.Response(
                status_code=200,
                json=_PR_METADATA_RESPONSE,
            )

        # Diffstat endpoint
        if url == f"/repositories/{workspace}/{repo_slug}/pullrequests/{pr_id}/diffstat":
            return httpx.Response(
                status_code=200,
                json=_DIFFSTAT_RESPONSE,
            )

        # File content at head commit — LoginScreen.kt (added file)
        if (
            url
            == f"/repositories/{workspace}/{repo_slug}/src/{_HEAD_COMMIT}/app/src/main/java/com/example/LoginScreen.kt"
        ):
            return httpx.Response(
                status_code=200,
                text=_LOGIN_SCREEN_CONTENT,
                headers={"content-type": "text/plain"},
            )

        # File content at head commit — HomeScreen.kt (modified file)
        if (
            url
            == f"/repositories/{workspace}/{repo_slug}/src/{_HEAD_COMMIT}/app/src/main/java/com/example/HomeScreen.kt"
        ):
            return httpx.Response(
                status_code=200,
                text=_HOME_SCREEN_HEAD_CONTENT,
                headers={"content-type": "text/plain"},
            )

        # File content at base commit — HomeScreen.kt (modified file, base version)
        if (
            url
            == f"/repositories/{workspace}/{repo_slug}/src/{_BASE_COMMIT}/app/src/main/java/com/example/HomeScreen.kt"
        ):
            return httpx.Response(
                status_code=200,
                text=_HOME_SCREEN_BASE_CONTENT,
                headers={"content-type": "text/plain"},
            )

        # File content at base commit — LoginScreen.kt doesn't exist at base (added file)
        if (
            url
            == f"/repositories/{workspace}/{repo_slug}/src/{_BASE_COMMIT}/app/src/main/java/com/example/LoginScreen.kt"
        ):
            # DiffExtractor sets base_content = "" for added files; this shouldn't be called
            # but if it is, return 404
            from pr_test_generator.bitbucket_client import BitbucketClientError

            raise BitbucketClientError(
                "File not found", status_code=404, url=url
            )

        # Default: unexpected URL
        raise AssertionError(f"Unexpected API call: {method} {url}")

    return mock_request


# --- End-to-End Tests ---


class TestEndToEndPipeline:
    """End-to-end tests exercising the full analysis pipeline with mocked API."""

    async def test_analyze_produces_correct_output_filename(
        self, mock_client: BitbucketClient, mock_settings: Settings
    ):
        """Output file should match the pattern {repo_slug}-PR{pr_id}-test-cases.md.

        Validates: Requirements 8.2
        """
        mock_client.request = AsyncMock(
            side_effect=_build_mock_request(_WORKSPACE, _REPO_SLUG, _PR_ID)
        )
        analyzer = PRAnalyzer(mock_client, mock_settings)

        output_path = await analyzer.analyze(_PR_LINK)

        expected_filename = f"{_REPO_SLUG}-PR{_PR_ID}-test-cases.md"
        assert output_path.name == expected_filename
        assert output_path.exists()

    async def test_analyze_output_contains_metadata_header(
        self, mock_client: BitbucketClient, mock_settings: Settings
    ):
        """Output file should contain metadata header with PR link, branches, changed file count.

        Validates: Requirements 8.5
        """
        mock_client.request = AsyncMock(
            side_effect=_build_mock_request(_WORKSPACE, _REPO_SLUG, _PR_ID)
        )
        analyzer = PRAnalyzer(mock_client, mock_settings)

        output_path = await analyzer.analyze(_PR_LINK)
        content = output_path.read_text(encoding="utf-8")

        # Check metadata header contains required fields
        assert "## Metadata" in content
        assert _PR_LINK in content
        assert "feature/login-screen" in content  # source branch
        assert "develop" in content  # destination branch
        assert "| Changed Files |" in content

        # Verify the changed file count is 2
        assert "| Changed Files | 2 |" in content

        # Verify ISO 8601 timestamp is present (pattern: YYYY-MM-DDTHH:MM:SSZ)
        iso_pattern = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")
        assert iso_pattern.search(content) is not None

    async def test_analyze_output_has_test_cases_grouped_by_file(
        self, mock_client: BitbucketClient, mock_settings: Settings
    ):
        """Test cases should be grouped by source file path with no interleaving.

        Validates: Requirements 7.2
        """
        mock_client.request = AsyncMock(
            side_effect=_build_mock_request(_WORKSPACE, _REPO_SLUG, _PR_ID)
        )
        analyzer = PRAnalyzer(mock_client, mock_settings)

        output_path = await analyzer.analyze(_PR_LINK)
        content = output_path.read_text(encoding="utf-8")

        # Verify test cases are grouped under file headings (### path)
        assert "## Test Cases by File" in content

        # Extract file section headers
        file_sections = re.findall(r"^### (.+)$", content, re.MULTILINE)
        assert len(file_sections) >= 2  # at least 2 files

        # Verify each file only appears once (contiguous grouping)
        seen_files = set()
        for section in file_sections:
            assert section not in seen_files, f"File {section} appears more than once"
            seen_files.add(section)

    async def test_analyze_output_has_sequential_test_case_ids(
        self, mock_client: BitbucketClient, mock_settings: Settings
    ):
        """Test case IDs should be sequential: TC-1, TC-2, TC-3, etc.

        Validates: Requirements 7.3
        """
        mock_client.request = AsyncMock(
            side_effect=_build_mock_request(_WORKSPACE, _REPO_SLUG, _PR_ID)
        )
        analyzer = PRAnalyzer(mock_client, mock_settings)

        output_path = await analyzer.analyze(_PR_LINK)
        content = output_path.read_text(encoding="utf-8")

        # Extract all TC-{n} IDs from the output
        tc_ids = re.findall(r"TC-(\d+)", content)
        assert len(tc_ids) > 0, "No test case IDs found in output"

        # Convert to integers and verify sequential ordering starting from 1
        tc_numbers = [int(n) for n in tc_ids]
        # Each ID appears multiple times (in header and in body), get unique ordered
        unique_ids = list(dict.fromkeys(tc_numbers))
        expected = list(range(1, len(unique_ids) + 1))
        assert unique_ids == expected

    async def test_analyze_output_test_cases_have_required_structure(
        self, mock_client: BitbucketClient, mock_settings: Settings
    ):
        """Each test case should have preconditions, steps, and expected results.

        Validates: Requirements 7.3
        """
        mock_client.request = AsyncMock(
            side_effect=_build_mock_request(_WORKSPACE, _REPO_SLUG, _PR_ID)
        )
        analyzer = PRAnalyzer(mock_client, mock_settings)

        output_path = await analyzer.analyze(_PR_LINK)
        content = output_path.read_text(encoding="utf-8")

        # Split into test case blocks by the separator
        tc_blocks = content.split("---")

        # Find blocks that contain TC- identifiers (actual test cases)
        test_case_blocks = [b for b in tc_blocks if "#### TC-" in b]
        assert len(test_case_blocks) > 0, "No test case blocks found"

        for block in test_case_blocks:
            assert "**Preconditions:**" in block, f"Missing preconditions in: {block[:80]}"
            assert "**Steps:**" in block, f"Missing steps in: {block[:80]}"
            assert "**Expected Results:**" in block, f"Missing expected results in: {block[:80]}"
            assert "**Source:**" in block, f"Missing source in: {block[:80]}"

    async def test_analyze_detects_locators_from_mock_content(
        self, mock_client: BitbucketClient, mock_settings: Settings
    ):
        """Pipeline should detect locators from the mocked file content.

        The mock LoginScreen.kt contains:
        - R.id.email_input (Android resource ID)
        - Modifier.testTag("login_button") (Compose test tag)
        - Modifier.testTag("password_field") (Compose test tag)
        - contentDescription = "Enter your password" (content description)

        These should all generate test cases in the output.
        """
        mock_client.request = AsyncMock(
            side_effect=_build_mock_request(_WORKSPACE, _REPO_SLUG, _PR_ID)
        )
        analyzer = PRAnalyzer(mock_client, mock_settings)

        output_path = await analyzer.analyze(_PR_LINK)
        content = output_path.read_text(encoding="utf-8")

        # Verify locators from LoginScreen.kt are detected
        assert "login_button" in content
        assert "password_field" in content
        assert "email_input" in content

    async def test_analyze_detects_patterns_from_mock_content(
        self, mock_client: BitbucketClient, mock_settings: Settings
    ):
        """Pipeline should detect code patterns (navigation, input) from mock content.

        HomeScreen.kt head has navigate("settings") and onClick which are
        not in the base version — these should be detected as added patterns.
        """
        mock_client.request = AsyncMock(
            side_effect=_build_mock_request(_WORKSPACE, _REPO_SLUG, _PR_ID)
        )
        analyzer = PRAnalyzer(mock_client, mock_settings)

        output_path = await analyzer.analyze(_PR_LINK)
        content = output_path.read_text(encoding="utf-8")

        # Verify navigation pattern generates test cases
        # The navigate("settings") should trigger navigation tests
        assert "navigation" in content.lower() or "navigate" in content.lower()

    async def test_analyze_output_written_to_settings_output_dir(
        self, mock_client: BitbucketClient, mock_settings: Settings
    ):
        """Output file should be written to the configured output directory."""
        mock_client.request = AsyncMock(
            side_effect=_build_mock_request(_WORKSPACE, _REPO_SLUG, _PR_ID)
        )
        analyzer = PRAnalyzer(mock_client, mock_settings)

        output_path = await analyzer.analyze(_PR_LINK)

        # Verify it's in the configured output directory
        assert str(output_path).startswith(str(mock_settings.output_dir))
        assert output_path.parent == mock_settings.output_dir

    async def test_analyze_multiple_locators_from_same_file_grouped(
        self, mock_client: BitbucketClient, mock_settings: Settings
    ):
        """All test cases from the same source file should be contiguous.

        Validates: Requirements 7.2
        """
        mock_client.request = AsyncMock(
            side_effect=_build_mock_request(_WORKSPACE, _REPO_SLUG, _PR_ID)
        )
        analyzer = PRAnalyzer(mock_client, mock_settings)

        output_path = await analyzer.analyze(_PR_LINK)
        content = output_path.read_text(encoding="utf-8")

        # Extract all (TC-id, source_file) pairs from the output
        # Each test case block starts with #### TC-{n}: and ends with **Source:**
        tc_sections = re.findall(
            r"#### (TC-\d+):.*?(?=#### TC-|\Z)", content, re.DOTALL
        )

        # Track which file section each test case falls under
        current_file = None
        file_sequence: list[str] = []

        for line in content.splitlines():
            if line.startswith("### ") and "Test Cases by File" not in line:
                current_file = line[4:].strip()
            elif line.startswith("#### TC-") and current_file:
                file_sequence.append(current_file)

        # Check for contiguous grouping: once we leave a file, we don't return
        if file_sequence:
            seen_files: set[str] = set()
            last_file: str | None = None
            for f in file_sequence:
                if f != last_file:
                    assert f not in seen_files, (
                        f"File '{f}' appears non-contiguously in test case sequence"
                    )
                    seen_files.add(f)
                    last_file = f
