"""Property-based tests for PRAnalyzer.parse_pr_link().

Feature: bitbucket-pr-test-generator
"""

import re
import string

import pytest
from hypothesis import given, assume, settings, HealthCheck
from hypothesis import strategies as st

from pr_test_generator.analyzer import PRAnalyzer


# --- Strategies for Property 1: Round-Trip ---

# Strategy for valid workspace strings: non-empty, alphanumeric + hyphens + underscores
valid_workspace = st.from_regex(r"[A-Za-z0-9][A-Za-z0-9_\-]*", fullmatch=True)

# Strategy for valid repo_slug strings: non-empty, alphanumeric + hyphens + underscores + dots
valid_repo_slug = st.from_regex(r"[A-Za-z0-9][A-Za-z0-9_\-.]*", fullmatch=True)

# Strategy for valid positive integer pr_id values
valid_pr_id = st.integers(min_value=1, max_value=10**9)


class TestPrLinkParsingRoundTrip:
    """Property 1: PR Link Parsing Round-Trip.

    For any valid (workspace, repo_slug, pr_id) tuple, constructing a URL and
    parsing it should yield the original values.

    **Validates: Requirements 1.1**
    """

    @given(workspace=valid_workspace, repo_slug=valid_repo_slug, pr_id=valid_pr_id)
    def test_pr_link_parsing_round_trip(self, workspace: str, repo_slug: str, pr_id: int):
        """For any valid (workspace, repo_slug, pr_id) tuple, constructing
        a Bitbucket PR URL and parsing it should yield the original values.

        **Validates: Requirements 1.1**
        """
        # Construct a valid Bitbucket PR URL
        url = f"https://bitbucket.org/{workspace}/{repo_slug}/pull-requests/{pr_id}"

        # Parse the URL
        analyzer = PRAnalyzer(client=None, settings=None)
        result = analyzer.parse_pr_link(url)

        # Verify round-trip: parsed values match original inputs
        assert result == (workspace, repo_slug, pr_id)


# Valid pattern used to filter out accidentally-valid inputs
_VALID_PR_PATTERN = re.compile(
    r"^https://bitbucket\.org/"
    r"[A-Za-z0-9_\-]+/"
    r"[A-Za-z0-9_\-.]+/"
    r"pull-requests/"
    r"[1-9]\d*$"
)


# --- Strategies for invalid PR links ---

# Completely random text strings (not URLs)
random_text = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P", "S", "Z")),
    min_size=0,
    max_size=200,
)

# URLs with wrong hosts
wrong_host_urls = st.builds(
    lambda host, ws, repo, pr_id: f"https://{host}/{ws}/{repo}/pull-requests/{pr_id}",
    host=st.sampled_from([
        "github.com",
        "gitlab.com",
        "bitbucket.com",
        "example.org",
        "bitbucket.io",
        "www.bitbucket.org",
    ]),
    ws=st.from_regex(r"[A-Za-z0-9_\-]{1,20}", fullmatch=True),
    repo=st.from_regex(r"[A-Za-z0-9_\-\.]{1,20}", fullmatch=True),
    pr_id=st.integers(min_value=1, max_value=99999),
)

# URLs missing path segments (no repo slug or no pull-requests segment)
missing_segments_urls = st.one_of(
    # Missing repo slug
    st.builds(
        lambda ws, pr_id: f"https://bitbucket.org/{ws}/pull-requests/{pr_id}",
        ws=st.from_regex(r"[A-Za-z0-9_\-]{1,20}", fullmatch=True),
        pr_id=st.integers(min_value=1, max_value=99999),
    ),
    # Missing pull-requests segment
    st.builds(
        lambda ws, repo, pr_id: f"https://bitbucket.org/{ws}/{repo}/{pr_id}",
        ws=st.from_regex(r"[A-Za-z0-9_\-]{1,20}", fullmatch=True),
        repo=st.from_regex(r"[A-Za-z0-9_\-\.]{1,20}", fullmatch=True),
        pr_id=st.integers(min_value=1, max_value=99999),
    ),
    # Missing workspace
    st.builds(
        lambda repo, pr_id: f"https://bitbucket.org/{repo}/pull-requests/{pr_id}",
        repo=st.from_regex(r"[A-Za-z0-9_\-\.]{1,20}", fullmatch=True),
        pr_id=st.integers(min_value=1, max_value=99999),
    ),
)

# URLs with non-numeric PR IDs
non_numeric_pr_id_urls = st.builds(
    lambda ws, repo, pr_id: f"https://bitbucket.org/{ws}/{repo}/pull-requests/{pr_id}",
    ws=st.from_regex(r"[A-Za-z0-9_\-]{1,20}", fullmatch=True),
    repo=st.from_regex(r"[A-Za-z0-9_\-\.]{1,20}", fullmatch=True),
    pr_id=st.from_regex(r"[A-Za-z][A-Za-z0-9_\-]{0,10}", fullmatch=True),
)

# Strings with correct prefix but extra path segments
extra_segments_urls = st.builds(
    lambda ws, repo, pr_id, extra: (
        f"https://bitbucket.org/{ws}/{repo}/pull-requests/{pr_id}/{extra}"
    ),
    ws=st.from_regex(r"[A-Za-z0-9_\-]{1,20}", fullmatch=True),
    repo=st.from_regex(r"[A-Za-z0-9_\-\.]{1,20}", fullmatch=True),
    pr_id=st.integers(min_value=1, max_value=99999),
    extra=st.from_regex(r"[A-Za-z0-9_/\-]{1,30}", fullmatch=True),
)

# URLs with PR ID of zero (invalid: must be positive)
zero_pr_id_urls = st.builds(
    lambda ws, repo: f"https://bitbucket.org/{ws}/{repo}/pull-requests/0",
    ws=st.from_regex(r"[A-Za-z0-9_\-]{1,20}", fullmatch=True),
    repo=st.from_regex(r"[A-Za-z0-9_\-\.]{1,20}", fullmatch=True),
)

# Combine all invalid strategies into one
invalid_pr_links = st.one_of(
    random_text,
    wrong_host_urls,
    missing_segments_urls,
    non_numeric_pr_id_urls,
    extra_segments_urls,
    zero_pr_id_urls,
)


class TestInvalidPrLinkRejection:
    """Property 2: Invalid PR Links Are Rejected.

    For any string not matching the expected pattern, parser should return error.

    **Validates: Requirements 1.2**
    """

    @given(data=invalid_pr_links)
    def test_invalid_pr_links_raise_value_error(self, data: str):
        """For any string not matching the expected Bitbucket PR link pattern,
        parse_pr_link should raise ValueError.

        **Validates: Requirements 1.2**
        """
        # PRAnalyzer is stateless for parse_pr_link, safe to reuse
        analyzer = PRAnalyzer(client=None, settings=None)

        # Filter out strings that accidentally match the valid pattern
        assume(not _VALID_PR_PATTERN.match(data.strip()))

        with pytest.raises(ValueError):
            analyzer.parse_pr_link(data)
