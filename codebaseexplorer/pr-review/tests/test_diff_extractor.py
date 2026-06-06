"""Unit tests for the DiffExtractor module.

Tests diffstat fetching, file categorization, pagination handling,
and grouped count aggregation.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from models import FileChange, FileChangeType
from pr_test_generator.bitbucket_client import BitbucketClientError
from pr_test_generator.diff_extractor import DiffExtractor, DiffExtractorError


def _make_response(values: list[dict], next_url: str | None = None) -> MagicMock:
    """Create a mock httpx.Response with JSON data."""
    data = {"values": values}
    if next_url is not None:
        data["next"] = next_url
    resp = MagicMock()
    resp.json.return_value = data
    return resp


@pytest.fixture
def mock_client():
    """Create a mock BitbucketClient."""
    client = AsyncMock()
    return client


class TestFetchDiffstat:
    """Tests for DiffExtractor.fetch_diffstat()."""

    async def test_single_page_added_file(self, mock_client):
        """Single added file is categorized correctly."""
        mock_client.request.return_value = _make_response([
            {"status": "added", "new": {"path": "src/new_file.py"}, "old": None}
        ])

        extractor = DiffExtractor(mock_client)
        result = await extractor.fetch_diffstat("workspace", "repo", 1)

        assert len(result) == 1
        assert result[0].path == "src/new_file.py"
        assert result[0].change_type == FileChangeType.ADDED
        assert result[0].old_path is None

    async def test_single_page_modified_file(self, mock_client):
        """Single modified file is categorized correctly."""
        mock_client.request.return_value = _make_response([
            {
                "status": "modified",
                "new": {"path": "src/main.py"},
                "old": {"path": "src/main.py"},
            }
        ])

        extractor = DiffExtractor(mock_client)
        result = await extractor.fetch_diffstat("workspace", "repo", 1)

        assert len(result) == 1
        assert result[0].path == "src/main.py"
        assert result[0].change_type == FileChangeType.MODIFIED
        assert result[0].old_path is None

    async def test_single_page_removed_file(self, mock_client):
        """Single removed file is categorized correctly."""
        mock_client.request.return_value = _make_response([
            {
                "status": "removed",
                "new": {"path": "src/old.py"},
                "old": {"path": "src/old.py"},
            }
        ])

        extractor = DiffExtractor(mock_client)
        result = await extractor.fetch_diffstat("workspace", "repo", 1)

        assert len(result) == 1
        assert result[0].path == "src/old.py"
        assert result[0].change_type == FileChangeType.REMOVED
        assert result[0].old_path is None

    async def test_renamed_file_includes_both_paths(self, mock_client):
        """Renamed file includes old_path and new path."""
        mock_client.request.return_value = _make_response([
            {
                "status": "renamed",
                "new": {"path": "src/new_name.py"},
                "old": {"path": "src/old_name.py"},
            }
        ])

        extractor = DiffExtractor(mock_client)
        result = await extractor.fetch_diffstat("workspace", "repo", 1)

        assert len(result) == 1
        assert result[0].path == "src/new_name.py"
        assert result[0].change_type == FileChangeType.RENAMED
        assert result[0].old_path == "src/old_name.py"

    async def test_multiple_file_types(self, mock_client):
        """Multiple files with different statuses are categorized correctly."""
        mock_client.request.return_value = _make_response([
            {"status": "added", "new": {"path": "a.py"}, "old": None},
            {"status": "modified", "new": {"path": "b.py"}, "old": {"path": "b.py"}},
            {"status": "removed", "new": {"path": "c.py"}, "old": {"path": "c.py"}},
            {
                "status": "renamed",
                "new": {"path": "d_new.py"},
                "old": {"path": "d_old.py"},
            },
        ])

        extractor = DiffExtractor(mock_client)
        result = await extractor.fetch_diffstat("workspace", "repo", 1)

        assert len(result) == 4
        assert result[0].change_type == FileChangeType.ADDED
        assert result[1].change_type == FileChangeType.MODIFIED
        assert result[2].change_type == FileChangeType.REMOVED
        assert result[3].change_type == FileChangeType.RENAMED
        assert result[3].old_path == "d_old.py"

    async def test_pagination_follows_next_link(self, mock_client):
        """Pagination is followed via the 'next' key."""
        page1 = _make_response(
            [{"status": "added", "new": {"path": "a.py"}, "old": None}],
            next_url="https://api.bitbucket.org/2.0/repositories/ws/repo/pullrequests/1/diffstat?page=2",
        )
        page2 = _make_response(
            [{"status": "modified", "new": {"path": "b.py"}, "old": {"path": "b.py"}}],
            next_url=None,
        )
        mock_client.request.side_effect = [page1, page2]

        extractor = DiffExtractor(mock_client)
        result = await extractor.fetch_diffstat("ws", "repo", 1)

        assert len(result) == 2
        assert mock_client.request.call_count == 2

    async def test_stops_at_max_files_limit(self, mock_client):
        """Stops fetching when 10,000 file limit is reached."""
        # Create a response with many files and a next link
        large_values = [
            {"status": "added", "new": {"path": f"file_{i}.py"}, "old": None}
            for i in range(10_000)
        ]
        mock_client.request.return_value = _make_response(large_values, next_url="http://next")

        extractor = DiffExtractor(mock_client)
        result = await extractor.fetch_diffstat("ws", "repo", 1)

        assert len(result) == 10_000
        # Should not follow the "next" link since limit is hit
        assert mock_client.request.call_count == 1

    async def test_empty_diffstat(self, mock_client):
        """Empty diffstat returns empty list."""
        mock_client.request.return_value = _make_response([])

        extractor = DiffExtractor(mock_client)
        result = await extractor.fetch_diffstat("ws", "repo", 1)

        assert result == []

    async def test_unrecognized_status_is_skipped(self, mock_client):
        """Entries with unrecognized status are skipped."""
        mock_client.request.return_value = _make_response([
            {"status": "unknown_type", "new": {"path": "x.py"}, "old": None},
            {"status": "added", "new": {"path": "valid.py"}, "old": None},
        ])

        extractor = DiffExtractor(mock_client)
        result = await extractor.fetch_diffstat("ws", "repo", 1)

        assert len(result) == 1
        assert result[0].path == "valid.py"

    async def test_api_error_raises_diff_extractor_error(self, mock_client):
        """BitbucketClientError is wrapped in DiffExtractorError."""
        mock_client.request.side_effect = BitbucketClientError(
            "HTTP 404", status_code=404, url="/some/url"
        )

        extractor = DiffExtractor(mock_client)

        with pytest.raises(DiffExtractorError) as exc_info:
            await extractor.fetch_diffstat("ws", "repo", 1)

        assert exc_info.value.status_code == 404
        assert "Failed to fetch diffstat" in str(exc_info.value)


class TestGetGroupedCounts:
    """Tests for DiffExtractor.get_grouped_counts()."""

    def test_empty_list(self):
        """Empty list returns empty dict."""
        extractor = DiffExtractor(MagicMock())
        assert extractor.get_grouped_counts([]) == {}

    def test_all_same_type(self):
        """All files of same type are counted correctly."""
        extractor = DiffExtractor(MagicMock())
        changes = [
            FileChange(path="a.py", change_type=FileChangeType.ADDED),
            FileChange(path="b.py", change_type=FileChangeType.ADDED),
            FileChange(path="c.py", change_type=FileChangeType.ADDED),
        ]
        counts = extractor.get_grouped_counts(changes)
        assert counts == {FileChangeType.ADDED: 3}

    def test_mixed_types(self):
        """Mixed file types are counted correctly and sum to total."""
        extractor = DiffExtractor(MagicMock())
        changes = [
            FileChange(path="a.py", change_type=FileChangeType.ADDED),
            FileChange(path="b.py", change_type=FileChangeType.MODIFIED),
            FileChange(path="c.py", change_type=FileChangeType.MODIFIED),
            FileChange(path="d.py", change_type=FileChangeType.REMOVED),
            FileChange(
                path="e.py",
                change_type=FileChangeType.RENAMED,
                old_path="old_e.py",
            ),
        ]
        counts = extractor.get_grouped_counts(changes)

        assert counts[FileChangeType.ADDED] == 1
        assert counts[FileChangeType.MODIFIED] == 2
        assert counts[FileChangeType.REMOVED] == 1
        assert counts[FileChangeType.RENAMED] == 1
        assert sum(counts.values()) == len(changes)


def _make_file_response(
    text: str = "file content",
    content_type: str = "text/plain",
    content_length: str | None = None,
    status_code: int = 200,
) -> MagicMock:
    """Create a mock httpx.Response for file content requests."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    headers = {"content-type": content_type}
    if content_length is not None:
        headers["content-length"] = content_length
    resp.headers = headers
    return resp


