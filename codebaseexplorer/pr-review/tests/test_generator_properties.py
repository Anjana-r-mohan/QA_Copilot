"""Property-based tests for the TestGenerator module.

Uses Hypothesis to verify structural correctness properties of generated
test cases across randomly generated locator and pattern inputs.
"""

import re
import tempfile
from pathlib import Path

from hypothesis import given, strategies as st, settings

from models import (
    DetectedLocator,
    DetectedPattern,
    FileChange,
    FileChangeType,
    LocatorType,
    LocatorStatus,
    PatternType,
)
from pr_test_generator.test_generator import TestGenerator


# --- Strategies ---

locator_types = st.sampled_from(list(LocatorType))
locator_statuses = st.sampled_from(list(LocatorStatus))
pattern_types = st.sampled_from(list(PatternType))

# Values and descriptions: non-empty short strings
values = st.text(min_size=1, max_size=30)
descriptions = st.text(min_size=1, max_size=30)

# File paths: non-empty relative paths
file_paths = st.text(min_size=3, max_size=60).filter(lambda s: s.strip() == s and len(s) >= 3)

# Line numbers
line_numbers = st.integers(min_value=1, max_value=500)

# Strategy for DetectedLocator objects
detected_locators = st.builds(
    DetectedLocator,
    locator_type=locator_types,
    value=values,
    file_path=file_paths,
    line_number=line_numbers,
    status=locator_statuses,
)

# Strategy for DetectedPattern objects
detected_patterns = st.builds(
    DetectedPattern,
    pattern_type=pattern_types,
    description=descriptions,
    file_path=file_paths,
    line_number=line_numbers,
    status=locator_statuses,
)


# --- Property 9: Test Case Structural Completeness ---


# Regex for valid test case ID: TC- followed by a positive integer (no leading zeros except "0" itself, but we require positive)
TC_ID_PATTERN = re.compile(r"^TC-(\d+)$")


