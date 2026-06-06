"""Unit tests for TestGenerator Markdown rendering and output file writing."""

import os
from pathlib import Path

import pytest

from models import TestCase
from pr_test_generator.test_generator import TestGenerator


@pytest.fixture
def generator() -> TestGenerator:
    """Create a fresh TestGenerator instance."""
    return TestGenerator()


@pytest.fixture
def sample_metadata() -> dict:
    """Sample PR metadata for rendering tests."""
    return {
        "pr_link": "https://bitbucket.org/workspace/my-repo/pull-requests/42",
        "source_branch": "feature/login-ui",
        "destination_branch": "develop",
        "changed_file_count": 5,
        "repo_slug": "my-repo",
        "pr_id": 42,
    }


@pytest.fixture
def sample_test_cases() -> list[TestCase]:
    """Sample test cases for rendering."""
    return [
        TestCase(
            id="TC-1",
            title="Verify Android Resource ID 'btn_submit' is visible on screen load",
            preconditions=[
                "Application is installed and launched",
                "Screen containing the button is accessible",
            ],
            steps=[
                "1. Launch the application",
                "2. Navigate to the login screen",
                "3. Verify the submit button is displayed",
            ],
            expected_results=[
                "The element 'btn_submit' is visible on the screen",
                "The element renders without visual defects",
            ],
            source_file="app/src/main/java/LoginActivity.kt",
            trigger="Android Resource ID: btn_submit",
        ),
        TestCase(
            id="TC-2",
            title="Verify user interaction with Android Resource ID 'btn_submit'",
            preconditions=[
                "Application is installed and launched",
                "Element 'btn_submit' is visible on the screen",
            ],
            steps=[
                "1. Locate the element identified by 'btn_submit'",
                "2. Perform a tap/click action on the element",
                "3. Observe the application response",
            ],
            expected_results=[
                "The element responds to user interaction",
                "The expected action or state change occurs",
            ],
            source_file="app/src/main/java/LoginActivity.kt",
            trigger="Android Resource ID: btn_submit",
        ),
        TestCase(
            id="TC-3",
            title="Verify forward navigation: Navigate to dashboard",
            preconditions=[
                "Application is installed and launched",
                "User is on the source screen",
            ],
            steps=[
                "1. Identify the navigation trigger on the source screen",
                "2. Perform the action that triggers navigation",
                "3. Wait for the destination screen to load",
                "4. Verify the correct destination screen is displayed",
            ],
            expected_results=[
                "Navigation to the target destination completes successfully",
                "The destination screen is displayed with correct content",
            ],
            source_file="app/src/main/java/NavigationGraph.kt",
            trigger="Navigate to dashboard",
        ),
    ]