class TestFetchFileContents:
    """Tests for DiffExtractor.fetch_file_contents()."""

    async def test_added_file_sets_empty_base_content(self, mock_client):
        """Added files get base_content='' and head_content fetched."""
        mock_client.request.return_value = _make_file_response("new file content")

        extractor = DiffExtractor(mock_client)
        changes = [FileChange(path="src/new.py", change_type=FileChangeType.ADDED)]

        result = await extractor.fetch_file_contents(
            "ws", "repo", changes, "base123", "head456"
        )

        assert result[0].base_content == ""
        assert result[0].head_content == "new file content"
        # Only one request (head commit only)
        mock_client.request.assert_called_once_with(
            "GET", "/repositories/ws/repo/src/head456/src/new.py"
        )

    async def test_modified_file_fetches_both_commits(self, mock_client):
        """Modified files fetch content at both base and head commits."""
        mock_client.request.side_effect = [
            _make_file_response("head content"),  # head fetch
            _make_file_response("base content"),  # base fetch
        ]

        extractor = DiffExtractor(mock_client)
        changes = [FileChange(path="src/main.py", change_type=FileChangeType.MODIFIED)]

        result = await extractor.fetch_file_contents(
            "ws", "repo", changes, "base123", "head456"
        )

        assert result[0].head_content == "head content"
        assert result[0].base_content == "base content"
        assert mock_client.request.call_count == 2

    async def test_removed_file_fetches_only_base(self, mock_client):
        """Removed files get head_content=None and base_content fetched."""
        mock_client.request.return_value = _make_file_response("old content")

        extractor = DiffExtractor(mock_client)
        changes = [FileChange(path="src/old.py", change_type=FileChangeType.REMOVED)]

        result = await extractor.fetch_file_contents(
            "ws", "repo", changes, "base123", "head456"
        )

        assert result[0].head_content is None
        assert result[0].base_content == "old content"
        # Only one request (base commit only)
        mock_client.request.assert_called_once_with(
            "GET", "/repositories/ws/repo/src/base123/src/old.py"
        )

    async def test_renamed_file_fetches_old_path_for_base(self, mock_client):
        """Renamed files fetch base content from old_path."""
        mock_client.request.side_effect = [
            _make_file_response("head content"),  # head fetch at new path
            _make_file_response("base content"),  # base fetch at old path
        ]

        extractor = DiffExtractor(mock_client)
        changes = [
            FileChange(
                path="src/new_name.py",
                change_type=FileChangeType.RENAMED,
                old_path="src/old_name.py",
            )
        ]

        result = await extractor.fetch_file_contents(
            "ws", "repo", changes, "base123", "head456"
        )

        assert result[0].head_content == "head content"
        assert result[0].base_content == "base content"
        # Verify base was fetched at old path
        calls = mock_client.request.call_args_list
        assert calls[0].args == ("GET", "/repositories/ws/repo/src/head456/src/new_name.py")
        assert calls[1].args == ("GET", "/repositories/ws/repo/src/base123/src/old_name.py")

    async def test_404_returns_none(self, mock_client):
        """404 from API sets content to None and logs warning."""
        mock_client.request.side_effect = BitbucketClientError(
            "HTTP 404", status_code=404, url="/some/url"
        )

        extractor = DiffExtractor(mock_client)
        changes = [FileChange(path="src/missing.py", change_type=FileChangeType.ADDED)]

        result = await extractor.fetch_file_contents(
            "ws", "repo", changes, "base123", "head456"
        )

        # head_content is None because of 404, base_content is "" (added file)
        assert result[0].head_content is None
        assert result[0].base_content == ""

    async def test_skip_binary_extension_png(self, mock_client):
        """Binary files (by extension) are skipped entirely."""
        extractor = DiffExtractor(mock_client)
        changes = [FileChange(path="assets/logo.png", change_type=FileChangeType.ADDED)]

        result = await extractor.fetch_file_contents(
            "ws", "repo", changes, "base123", "head456"
        )

        # No content fetched, no API calls made
        assert result[0].head_content is None
        assert result[0].base_content is None
        mock_client.request.assert_not_called()

    async def test_skip_binary_extension_jar(self, mock_client):
        """JAR files are detected as binary and skipped."""
        extractor = DiffExtractor(mock_client)
        changes = [FileChange(path="libs/dep.jar", change_type=FileChangeType.MODIFIED)]

        result = await extractor.fetch_file_contents(
            "ws", "repo", changes, "base123", "head456"
        )

        assert result[0].head_content is None
        assert result[0].base_content is None
        mock_client.request.assert_not_called()

    async def test_skip_binary_content_type(self, mock_client):
        """Files with binary Content-Type are skipped."""
        mock_client.request.return_value = _make_file_response(
            text="binary data", content_type="application/octet-stream"
        )

        extractor = DiffExtractor(mock_client)
        changes = [FileChange(path="data/file.bin2", change_type=FileChangeType.ADDED)]

        result = await extractor.fetch_file_contents(
            "ws", "repo", changes, "base123", "head456"
        )

        # head_content is None because of binary Content-Type
        assert result[0].head_content is None
        assert result[0].base_content == ""

    async def test_skip_file_exceeding_1mb_content_length(self, mock_client):
        """Files exceeding 1MB (via Content-Length) are skipped."""
        mock_client.request.return_value = _make_file_response(
            text="small preview",
            content_type="text/plain",
            content_length="2000000",  # 2MB
        )

        extractor = DiffExtractor(mock_client)
        changes = [FileChange(path="src/huge.py", change_type=FileChangeType.ADDED)]

        result = await extractor.fetch_file_contents(
            "ws", "repo", changes, "base123", "head456"
        )

        assert result[0].head_content is None
        assert result[0].base_content == ""

    async def test_skip_file_exceeding_1mb_body_size(self, mock_client):
        """Files exceeding 1MB (via body size) are skipped when no Content-Length."""
        large_content = "x" * (1_048_577)  # Just over 1MB
        mock_client.request.return_value = _make_file_response(
            text=large_content,
            content_type="text/plain",
            content_length=None,
        )

        extractor = DiffExtractor(mock_client)
        changes = [FileChange(path="src/huge.py", change_type=FileChangeType.ADDED)]

        result = await extractor.fetch_file_contents(
            "ws", "repo", changes, "base123", "head456"
        )

        assert result[0].head_content is None
        assert result[0].base_content == ""

    async def test_text_content_type_accepted(self, mock_client):
        """text/* Content-Type files are fetched correctly."""
        mock_client.request.return_value = _make_file_response(
            text="kotlin code", content_type="text/x-kotlin"
        )

        extractor = DiffExtractor(mock_client)
        changes = [FileChange(path="src/Main.kt", change_type=FileChangeType.ADDED)]

        result = await extractor.fetch_file_contents(
            "ws", "repo", changes, "base123", "head456"
        )

        assert result[0].head_content == "kotlin code"

    async def test_application_json_content_type_accepted(self, mock_client):
        """application/json Content-Type is treated as text."""
        mock_client.request.return_value = _make_file_response(
            text='{"key": "value"}', content_type="application/json"
        )

        extractor = DiffExtractor(mock_client)
        changes = [FileChange(path="config.json", change_type=FileChangeType.ADDED)]

        result = await extractor.fetch_file_contents(
            "ws", "repo", changes, "base123", "head456"
        )

        assert result[0].head_content == '{"key": "value"}'

    async def test_non_404_error_propagates(self, mock_client):
        """Non-404 errors (auth, rate limit) propagate as exceptions."""
        from pr_test_generator.bitbucket_client import AuthenticationError

        mock_client.request.side_effect = AuthenticationError(
            "Auth failed", status_code=401, url="/some/url"
        )

        extractor = DiffExtractor(mock_client)
        changes = [FileChange(path="src/file.py", change_type=FileChangeType.ADDED)]

        with pytest.raises(AuthenticationError):
            await extractor.fetch_file_contents(
                "ws", "repo", changes, "base123", "head456"
            )

    async def test_multiple_files_processed(self, mock_client):
        """Multiple files are all processed correctly."""
        mock_client.request.side_effect = [
            _make_file_response("added content"),   # head for added file
            _make_file_response("mod head"),        # head for modified file
            _make_file_response("mod base"),        # base for modified file
        ]

        extractor = DiffExtractor(mock_client)
        changes = [
            FileChange(path="src/new.py", change_type=FileChangeType.ADDED),
            FileChange(path="src/existing.py", change_type=FileChangeType.MODIFIED),
        ]

        result = await extractor.fetch_file_contents(
            "ws", "repo", changes, "base123", "head456"
        )

        assert result[0].head_content == "added content"
        assert result[0].base_content == ""
        assert result[1].head_content == "mod head"
        assert result[1].base_content == "mod base"