class TestTestCaseStructuralCompleteness:
    """Property 9: Test Case Structural Completeness.

    For any generated test case: ID matches TC-{positive_integer}, title is
    ≤120 characters and non-empty, preconditions has ≥1 entry, steps has ≥1
    entry, and expected_results has ≥1 entry.

    **Validates: Requirements 7.3**
    """

    @given(
        locators=st.lists(detected_locators, min_size=1, max_size=5),
        patterns=st.lists(detected_patterns, min_size=0, max_size=3),
    )
    @settings(max_examples=100)
    def test_structural_completeness_from_locators(
        self,
        locators: list,
        patterns: list,
    ):
        """For any non-empty set of locators and patterns, every generated test case
        satisfies structural completeness constraints.

        **Validates: Requirements 7.3**
        """
        generator = TestGenerator()
        test_cases = generator.generate(locators, patterns, pr_metadata={})

        # With at least 1 locator, we should get at least 1 test case
        assert len(test_cases) >= 1, (
            f"Expected at least 1 test case from {len(locators)} locators, got 0"
        )

        for tc in test_cases:
            # ID matches TC-{positive_integer}
            match = TC_ID_PATTERN.match(tc.id)
            assert match is not None, (
                f"Test case ID '{tc.id}' does not match pattern TC-{{positive_integer}}"
            )
            tc_number = int(match.group(1))
            assert tc_number > 0, (
                f"Test case ID number must be positive, got {tc_number}"
            )

            # Title is non-empty and ≤120 characters
            assert len(tc.title) > 0, (
                f"Test case '{tc.id}' has empty title"
            )
            assert len(tc.title) <= 120, (
                f"Test case '{tc.id}' title exceeds 120 chars: {len(tc.title)}"
            )

            # At least 1 precondition
            assert len(tc.preconditions) >= 1, (
                f"Test case '{tc.id}' has no preconditions"
            )

            # At least 1 step
            assert len(tc.steps) >= 1, (
                f"Test case '{tc.id}' has no steps"
            )

            # At least 1 expected result
            assert len(tc.expected_results) >= 1, (
                f"Test case '{tc.id}' has no expected results"
            )

    @given(
        locators=st.lists(detected_locators, min_size=0, max_size=3),
        patterns=st.lists(detected_patterns, min_size=1, max_size=5),
    )
    @settings(max_examples=100)
    def test_structural_completeness_from_patterns(
        self,
        locators: list,
        patterns: list,
    ):
        """For any non-empty set of patterns, every generated test case satisfies
        structural completeness constraints.

        **Validates: Requirements 7.3**
        """
        generator = TestGenerator()
        test_cases = generator.generate(locators, patterns, pr_metadata={})

        # With at least 1 pattern, we should get at least 1 test case
        assert len(test_cases) >= 1, (
            f"Expected at least 1 test case from {len(patterns)} patterns, got 0"
        )

        for tc in test_cases:
            # ID matches TC-{positive_integer}
            match = TC_ID_PATTERN.match(tc.id)
            assert match is not None, (
                f"Test case ID '{tc.id}' does not match pattern TC-{{positive_integer}}"
            )
            tc_number = int(match.group(1))
            assert tc_number > 0, (
                f"Test case ID number must be positive, got {tc_number}"
            )

            # Title is non-empty and ≤120 characters
            assert len(tc.title) > 0, (
                f"Test case '{tc.id}' has empty title"
            )
            assert len(tc.title) <= 120, (
                f"Test case '{tc.id}' title exceeds 120 chars: {len(tc.title)}"
            )

            # At least 1 precondition
            assert len(tc.preconditions) >= 1, (
                f"Test case '{tc.id}' has no preconditions"
            )

            # At least 1 step
            assert len(tc.steps) >= 1, (
                f"Test case '{tc.id}' has no steps"
            )

            # At least 1 expected result
            assert len(tc.expected_results) >= 1, (
                f"Test case '{tc.id}' has no expected results"
            )

    @given(
        locators=st.lists(detected_locators, min_size=1, max_size=8),
        patterns=st.lists(detected_patterns, min_size=1, max_size=8),
    )
    @settings(max_examples=100)
    def test_ids_are_sequential_positive_integers(
        self,
        locators: list,
        patterns: list,
    ):
        """For any generated output, test case IDs form a sequence TC-1, TC-2, ..., TC-N.

        **Validates: Requirements 7.3**
        """
        generator = TestGenerator()
        test_cases = generator.generate(locators, patterns, pr_metadata={})

        assert len(test_cases) >= 1

        for idx, tc in enumerate(test_cases, start=1):
            expected_id = f"TC-{idx}"
            assert tc.id == expected_id, (
                f"Expected ID '{expected_id}' at position {idx}, got '{tc.id}'"
            )


# --- Strategies for Navigation Property ---

navigation_description_st = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P", "Z")),
    min_size=1,
    max_size=80,
).filter(lambda s: s.strip())

navigation_file_path_st = st.from_regex(
    r"[a-zA-Z][a-zA-Z0-9_/]*\.(kt|swift|java)", fullmatch=True
)

navigation_line_number_st = st.integers(min_value=1, max_value=10000)

navigation_status_st = st.sampled_from([LocatorStatus.ADDED, LocatorStatus.MODIFIED])


@st.composite
def navigation_pattern_strategy(draw):
    """Strategy for generating a DetectedPattern with pattern_type=NAVIGATION and status ADDED or MODIFIED."""
    return DetectedPattern(
        pattern_type=PatternType.NAVIGATION,
        description=draw(navigation_description_st),
        file_path=draw(navigation_file_path_st),
        line_number=draw(navigation_line_number_st),
        status=draw(navigation_status_st),
    )


# --- Property 12: Navigation Change Generates Bidirectional Tests ---


