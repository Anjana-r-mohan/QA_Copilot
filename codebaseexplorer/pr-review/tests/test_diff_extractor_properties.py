"""Property-based tests for the DiffExtractor module.

Feature: bitbucket-pr-test-generator, Property 7: Diffstat Categorization Correctness
Feature: bitbucket-pr-test-generator, Property 8: File Count Aggregation
"""

from __future__ import annotations

from collections import Counter
from unittest.mock import AsyncMock, MagicMock

from hypothesis import given, settings
from hypothesis import strategies as st

from models import FileChange, FileChangeType
from pr_test_generator.diff_extractor import DiffExtractor, _STATUS_MAP


# --- Strategies ---

# Valid Bitbucket diffstat status strings
valid_statuses = st.sampled_from(["added", "modified", "removed", "renamed"])

# File path segments: alphanumeric with common extensions
path_segment = st.from_regex(r"[a-zA-Z][a-zA-Z0-9_]{0,20}", fullmatch=True)
file_extension = st.sampled_from([".py", ".kt", ".swift", ".java", ".ts", ".xml"])

file_path = st.builds(
    lambda segments, ext: "/".join(segments) + ext,
    segments=st.lists(path_segment, min_size=1, max_size=4),
    ext=file_extension,
)


# Strategy to generate a diffstat entry dict with a given status and paths
@st.composite
def diffstat_entry(draw):
    """Generate a random diffstat entry with a valid status and path info."""
    status = draw(valid_statuses)
    new_path = draw(file_path)
    old_path = draw(file_path)

    entry = {"status": status}

    if status == "added":
        entry["new"] = {"path": new_path}
        entry["old"] = None
    elif status == "modified":
        entry["new"] = {"path": new_path}
        entry["old"] = {"path": new_path}  # same path for modified
    elif status == "removed":
        entry["new"] = {"path": old_path}
        entry["old"] = {"path": old_path}
    elif status == "renamed":
        entry["new"] = {"path": new_path}
        entry["old"] = {"path": old_path}

    return entry


# --- Property 7: Diffstat Categorization Correctness ---


class TestDiffstatCategorizationCorrectness:
    """**Validates: Requirements 3.2**

    Property 7: Diffstat Categorization Correctness

    For any diffstat entry with a status field value of "added", "modified",
    "removed", or "renamed", the DiffExtractor should map it to the corresponding
    FileChangeType enum value without loss of information.
    """

    @given(entry=diffstat_entry())
    @settings(max_examples=100)
    def test_status_maps_to_correct_file_change_type(self, entry: dict):
        """Each valid status string is mapped to the corresponding FileChangeType enum.

        The _STATUS_MAP constant maps:
        - "added" → FileChangeType.ADDED
        - "modified" → FileChangeType.MODIFIED
        - "removed" → FileChangeType.REMOVED
        - "renamed" → FileChangeType.RENAMED
        """
        mock_client = AsyncMock()
        extractor = DiffExtractor(mock_client)

        result = extractor._parse_entry(entry)

        # Result should never be None for valid statuses
        assert result is not None, (
            f"_parse_entry returned None for valid status '{entry['status']}'"
        )

        # Verify the mapping is correct
        expected_type = _STATUS_MAP[entry["status"]]
        assert result.change_type == expected_type, (
            f"Expected {expected_type} for status '{entry['status']}', "
            f"got {result.change_type}"
        )

    @given(entry=diffstat_entry())
    @settings(max_examples=100)
    def test_renamed_preserves_old_path(self, entry: dict):
        """For renamed entries, old_path is preserved in the FileChange result."""
        mock_client = AsyncMock()
        extractor = DiffExtractor(mock_client)

        result = extractor._parse_entry(entry)
        assert result is not None

        if entry["status"] == "renamed":
            expected_old_path = entry["old"]["path"]
            assert result.old_path == expected_old_path, (
                f"Expected old_path '{expected_old_path}', got '{result.old_path}'"
            )
        else:
            # Non-renamed entries should not have old_path set
            assert result.old_path is None, (
                f"Expected old_path=None for status '{entry['status']}', "
                f"got '{result.old_path}'"
            )

    @given(entry=diffstat_entry())
    @settings(max_examples=100)
    def test_path_is_non_empty_string(self, entry: dict):
        """The resulting FileChange always has a non-empty path."""
        mock_client = AsyncMock()
        extractor = DiffExtractor(mock_client)

        result = extractor._parse_entry(entry)
        assert result is not None

        assert isinstance(result.path, str)
        assert len(result.path) > 0, (
            f"Expected non-empty path for status '{entry['status']}'"
        )

    @given(status=valid_statuses)
    @settings(max_examples=100)
    def test_status_map_coverage(self, status: str):
        """Every valid status string exists in _STATUS_MAP and maps to a FileChangeType."""
        assert status in _STATUS_MAP, f"Status '{status}' not in _STATUS_MAP"
        assert isinstance(_STATUS_MAP[status], FileChangeType), (
            f"_STATUS_MAP['{status}'] is not a FileChangeType"
        )


# --- Strategies for Property 8: File Count Aggregation ---

# Strategy for random file paths
_random_file_paths = st.from_regex(r"[a-z][a-z0-9_/\-.]{0,60}", fullmatch=True)

# Strategy for random FileChangeType values
_file_change_types = st.sampled_from(list(FileChangeType))

# Strategy for generating a single FileChange object
_file_change_strategy = st.builds(
    FileChange,
    path=_random_file_paths,
    change_type=_file_change_types,
)

# Strategy for lists of FileChange objects (0 to 100 items)
_file_change_lists = st.lists(_file_change_strategy, min_size=0, max_size=100)


# --- Property 8: File Count Aggregation ---


class TestFileCountAggregation:
    """Property 8: File Count Aggregation.

    For any list of FileChange objects, the grouped counts by change type
    should sum to the total number of items in the list, and each individual
    count should equal the actual number of items with that change type.

    **Validates: Requirements 3.4**
    """

    @given(file_changes=_file_change_lists)
    @settings(max_examples=100)
    def test_grouped_counts_sum_to_total(self, file_changes: list[FileChange]):
        """For any list of FileChange objects, the sum of all grouped counts
        should equal the total length of the input list.

        **Validates: Requirements 3.4**
        """
        extractor = DiffExtractor(MagicMock())
        counts = extractor.get_grouped_counts(file_changes)

        assert sum(counts.values()) == len(file_changes)

    @given(file_changes=_file_change_lists)
    @settings(max_examples=100)
    def test_grouped_counts_match_actual_per_type(self, file_changes: list[FileChange]):
        """For any list of FileChange objects, each grouped count should match
        the actual number of items with that change type in the input list.

        **Validates: Requirements 3.4**
        """
        extractor = DiffExtractor(MagicMock())
        counts = extractor.get_grouped_counts(file_changes)

        # Compute expected counts manually
        expected: Counter = Counter()
        for fc in file_changes:
            expected[fc.change_type] += 1

        # Every type present in the input should be in the result with matching count
        for change_type, expected_count in expected.items():
            assert counts.get(change_type) == expected_count

        # No extra types should be in the result
        for change_type in counts:
            assert change_type in expected