class TestIsBinaryExtension:
    """Tests for DiffExtractor._is_binary_extension()."""

    @pytest.mark.parametrize(
        "path,expected",
        [
            ("image.png", True),
            ("photo.jpg", True),
            ("photo.JPEG", True),
            ("lib.jar", True),
            ("native.so", True),
            ("archive.zip", True),
            ("module.aar", True),
            ("Compiled.class", True),
            ("icon.gif", True),
            ("doc.pdf", True),
            ("src/main.py", False),
            ("src/Main.kt", False),
            ("build.gradle.kts", False),
            ("README.md", False),
            ("config.json", False),
            ("noextension", False),
        ],
    )
    def test_binary_extension_detection(self, path, expected):
        assert DiffExtractor._is_binary_extension(path) == expected


class TestIsTextContentType:
    """Tests for DiffExtractor._is_text_content_type()."""

    @pytest.mark.parametrize(
        "content_type,expected",
        [
            ("text/plain", True),
            ("text/html", True),
            ("text/x-kotlin", True),
            ("text/plain; charset=utf-8", True),
            ("application/json", True),
            ("application/xml", True),
            ("application/javascript", True),
            ("application/ld+json", True),
            ("application/atom+xml", True),
            ("application/octet-stream", False),
            ("image/png", False),
            ("application/zip", False),
            ("", True),  # empty = assume text
        ],
    )
    def test_content_type_detection(self, content_type, expected):
        assert DiffExtractor._is_text_content_type(content_type) == expected