class TestNavigationBidirectionalTests:
    """Property 12: Navigation Change Generates Bidirectional Tests.

    For any navigation pattern with status ADDED or MODIFIED, generator produces
    ≥1 forward and ≥1 back navigation test.

    **Validates: Requirements 7.6**
    """

    @given(pattern=navigation_pattern_strategy())
    @settings(max_examples=100)
    def test_navigation_generates_bidirectional_tests(self, pattern: DetectedPattern):
        """Feature: bitbucket-pr-test-generator, Property 12: Navigation Change Generates Bidirectional Tests

        For any navigation pattern, generator produces ≥1 forward and ≥1 back
        navigation test.

        **Validates: Requirements 7.6**
        """
        generator = TestGenerator()
        test_cases = generator.generate(
            locators=[], patterns=[pattern], pr_metadata={}
        )

        # At least 2 test cases (one forward, one back)
        assert len(test_cases) >= 2, (
            f"Expected ≥2 test cases for navigation pattern, got {len(test_cases)}"
        )

        # At least one test case title contains "forward" (forward navigation)
        titles_lower = [tc.title.lower() for tc in test_cases]
        assert any("forward" in title for title in titles_lower), (
            f"Expected at least one test case with 'forward' in title, got titles: {titles_lower}"
        )

        # At least one test case title contains "back" (back navigation)
        assert any("back" in title for title in titles_lower), (
            f"Expected at least one test case with 'back' in title, got titles: {titles_lower}"
        )


# --- Strategy for generating an ADDED DetectedLocator ---


@st.composite
def added_locator(draw):
    """Generate a DetectedLocator with status=ADDED."""
    return DetectedLocator(
        locator_type=draw(locator_types),
        value=draw(values),
        file_path=draw(file_paths),
        line_number=draw(line_numbers),
        status=LocatorStatus.ADDED,
    )


# --- Property 11: New UI Element Generates Required Test Categories ---


class TestNewUIElementGeneratesRequiredTestCategories:
    """Property 11: New UI Element Generates Required Test Categories.

    For any detected locator with status "added", the test generator should
    produce at least three test cases covering: element visibility on screen
    load, user interaction response, and accessibility label presence.

    **Validates: Requirements 7.5**
    """

    @given(locator=added_locator())
    @settings(max_examples=100)
    def test_added_locator_generates_three_required_categories(
        self, locator: DetectedLocator
    ):
        """Feature: bitbucket-pr-test-generator, Property 11: New UI Element Generates Required Test Categories

        For any added locator, generator produces ≥3 tests covering visibility,
        interaction, accessibility.

        **Validates: Requirements 7.5**
        """
        generator = TestGenerator()
        test_cases = generator.generate(
            locators=[locator],
            patterns=[],
            pr_metadata={},
        )

        # At least 3 test cases should be generated for an added locator
        assert len(test_cases) >= 3, (
            f"Expected ≥3 test cases for an added locator, got {len(test_cases)}. "
            f"Locator: type={locator.locator_type}, value='{locator.value}'"
        )

        # Collect all test case titles (lowercased for keyword matching)
        titles_lower = [tc.title.lower() for tc in test_cases]

        # Check visibility category: "visible" or "visibility" in at least one title
        has_visibility = any(
            "visible" in t or "visibility" in t for t in titles_lower
        )
        assert has_visibility, (
            f"Expected at least one test covering visibility. "
            f"Titles: {[tc.title for tc in test_cases]}"
        )

        # Check interaction category: "interaction" or "interact" in at least one title
        has_interaction = any(
            "interaction" in t or "interact" in t for t in titles_lower
        )
        assert has_interaction, (
            f"Expected at least one test covering interaction. "
            f"Titles: {[tc.title for tc in test_cases]}"
        )

        # Check accessibility category: "accessibility" or "accessible" in at least one title
        has_accessibility = any(
            "accessibility" in t or "accessible" in t for t in titles_lower
        )
        assert has_accessibility, (
            f"Expected at least one test covering accessibility. "
            f"Titles: {[tc.title for tc in test_cases]}"
        )


# --- Strategies for Output Filename Property ---

repo_slug_st = st.from_regex(r"[a-z][a-z0-9\-]{0,29}", fullmatch=True)
pr_id_st = st.integers(min_value=1, max_value=99999)


# --- Property 13: Output Filename Pattern ---


