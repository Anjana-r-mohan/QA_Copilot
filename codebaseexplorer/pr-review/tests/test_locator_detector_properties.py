"""Property-based tests for the LocatorDetector module.

Uses Hypothesis to verify correctness properties of locator detection
and classification logic across randomly generated inputs.
"""

from hypothesis import given, strategies as st, settings

from models import (
    DetectedLocator,
    FileChange,
    FileChangeType,
    LocatorStatus,
    LocatorType,
)
from pr_test_generator.locator_detector import LocatorDetector


# --- Strategies ---

locator_types = st.sampled_from(list(LocatorType))

# Generate valid locator values: non-empty identifiers without quotes or newlines
locator_values = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "Pc", "Pd"),
                           whitelist_characters="_"),
    min_size=1,
    max_size=30,
).filter(lambda s: s.strip() == s and len(s) > 0)

# A locator item is a (LocatorType, value) pair
locator_item = st.tuples(locator_types, locator_values)

# Sets of locator items (using frozensets for set operations, lists for strategy)
locator_set = st.frozensets(locator_item, min_size=0, max_size=10)

# Line numbers (positive integers)
line_numbers = st.integers(min_value=1, max_value=500)


# --- Strategies for Property 3: Locator Regex Detection and Value Extraction ---

# Characters that Python's str.splitlines() treats as line boundaries.
# The detector scans line-by-line, so locator values must not contain these.
_LINE_SEPARATORS = '"\n\r\x0b\x0c\x1c\x1d\x1e\x85\u2028\u2029'

# Android resource IDs: \w+ (word characters, must start with letter or underscore)
android_identifiers = st.from_regex(r"[A-Za-z_][A-Za-z0-9_]{0,30}", fullmatch=True)

# Compose test tag values: non-empty strings without quotes or line separators
# (the regex [^"]+ requires the value to be on a single line)
compose_tag_values = st.text(
    alphabet=st.characters(
        blacklist_characters=_LINE_SEPARATORS,
        blacklist_categories=("Cs",),
    ),
    min_size=1,
    max_size=50,
)

# iOS accessibility identifier values: non-empty strings without quotes or line separators
ios_acc_values = st.text(
    alphabet=st.characters(
        blacklist_characters=_LINE_SEPARATORS,
        blacklist_categories=("Cs",),
    ),
    min_size=1,
    max_size=50,
)

# Content description values: non-empty strings without quotes or line separators
content_desc_values = st.text(
    alphabet=st.characters(
        blacklist_characters=_LINE_SEPARATORS,
        blacklist_categories=("Cs",),
    ),
    min_size=1,
    max_size=50,
)


# --- Property 3: Locator Regex Detection and Value Extraction ---