class TestRenderMarkdown:
    """Tests for render_markdown() method."""

    def test_renders_title_with_repo_and_pr_id(
        self, generator: TestGenerator, sample_test_cases: list[TestCase], sample_metadata: dict
    ):
        result = generator.render_markdown(sample_test_cases, sample_metadata)
        assert "# Test Cases: my-repo-PR42" in result

    def test_renders_metadata_table(
        self, generator: TestGenerator, sample_test_cases: list[TestCase], sample_metadata: dict
    ):
        result = generator.render_markdown(sample_test_cases, sample_metadata)
        assert "## Metadata" in result
        assert "| PR Link | https://bitbucket.org/workspace/my-repo/pull-requests/42 |" in result
        assert "| Source Branch | feature/login-ui |" in result
        assert "| Destination Branch | develop |" in result
        assert "| Changed Files | 5 |" in result

    def test_renders_iso8601_timestamp(
        self, generator: TestGenerator, sample_test_cases: list[TestCase], sample_metadata: dict
    ):
        result = generator.render_markdown(sample_test_cases, sample_metadata)
        # Should contain a UTC timestamp in ISO 8601 format
        assert "| Generated |" in result
        # Check format matches YYYY-MM-DDTHH:MM:SSZ
        lines = result.split("\n")
        generated_line = [l for l in lines if "| Generated |" in l][0]
        # Extract the timestamp value
        parts = generated_line.split("|")
        timestamp_str = parts[2].strip()
        assert timestamp_str.endswith("Z")
        assert "T" in timestamp_str

    def test_renders_summary_section(
        self, generator: TestGenerator, sample_test_cases: list[TestCase], sample_metadata: dict
    ):
        result = generator.render_markdown(sample_test_cases, sample_metadata)
        assert "## Summary" in result
        assert "- Total test cases: 3" in result
        assert "- Files analyzed: 2" in result

    def test_renders_test_cases_by_file(
        self, generator: TestGenerator, sample_test_cases: list[TestCase], sample_metadata: dict
    ):
        result = generator.render_markdown(sample_test_cases, sample_metadata)
        assert "## Test Cases by File" in result
        assert "### app/src/main/java/LoginActivity.kt" in result
        assert "### app/src/main/java/NavigationGraph.kt" in result

    def test_renders_test_case_structure(
        self, generator: TestGenerator, sample_test_cases: list[TestCase], sample_metadata: dict
    ):
        result = generator.render_markdown(sample_test_cases, sample_metadata)
        assert "#### TC-1:" in result
        assert "**Preconditions:**" in result
        assert "**Steps:**" in result
        assert "**Expected Results:**" in result
        assert "**Source:**" in result
        assert "---" in result

    def test_no_testable_changes_produces_summary_only(
        self, generator: TestGenerator, sample_metadata: dict
    ):
        result = generator.render_markdown([], sample_metadata)
        assert "# Test Cases: my-repo-PR42" in result
        assert "## Metadata" in result
        assert "## Summary" in result
        assert "- Total test cases: 0" in result
        assert "No testable UI changes were found in this pull request." in result
        assert "## Test Cases by File" not in result

    def test_locator_count_classification(self, generator: TestGenerator, sample_metadata: dict):
        """Test that locator-triggered test cases are counted correctly."""
        test_cases = [
            TestCase(
                id="TC-1",
                title="Verify element is visible",
                preconditions=[],
                steps=[],
                expected_results=[],
                source_file="file.kt",
                trigger="Android Resource ID: btn_ok",
            ),
            TestCase(
                id="TC-2",
                title="Verify element no longer present (removed)",
                preconditions=[],
                steps=[],
                expected_results=[],
                source_file="file.kt",
                trigger="Compose Test Tag: old_tag",
            ),
        ]
        result = generator.render_markdown(test_cases, sample_metadata)
        assert "- Locators detected: 2" in result

    def test_pattern_count(self, generator: TestGenerator, sample_metadata: dict):
        """Test that pattern-triggered test cases are counted."""
        test_cases = [
            TestCase(
                id="TC-1",
                title="Verify forward navigation",
                preconditions=[],
                steps=[],
                expected_results=[],
                source_file="file.kt",
                trigger="Navigate to dashboard",
            ),
        ]
        result = generator.render_markdown(test_cases, sample_metadata)
        assert "- Patterns detected: 1" in result


class TestWriteOutput:
    """Tests for write_output() method."""

    def test_writes_file_with_correct_name(
        self, generator: TestGenerator, tmp_path: Path
    ):
        content = "# Test Cases\nSample content"
        result_path = generator.write_output(content, "my-repo", 42, tmp_path)
        assert result_path.name == "my-repo-PR42-test-cases.md"
        assert result_path.exists()
        assert result_path.read_text(encoding="utf-8") == content

    def test_creates_output_directory(self, generator: TestGenerator, tmp_path: Path):
        nested_dir = tmp_path / "deep" / "nested" / "output"
        content = "# Test Cases"
        result_path = generator.write_output(content, "repo", 1, nested_dir)
        assert result_path.exists()
        assert nested_dir.exists()

    def test_default_output_dir(self, generator: TestGenerator, tmp_path: Path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        content = "# Test Cases"
        result_path = generator.write_output(content, "repo", 5)
        assert result_path == Path("./output") / "repo-PR5-test-cases.md"
        assert result_path.exists()

    def test_overwrites_existing_file(self, generator: TestGenerator, tmp_path: Path):
        content_v1 = "# Version 1"
        content_v2 = "# Version 2"
        generator.write_output(content_v1, "repo", 10, tmp_path)
        result_path = generator.write_output(content_v2, "repo", 10, tmp_path)
        assert result_path.read_text(encoding="utf-8") == content_v2

    def test_raises_oserror_for_invalid_directory(self, generator: TestGenerator):
        # Use /dev/null as parent which can't contain directories
        with pytest.raises(OSError, match="Cannot create output directory"):
            generator.write_output("content", "repo", 1, Path("/dev/null/impossible"))

    def test_accepts_string_output_dir(self, generator: TestGenerator, tmp_path: Path):
        content = "# Test Cases"
        result_path = generator.write_output(content, "repo", 7, str(tmp_path))
        assert result_path.exists()
        assert result_path.name == "repo-PR7-test-cases.md"
