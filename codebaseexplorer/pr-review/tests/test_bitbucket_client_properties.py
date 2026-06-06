"""Property-based tests for the BitbucketClient retry logic.

Feature: bitbucket-pr-test-generator, Property 15 & 16
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from pr_test_generator.bitbucket_client import (
    BitbucketClient,
    RateLimitError,
    TransientError,
    compute_backoff_delay,
)
from pr_test_generator.settings import Settings


# --- Strategies ---

# 5xx status codes that the client considers transient
transient_statuses = st.sampled_from([500, 502, 503, 504])

# Rate-limit status code
rate_limit_status = st.just(429)

# A single response status that is either 429 or 5xx
error_status = st.one_of(transient_statuses, rate_limit_status)

# A sequence of mixed error statuses (1 to 10 responses), followed by an optional success
error_sequence = st.lists(error_status, min_size=1, max_size=10)


# --- Helpers ---

def _make_settings() -> Settings:
    """Create a minimal Settings instance for testing."""
    return Settings(
        email="test@example.com",
        api_token="fake-token",
        output_dir=Path("./output"),
    )


def _make_response(status_code: int) -> httpx.Response:
    """Create a mock httpx.Response with the given status code."""
    return httpx.Response(
        status_code=status_code,
        request=httpx.Request("GET", "https://api.bitbucket.org/2.0/test"),
    )


# --- Property 16: Independent Retry Counters ---


class TestIndependentRetryCounters:
    """**Validates: Requirements 10.6**

    Property 16: Independent Retry Counters

    For any sequence of mixed 429 and 5xx responses, rate-limit retries (429)
    should not decrement the transient error (5xx) retry budget and vice versa,
    allowing up to 3 retries of each type independently per request.
    """

    @given(
        error_statuses=st.lists(
            st.sampled_from([429, 500, 502, 503, 504]),
            min_size=1,
            max_size=10,
        )
    )
    @settings(max_examples=100)
    @pytest.mark.asyncio
    async def test_independent_counters_never_cross_contaminate(
        self, error_statuses: list[int]
    ):
        """429 retries don't consume 5xx budget and vice versa.

        Given a sequence of error responses followed by a 200 success,
        the request succeeds as long as both counters stay within their
        independent budget of 3 retries each.
        """
        # Count how many of each error type in the sequence
        rate_limit_count = sum(1 for s in error_statuses if s == 429)
        transient_count = sum(1 for s in error_statuses if s != 429)

        # Only test sequences where both counters are within budget (<=3 each)
        assume(rate_limit_count <= 3)
        assume(transient_count <= 3)

        # Build the response sequence: all errors, then a success
        responses = [_make_response(s) for s in error_statuses]
        responses.append(_make_response(200))

        settings_obj = _make_settings()
        client = BitbucketClient(settings_obj)

        call_count = 0

        async def mock_request(*args, **kwargs):
            nonlocal call_count
            resp = responses[call_count]
            call_count += 1
            return resp

        # Patch the internal httpx client's request method and asyncio.sleep
        with patch.object(client._http, "request", side_effect=mock_request):
            with patch("pr_test_generator.bitbucket_client.asyncio.sleep", new_callable=AsyncMock):
                result = await client.request("GET", "/test")

        # The request should succeed since both counters are within budget
        assert result.status_code == 200
        # All responses should have been consumed (errors + the final 200)
        assert call_count == len(error_statuses) + 1

        await client.aclose()

    @given(
        rate_limit_extras=st.integers(min_value=4, max_value=8),
        transient_count=st.integers(min_value=0, max_value=3),
    )
    @settings(max_examples=100)
    @pytest.mark.asyncio
    async def test_exceeding_rate_limit_budget_raises_regardless_of_transient(
        self, rate_limit_extras: int, transient_count: int
    ):
        """Exceeding 429 budget (>3) raises RateLimitError even with unused 5xx budget.

        This proves that 5xx budget does NOT help 429 retries — they are independent.
        """
        # Build a sequence with more than 3 rate-limit responses interleaved with
        # some transient errors (within their own budget)
        statuses: list[int] = []
        # Add some transient errors first (within budget)
        statuses.extend([500] * transient_count)
        # Add more than 3 rate-limit errors — this should exhaust the 429 budget
        statuses.extend([429] * rate_limit_extras)

        responses = [_make_response(s) for s in statuses]

        settings_obj = _make_settings()
        client = BitbucketClient(settings_obj)

        call_count = 0

        async def mock_request(*args, **kwargs):
            nonlocal call_count
            resp = responses[call_count]
            call_count += 1
            return resp

        with patch.object(client._http, "request", side_effect=mock_request):
            with patch("pr_test_generator.bitbucket_client.asyncio.sleep", new_callable=AsyncMock):
                with pytest.raises(RateLimitError):
                    await client.request("GET", "/test")

        await client.aclose()

    @given(
        transient_extras=st.integers(min_value=4, max_value=8),
        rate_limit_count=st.integers(min_value=0, max_value=3),
    )
    @settings(max_examples=100)
    @pytest.mark.asyncio
    async def test_exceeding_transient_budget_raises_regardless_of_rate_limit(
        self, transient_extras: int, rate_limit_count: int
    ):
        """Exceeding 5xx budget (>3) raises TransientError even with unused 429 budget.

        This proves that 429 budget does NOT help 5xx retries — they are independent.
        """
        # Build a sequence with some rate-limit responses (within their budget)
        # followed by more than 3 transient errors to exhaust the 5xx budget
        statuses: list[int] = []
        # Add some rate-limit errors first (within budget)
        statuses.extend([429] * rate_limit_count)
        # Add more than 3 transient errors — this should exhaust the 5xx budget
        statuses.extend([500] * transient_extras)

        responses = [_make_response(s) for s in statuses]

        settings_obj = _make_settings()
        client = BitbucketClient(settings_obj)

        call_count = 0

        async def mock_request(*args, **kwargs):
            nonlocal call_count
            resp = responses[call_count]
            call_count += 1
            return resp

        with patch.object(client._http, "request", side_effect=mock_request):
            with patch("pr_test_generator.bitbucket_client.asyncio.sleep", new_callable=AsyncMock):
                with pytest.raises(TransientError):
                    await client.request("GET", "/test")

        await client.aclose()

    @given(
        data=st.data(),
    )
    @settings(max_examples=100)
    @pytest.mark.asyncio
    async def test_interleaved_errors_up_to_six_retries_still_succeed(
        self, data: st.DataObject
    ):
        """A request can survive up to 3 rate-limit AND 3 transient retries (6 total).

        Generates an interleaved sequence of exactly 3 rate-limit and 3 transient
        errors in random order, followed by a 200 success.
        """
        # Create exactly 3 of each error type
        rate_limit_errors = [429, 429, 429]
        transient_errors = data.draw(
            st.lists(
                st.sampled_from([500, 502, 503, 504]),
                min_size=3,
                max_size=3,
            )
        )

        # Combine and shuffle to get a random interleaving
        all_errors = rate_limit_errors + transient_errors
        shuffled = data.draw(st.permutations(all_errors))

        # Build response list: all errors then success
        responses = [_make_response(s) for s in shuffled]
        responses.append(_make_response(200))

        settings_obj = _make_settings()
        client = BitbucketClient(settings_obj)

        call_count = 0

        async def mock_request(*args, **kwargs):
            nonlocal call_count
            resp = responses[call_count]
            call_count += 1
            return resp

        with patch.object(client._http, "request", side_effect=mock_request):
            with patch("pr_test_generator.bitbucket_client.asyncio.sleep", new_callable=AsyncMock):
                result = await client.request("GET", "/test")

        # Should succeed after consuming all 6 error responses + the final 200
        assert result.status_code == 200
        assert call_count == 7  # 6 errors + 1 success

        await client.aclose()


# --- Property 15: Retry Delay Follows Exponential Backoff Capped at 30 Seconds ---


class TestRetryDelayExponentialBackoff:
    """**Validates: Requirements 2.6, 10.3, 10.4**

    Property 15: Retry Delay Follows Exponential Backoff Capped at 30 Seconds

    For any attempt number (1 through N), the computed retry delay should equal
    min(base_delay * 2^(attempt-1), 30) seconds, where base_delay is the configured
    starting delay, and the result should never exceed 30 seconds regardless of the
    attempt number.
    """

    @given(
        attempt=st.integers(min_value=1, max_value=100),
        base_delay=st.floats(min_value=0.1, max_value=10.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=100)
    def test_delay_equals_exponential_backoff_formula(self, attempt: int, base_delay: float):
        """The computed delay must equal min(base_delay * 2^(attempt-1), 30)."""
        result = compute_backoff_delay(attempt, base_delay)
        expected = min(base_delay * (2 ** (attempt - 1)), 30.0)
        assert result == expected, (
            f"Expected {expected} for attempt={attempt}, base_delay={base_delay}, got {result}"
        )

    @given(
        attempt=st.integers(min_value=1, max_value=100),
        base_delay=st.floats(min_value=0.1, max_value=10.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=100)
    def test_delay_never_exceeds_30_seconds(self, attempt: int, base_delay: float):
        """The result should never exceed 30 seconds regardless of attempt number."""
        result = compute_backoff_delay(attempt, base_delay)
        assert result <= 30.0, (
            f"Delay {result} exceeded 30s cap for attempt={attempt}, base_delay={base_delay}"
        )