class TestLocatorRegexDetectionAndValueExtraction:
    """Property 3: Locator Regex Detection and Value Extraction.

    For any locator type and valid identifier/value string, embedding that
    locator in a code string using the canonical pattern and scanning the code
    should detect the locator and extract the exact original value.

    **Validates: Requirements 5.1, 5.2, 5.3, 5.4**
    """

    @given(identifier=android_identifiers)
    @settings(max_examples=100)
    def test_android_resource_id_detection(self, identifier: str):
        """For any valid Android identifier, embedding R.id.{identifier} in code
        and scanning should detect it and extract the exact value.

        **Validates: Requirements 5.1**
        """
        code = f"val view = R.id.{identifier}"
        file_change = FileChange(
            path="app/Activity.kt",
            change_type=FileChangeType.ADDED,
            base_content="",
            head_content=code,
        )

        detector = LocatorDetector()
        results = detector.detect(file_change)

        # At least one result detected
        assert len(results) >= 1, (
            f"Expected at least one detection for R.id.{identifier}"
        )
        # Find the result matching our identifier
        matching = [r for r in results if r.value == identifier]
        assert len(matching) >= 1, (
            f"Expected to find identifier '{identifier}' in results, "
            f"got values: {[r.value for r in results]}"
        )
        # Verify correct locator type
        assert matching[0].locator_type == LocatorType.ANDROID_RESOURCE_ID

    @given(value=compose_tag_values)
    @settings(max_examples=100)
    def test_compose_test_tag_detection(self, value: str):
        """For any valid non-empty string without quotes, embedding
        Modifier.testTag("{value}") in code and scanning should detect it
        and extract the exact value.

        **Validates: Requirements 5.2**
        """
        code = f'Modifier.testTag("{value}")'
        file_change = FileChange(
            path="app/Screen.kt",
            change_type=FileChangeType.ADDED,
            base_content="",
            head_content=code,
        )

        detector = LocatorDetector()
        results = detector.detect(file_change)

        assert len(results) >= 1, (
            f"Expected at least one detection for testTag(\"{value}\")"
        )
        matching = [r for r in results if r.value == value]
        assert len(matching) >= 1, (
            f"Expected to find value '{value}' in results, "
            f"got values: {[r.value for r in results]}"
        )
        assert matching[0].locator_type == LocatorType.COMPOSE_TEST_TAG

    @given(value=ios_acc_values)
    @settings(max_examples=100)
    def test_ios_accessibility_identifier_detection(self, value: str):
        """For any valid non-empty string without quotes, embedding
        .accessibilityIdentifier("{value}") in code and scanning should detect
        it and extract the exact value.

        **Validates: Requirements 5.3**
        """
        code = f'.accessibilityIdentifier("{value}")'
        file_change = FileChange(
            path="ios/LoginView.swift",
            change_type=FileChangeType.ADDED,
            base_content="",
            head_content=code,
        )

        detector = LocatorDetector()
        results = detector.detect(file_change)

        assert len(results) >= 1, (
            f"Expected at least one detection for accessibilityIdentifier(\"{value}\")"
        )
        matching = [r for r in results if r.value == value]
        assert len(matching) >= 1, (
            f"Expected to find value '{value}' in results, "
            f"got values: {[r.value for r in results]}"
        )
        assert matching[0].locator_type == LocatorType.IOS_ACCESSIBILITY_ID

    @given(value=content_desc_values)
    @settings(max_examples=100)
    def test_content_description_detection(self, value: str):
        """For any valid non-empty string without quotes, embedding
        contentDescription = "{value}" in code and scanning should detect it
        and extract the exact value.

        **Validates: Requirements 5.4**
        """
        code = f'contentDescription = "{value}"'
        file_change = FileChange(
            path="app/Component.kt",
            change_type=FileChangeType.ADDED,
            base_content="",
            head_content=code,
        )

        detector = LocatorDetector()
        results = detector.detect(file_change)

        assert len(results) >= 1, (
            f"Expected at least one detection for contentDescription = \"{value}\""
        )
        matching = [r for r in results if r.value == value]
        assert len(matching) >= 1, (
            f"Expected to find value '{value}' in results, "
            f"got values: {[r.value for r in results]}"
        )
        assert matching[0].locator_type == LocatorType.CONTENT_DESCRIPTION


# --- Property 4: Locator and Pattern Classification via Set-Difference ---


