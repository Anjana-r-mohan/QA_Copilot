"""Unit tests for PRAnalyzer.parse_pr_link() and fetch_pr_metadata()."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from pr_test_generator.analyzer import PRAnalyzer
from pr_test_generator.bitbucket_client import BitbucketClientError
from models import PRMetadata


@pytest.fixture
def analyzer():
    """Create a PRAnalyzer with stub dependencies."""
    return PRAnalyzer(client=None, settings=None)


class TestParsePrLink:
    """Tests for parse_pr_link method."""

    def test_valid_simple_url(self, analyzer: PRAnalyzer):
        result = analyzer.parse_pr_link(
            "https://bitbucket.org/my-team/my-repo/pull-requests/42"
        )
        assert result == ("my-team", "my-repo", 42)

    def test_valid_url_with_underscores(self, analyzer: PRAnalyzer):
        result = analyzer.parse_pr_link(
            "https://bitbucket.org/my_workspace/my_repo/pull-requests/1"
        )
        assert result == ("my_workspace", "my_repo", 1)

    def test_valid_url_with_numbers_in_slug(self, analyzer: PRAnalyzer):
        result = analyzer.parse_pr_link(
            "https://bitbucket.org/team123/repo456/pull-requests/789"
        )
        assert result == ("team123", "repo456", 789)

    def test_valid_url_with_dots_in_repo_slug(self, analyzer: PRAnalyzer):
        result = analyzer.parse_pr_link(
            "https://bitbucket.org/workspace/my.repo.name/pull-requests/5"
        )
        assert result == ("workspace", "my.repo.name", 5)

    def test_valid_url_strips_whitespace(self, analyzer: PRAnalyzer):
        result = analyzer.parse_pr_link(
            "  https://bitbucket.org/team/repo/pull-requests/10  "
        )
        assert result == ("team", "repo", 10)

    def test_invalid_url_empty_string(self, analyzer: PRAnalyzer):
        with pytest.raises(ValueError, match="Invalid PR link"):
            analyzer.parse_pr_link("")

    def test_invalid_url_random_string(self, analyzer: PRAnalyzer):
        with pytest.raises(ValueError, match="Invalid PR link"):
            analyzer.parse_pr_link("not a url at all")

    def test_invalid_url_wrong_host(self, analyzer: PRAnalyzer):
        with pytest.raises(ValueError, match="Invalid PR link"):
            analyzer.parse_pr_link(
                "https://github.com/my-team/my-repo/pull-requests/42"
            )

    def test_invalid_url_missing_pr_id(self, analyzer: PRAnalyzer):
        with pytest.raises(ValueError, match="Invalid PR link"):
            analyzer.parse_pr_link(
                "https://bitbucket.org/my-team/my-repo/pull-requests/"
            )

    def test_invalid_url_non_numeric_pr_id(self, analyzer: PRAnalyzer):
        with pytest.raises(ValueError, match="Invalid PR link"):
            analyzer.parse_pr_link(
                "https://bitbucket.org/my-team/my-repo/pull-requests/abc"
            )

    def test_invalid_url_negative_pr_id(self, analyzer: PRAnalyzer):
        # Negative numbers won't match \d+ so it's caught by regex
        with pytest.raises(ValueError, match="Invalid PR link"):
            analyzer.parse_pr_link(
                "https://bitbucket.org/my-team/my-repo/pull-requests/-1"
            )

    def test_invalid_url_zero_pr_id(self, analyzer: PRAnalyzer):
        with pytest.raises(ValueError, match="must be a positive integer"):
            analyzer.parse_pr_link(
                "https://bitbucket.org/my-team/my-repo/pull-requests/0"
            )

    def test_invalid_url_trailing_path(self, analyzer: PRAnalyzer):
        with pytest.raises(ValueError, match="Invalid PR link"):
            analyzer.parse_pr_link(
                "https://bitbucket.org/my-team/my-repo/pull-requests/42/activity"
            )

    def test_invalid_url_http_not_https(self, analyzer: PRAnalyzer):
        with pytest.raises(ValueError, match="Invalid PR link"):
            analyzer.parse_pr_link(
                "http://bitbucket.org/my-team/my-repo/pull-requests/42"
            )

    def test_invalid_url_missing_workspace(self, analyzer: PRAnalyzer):
        with pytest.raises(ValueError, match="Invalid PR link"):
            analyzer.parse_pr_link(
                "https://bitbucket.org/pull-requests/42"
            )

    def test_error_message_includes_example(self, analyzer: PRAnalyzer):
        with pytest.raises(ValueError, match=r"Example:.*bitbucket\.org"):
            analyzer.parse_pr_link("invalid")



class TestFetchPrMetadata:
    """Tests for fetch_pr_metadata method."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock BitbucketClient."""
        client = AsyncMock()
        return client

    @pytest.fixture
    def analyzer_with_client(self, mock_client):
        """Create a PRAnalyzer with a mocked client."""
        return PRAnalyzer(client=mock_client, settings=None)

    @pytest.fixture
    def sample_api_response(self):
        """Sample Bitbucket API response for a pull request."""
        return {
            "title": "Add login feature",
            "author": {"display_name": "Jane Doe"},
            "source": {
                "branch": {"name": "feature/login"},
                "commit": {"hash": "abc123def456"},
            },
            "destination": {
                "branch": {"name": "main"},
                "commit": {"hash": "789xyz000111"},
            },
            "links": {
                "html": {"href": "https://bitbucket.org/my-team/my-repo/pull-requests/42"}
            },
        }

    @pytest.mark.asyncio
    async def test_successful_fetch(
        self, analyzer_with_client, mock_client, sample_api_response
    ):
        """Test successful fetch maps response to PRMetadata correctly."""
        response_mock = MagicMock()
        response_mock.json.return_value = sample_api_response
        mock_client.request.return_value = response_mock

        result = await analyzer_with_client.fetch_pr_metadata("my-team", "my-repo", 42)

        assert isinstance(result, PRMetadata)
        assert result.title == "Add login feature"
        assert result.author == "Jane Doe"
        assert result.source_branch == "feature/login"
        assert result.destination_branch == "main"
        assert result.head_commit == "abc123def456"
        assert result.base_commit == "789xyz000111"
        assert result.workspace == "my-team"
        assert result.repo_slug == "my-repo"
        assert result.pr_id == 42
        assert result.pr_link == "https://bitbucket.org/my-team/my-repo/pull-requests/42"

    @pytest.mark.asyncio
    async def test_correct_api_endpoint_called(
        self, analyzer_with_client, mock_client, sample_api_response
    ):
        """Test that the correct Bitbucket API endpoint is called."""
        response_mock = MagicMock()
        response_mock.json.return_value = sample_api_response
        mock_client.request.return_value = response_mock

        await analyzer_with_client.fetch_pr_metadata("workspace1", "repo-a", 99)

        mock_client.request.assert_called_once_with(
            "GET", "/repositories/workspace1/repo-a/pullrequests/99"
        )

    @pytest.mark.asyncio
    async def test_404_raises_value_error(self, analyzer_with_client, mock_client):
        """Test that a 404 response raises ValueError with descriptive message."""
        mock_client.request.side_effect = BitbucketClientError(
            "Not found", status_code=404, url="/repositories/team/repo/pullrequests/999"
        )

        with pytest.raises(ValueError, match="Pull request not found"):
            await analyzer_with_client.fetch_pr_metadata("team", "repo", 999)

    @pytest.mark.asyncio
    async def test_404_error_contains_identifiers(self, analyzer_with_client, mock_client):
        """Test that 404 ValueError message includes workspace/repo/pr_id."""
        mock_client.request.side_effect = BitbucketClientError(
            "Not found", status_code=404, url="/repositories/acme/widgets/pullrequests/7"
        )

        with pytest.raises(ValueError, match="acme/widgets#7"):
            await analyzer_with_client.fetch_pr_metadata("acme", "widgets", 7)

    @pytest.mark.asyncio
    async def test_non_404_error_re_raised(self, analyzer_with_client, mock_client):
        """Test that non-404 BitbucketClientErrors are re-raised as-is."""
        error = BitbucketClientError(
            "Server error", status_code=500, url="/repositories/t/r/pullrequests/1"
        )
        mock_client.request.side_effect = error

        with pytest.raises(BitbucketClientError) as exc_info:
            await analyzer_with_client.fetch_pr_metadata("t", "r", 1)

        assert exc_info.value.status_code == 500

    @pytest.mark.asyncio
    async def test_auth_error_propagated(self, analyzer_with_client, mock_client):
        """Test that authentication errors propagate without being caught."""
        from pr_test_generator.bitbucket_client import AuthenticationError

        mock_client.request.side_effect = AuthenticationError(
            "Auth failed", status_code=401, url="/repositories/x/y/pullrequests/1"
        )

        with pytest.raises(AuthenticationError):
            await analyzer_with_client.fetch_pr_metadata("x", "y", 1)