class TestOutputFilenamePattern:
    """Property 13: Output Filename Pattern.

    For any valid repository slug and positive integer PR ID, the generated
    output filename equals `{repo_slug}-PR{pr_id}-test-cases.md` exactly.

    **Validates: Requirements 8.2**
    """

    @given(repo_slug=repo_slug_st, pr_id=pr_id_st)
    @settings(max_examples=100)
    def test_output_filename_matches_expected_pattern(
        self, repo_slug: str, pr_id: int
    ):
        """Feature: bitbucket-pr-test-generator, Property 13: Output Filename Pattern

        For any valid repo slug and PR ID, write_output returns a path whose
        filename equals `{repo_slug}-PR{pr_id}-test-cases.md`.

        **Validates: Requirements 8.2**
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            generator = TestGenerator()
            result_path = generator.write_output(
                "# Test", repo_slug, pr_id, Path(tmp_dir)
            )

            expected_filename = f"{repo_slug}-PR{pr_id}-test-cases.md"
            assert result_path.name == expected_filename, (
                f"Expected filename '{expected_filename}', got '{result_path.name}'"
            )


# --- Strategies for Metadata Header Property ---

pr_links = st.from_regex(
    r"https://bitbucket\.org/[a-z]+/[a-z\-]+/pull-requests/\d+", fullmatch=True
)
branch_names = st.from_regex(r"[a-z][a-z0-9_/\-]{0,20}", fullmatch=True)
file_counts = st.integers(min_value=0, max_value=9999)
repo_slugs = st.from_regex(r"[a-z][a-z0-9\-]{0,15}", fullmatch=True)
pr_ids = st.integers(min_value=1, max_value=99999)


# --- Property 14: Metadata Header Contains All Required Fields ---


class TestMetadataHeaderCompleteness:
    """Property 14: Metadata Header Contains All Required Fields.

    For any generated output, metadata section contains: PR link, ISO 8601 UTC
    timestamp, source branch, destination branch, changed file count.

    **Validates: Requirements 8.5**
    """

    @given(
        pr_link=pr_links,
        source_branch=branch_names,
        destination_branch=branch_names,
        changed_file_count=file_counts,
        repo_slug=repo_slugs,
        pr_id=pr_ids,
    )
    @settings(max_examples=100)
    def test_metadata_header_contains_all_required_fields(
        self,
        pr_link: str,
        source_branch: str,
        destination_branch: str,
        changed_file_count: int,
        repo_slug: str,
        pr_id: int,
    ):
        """Feature: bitbucket-pr-test-generator, Property 14: Metadata Header Contains All Required Fields

        For any generated output, the metadata section contains: PR link URL,
        ISO 8601 UTC timestamp, source branch, destination branch, and changed
        file count.

        **Validates: Requirements 8.5**
        """
        pr_metadata = {
            "pr_link": pr_link,
            "source_branch": source_branch,
            "destination_branch": destination_branch,
            "changed_file_count": changed_file_count,
            "repo_slug": repo_slug,
            "pr_id": pr_id,
        }

        # Generate a simple locator to produce at least one test case
        from models import DetectedLocator, LocatorType, LocatorStatus

        locator = DetectedLocator(
            locator_type=LocatorType.ANDROID_RESOURCE_ID,
            value="sample_button",
            file_path="com/example/Screen.kt",
            line_number=10,
            status=LocatorStatus.ADDED,
        )

        generator = TestGenerator()
        test_cases = generator.generate(
            locators=[locator], patterns=[], pr_metadata=pr_metadata
        )
        markdown = generator.render_markdown(test_cases, pr_metadata)

        # Assert PR link is present in the output
        assert pr_link in markdown, (
            f"PR link '{pr_link}' not found in rendered markdown"
        )

        # Assert timestamp is ISO 8601 UTC format (contains "T" and ends in "Z")
        # Look for a timestamp pattern like 2024-01-15T12:34:56Z
        iso_timestamp_pattern = re.compile(
            r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z"
        )
        assert iso_timestamp_pattern.search(markdown), (
            "No ISO 8601 UTC timestamp (YYYY-MM-DDTHH:MM:SSZ) found in markdown"
        )

        # Assert source branch is present
        assert source_branch in markdown, (
            f"Source branch '{source_branch}' not found in rendered markdown"
        )

        # Assert destination branch is present
        assert destination_branch in markdown, (
            f"Destination branch '{destination_branch}' not found in rendered markdown"
        )

        # Assert changed file count is present as a number
        assert str(changed_file_count) in markdown, (
            f"Changed file count '{changed_file_count}' not found in rendered markdown"
        )