class TestLocatorClassificationProperty:
    """Property 4: Locator and Pattern Classification via Set-Difference.

    **Validates: Requirements 5.5, 6.5**

    For any two sets of detected items (base_set and head_set), the
    classification should satisfy:
    - Items in head_set but not in base_set are classified as "added"
    - Items in base_set but not in head_set are classified as "removed"
    - Items present in both but with changed line numbers are "modified"
    """

    @given(
        base_items=locator_set,
        head_items=locator_set,
        base_line=line_numbers,
        head_line=line_numbers,
    )
    @settings(max_examples=100)
    def test_classification_via_set_difference(
        self,
        base_items: frozenset[tuple[LocatorType, str]],
        head_items: frozenset[tuple[LocatorType, str]],
        base_line: int,
        head_line: int,
    ):
        """Feature: bitbucket-pr-test-generator, Property 4: Locator and Pattern Classification via Set-Difference

        **Validates: Requirements 5.5, 6.5**
        """
        detector = LocatorDetector()

        # Build base_locators dict: (LocatorType, value) -> [(line_number, value)]
        # Use distinct line numbers for base items to avoid collisions
        base_locators: dict[tuple[LocatorType, str], list[tuple[int, str]]] = {}
        for i, (loc_type, value) in enumerate(sorted(base_items, key=str)):
            line = base_line + i
            base_locators[(loc_type, value)] = [(line, value)]

        # Build head_locators dict with different line offset
        head_locators: dict[tuple[LocatorType, str], list[tuple[int, str]]] = {}
        for i, (loc_type, value) in enumerate(sorted(head_items, key=str)):
            line = head_line + i
            head_locators[(loc_type, value)] = [(line, value)]

        file_path = "test/File.kt"
        results = detector._classify_locators(base_locators, head_locators, file_path)

        # Compute expected sets
        only_in_head = head_items - base_items
        only_in_base = base_items - head_items
        in_both = base_items & head_items

        # Collect results by status
        added = {(r.locator_type, r.value) for r in results if r.status == LocatorStatus.ADDED}
        removed = {(r.locator_type, r.value) for r in results if r.status == LocatorStatus.REMOVED}
        modified = {(r.locator_type, r.value) for r in results if r.status == LocatorStatus.MODIFIED}

        # Property: items only in head are classified as "added"
        assert added == only_in_head, (
            f"Added mismatch: expected {only_in_head}, got {added}"
        )

        # Property: items only in base are classified as "removed"
        assert removed == only_in_base, (
            f"Removed mismatch: expected {only_in_base}, got {removed}"
        )

        # Property: items in both with different line numbers are "modified"
        # Items in both with same line numbers are NOT reported
        expected_modified = set()
        for key in in_both:
            base_lines = sorted(t[0] for t in base_locators[key])
            head_lines = sorted(t[0] for t in head_locators[key])
            if base_lines != head_lines:
                expected_modified.add(key)

        assert modified == expected_modified, (
            f"Modified mismatch: expected {expected_modified}, got {modified}"
        )

    @given(
        common_items=st.frozensets(locator_item, min_size=1, max_size=5),
        same_line=line_numbers,
    )
    @settings(max_examples=100)
    def test_same_line_items_not_reported(
        self,
        common_items: frozenset[tuple[LocatorType, str]],
        same_line: int,
    ):
        """Items in both base and head at the same line numbers produce no output.

        **Validates: Requirements 5.5, 6.5**
        """
        detector = LocatorDetector()

        # Both base and head have the same items at the same line numbers
        locators: dict[tuple[LocatorType, str], list[tuple[int, str]]] = {}
        for i, (loc_type, value) in enumerate(sorted(common_items, key=str)):
            line = same_line + i
            locators[(loc_type, value)] = [(line, value)]

        file_path = "test/Same.kt"
        results = detector._classify_locators(locators, locators, file_path)

        # No items should be reported since everything is unchanged
        assert results == [], (
            f"Expected no results for identical sets, got {len(results)} items"
        )

    @given(
        added_items=st.frozensets(locator_item, min_size=0, max_size=5),
        removed_items=st.frozensets(locator_item, min_size=0, max_size=5),
    )
    @settings(max_examples=100)
    def test_disjoint_sets_no_modified(
        self,
        added_items: frozenset[tuple[LocatorType, str]],
        removed_items: frozenset[tuple[LocatorType, str]],
    ):
        """When base and head sets are completely disjoint, no 'modified' results appear.

        **Validates: Requirements 5.5, 6.5**
        """
        # Ensure disjoint by removing overlap
        actual_removed = removed_items - added_items
        actual_added = added_items - removed_items

        detector = LocatorDetector()

        base_locators: dict[tuple[LocatorType, str], list[tuple[int, str]]] = {}
        for i, (loc_type, value) in enumerate(sorted(actual_removed, key=str)):
            base_locators[(loc_type, value)] = [(i + 1, value)]

        head_locators: dict[tuple[LocatorType, str], list[tuple[int, str]]] = {}
        for i, (loc_type, value) in enumerate(sorted(actual_added, key=str)):
            head_locators[(loc_type, value)] = [(i + 1, value)]

        file_path = "test/Disjoint.kt"
        results = detector._classify_locators(base_locators, head_locators, file_path)

        modified = [r for r in results if r.status == LocatorStatus.MODIFIED]
        assert modified == [], (
            f"Expected no modified items for disjoint sets, got {len(modified)}"
        )

        # All results should be either added or removed
        for r in results:
            assert r.status in (LocatorStatus.ADDED, LocatorStatus.REMOVED)


# --- Property 6: Detected Item Data Completeness ---


def _embed_locator(locator_type: LocatorType, value: str) -> str:
    """Embed a locator value into its canonical code pattern."""
    if locator_type == LocatorType.ANDROID_RESOURCE_ID:
        return f"val view = R.id.{value}"
    elif locator_type == LocatorType.COMPOSE_TEST_TAG:
        return f'Modifier.testTag("{value}")'
    elif locator_type == LocatorType.IOS_ACCESSIBILITY_ID:
        return f'.accessibilityIdentifier("{value}")'
    elif locator_type == LocatorType.CONTENT_DESCRIPTION:
        return f'contentDescription = "{value}"'
    return ""


# Strategy: generate content guaranteed to contain at least one locator.
# We pick a locator type, generate a valid value for it, embed it,
# and optionally surround with random padding lines.

_padding_lines = st.lists(
    st.text(
        alphabet=st.characters(
            whitelist_categories=("L", "N", "Zs", "Pc", "Pd"),
            whitelist_characters=" =(){}[];",
        ),
        min_size=0,
        max_size=80,
    ),
    min_size=0,
    max_size=10,
)


@st.composite
def code_with_locator(draw):
    """Generate code content guaranteed to contain at least one locator pattern."""
    # Pick a locator type
    loc_type = draw(locator_types)

    # Generate an appropriate value based on type
    if loc_type == LocatorType.ANDROID_RESOURCE_ID:
        value = draw(android_identifiers)
    else:
        # For string-based locators, use non-empty text without quotes/newlines
        value = draw(
            st.text(
                alphabet=st.characters(
                    blacklist_characters=_LINE_SEPARATORS,
                    blacklist_categories=("Cs",),
                ),
                min_size=1,
                max_size=30,
            )
        )

    # Build the locator line
    locator_line = _embed_locator(loc_type, value)

    # Surround with padding lines
    before = draw(_padding_lines)
    after = draw(_padding_lines)

    lines = before + [locator_line] + after
    return "\n".join(lines)


# File paths: non-empty relative paths for the FileChange.
# We construct valid paths directly to avoid excessive filtering.
_path_segment = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N", "Pc", "Pd"),
        whitelist_characters="._-",
    ),
    min_size=1,
    max_size=20,
)

file_paths = st.builds(
    lambda parts: "/".join(parts),
    st.lists(_path_segment, min_size=2, max_size=4),
)


class TestDetectedItemDataCompleteness:
    """Property 6: Detected Item Data Completeness.

    For any code file containing at least one detectable locator, every item in
    the detection result should have a non-empty file_path, a line_number greater
    than zero, a valid type enum value, and a non-empty extracted value.

    **Validates: Requirements 5.6**
    """

    @given(
        content=code_with_locator(),
        file_path=file_paths,
    )
    @settings(max_examples=100)
    def test_detected_items_are_complete(self, content: str, file_path: str):
        """Feature: bitbucket-pr-test-generator, Property 6: Detected Item Data Completeness

        For any file with detectable locators, every result item should have
        non-empty file_path, line_number > 0, valid type, non-empty value,
        and valid status.

        **Validates: Requirements 5.6**
        """
        file_change = FileChange(
            path=file_path,
            change_type=FileChangeType.ADDED,
            base_content="",
            head_content=content,
        )

        detector = LocatorDetector()
        results = detector.detect(file_change)

        # We generated content with at least one locator, so results should be non-empty
        assert len(results) >= 1, (
            f"Expected at least one detection for content with embedded locator, "
            f"got 0 results"
        )

        for item in results:
            # file_path is non-empty
            assert item.file_path != "", (
                f"DetectedLocator has empty file_path: {item}"
            )

            # line_number > 0
            assert item.line_number > 0, (
                f"DetectedLocator has line_number <= 0: {item.line_number}"
            )

            # locator_type is a valid LocatorType enum member
            assert isinstance(item.locator_type, LocatorType), (
                f"DetectedLocator has invalid locator_type: {item.locator_type}"
            )

            # value is non-empty
            assert item.value != "", (
                f"DetectedLocator has empty value: {item}"
            )

            # status is a valid LocatorStatus enum member
            assert isinstance(item.status, LocatorStatus), (
                f"DetectedLocator has invalid status: {item.status}"
            )
