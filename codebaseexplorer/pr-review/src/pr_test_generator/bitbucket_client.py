"""Async Bitbucket Cloud REST API client for the PR Test Generator.

This is a standalone client (independent of bitbucket_mcp) that implements:
- HTTP Basic Auth using BITBUCKET_EMAIL and BITBUCKET_API_TOKEN via Settings
- Transient error retries (5xx, network failures): max 3 retries with exponential backoff
- Rate-limit retries (429): parse Retry-After header, default to 60s, max 3 retries
- Both retry counters are INDEPENDENT per request
- 401: return auth error immediately without retrying
- 403: return insufficient permissions error immediately without retrying
- On exhaustion: report HTTP status/network error, endpoint URL, and attempt count
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from .settings import Settings

log = logging.getLogger("pr_test_generator.bitbucket_client")

# Retry configuration
_MAX_TRANSIENT_RETRIES = 3
_MAX_RATE_LIMIT_RETRIES = 3
_BACKOFF_BASE = 1.0  # seconds
_BACKOFF_CAP = 30.0  # seconds
_RATE_LIMIT_DEFAULT_WAIT = 60.0  # seconds when Retry-After header is absent

# HTTP status codes considered transient (retryable)
_TRANSIENT_STATUSES = frozenset({500, 502, 503, 504})


class BitbucketClientError(Exception):
    """Base error for BitbucketClient failures."""

    def __init__(self, message: str, *, status_code: int | None = None, url: str = "") -> None:
        self.status_code = status_code
        self.url = url
        super().__init__(message)


class AuthenticationError(BitbucketClientError):
    """401 Unauthorized — invalid or expired credentials."""

    pass


class InsufficientPermissionsError(BitbucketClientError):
    """403 Forbidden — token lacks required scope."""

    pass


class TransientError(BitbucketClientError):
    """Transient error (5xx or network failure) after all retries exhausted."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        url: str = "",
        attempts: int = 0,
    ) -> None:
        self.attempts = attempts
        super().__init__(message, status_code=status_code, url=url)


class RateLimitError(BitbucketClientError):
    """429 Too Many Requests after all rate-limit retries exhausted."""

    def __init__(
        self,
        message: str,
        *,
        url: str = "",
        attempts: int = 0,
    ) -> None:
        self.attempts = attempts
        super().__init__(message, status_code=429, url=url)


def compute_backoff_delay(attempt: int, base_delay: float = _BACKOFF_BASE) -> float:
    """Compute exponential backoff delay capped at 30 seconds.

    Formula: min(base_delay * 2^(attempt-1), 30)

    Args:
        attempt: The retry attempt number (1-indexed).
        base_delay: Base delay in seconds (default 1.0).

    Returns:
        Delay in seconds, never exceeding 30.
    """
    return min(base_delay * (2 ** (attempt - 1)), _BACKOFF_CAP)


def parse_retry_after(response: httpx.Response) -> float:
    """Parse the Retry-After header from a 429 response.

    Returns the number of seconds to wait. If the header is absent or
    cannot be parsed, returns the default of 60 seconds.
    """
    retry_after = response.headers.get("Retry-After")
    if retry_after is not None:
        try:
            value = float(retry_after)
            if value >= 0:
                return value
        except (ValueError, TypeError):
            pass
    return _RATE_LIMIT_DEFAULT_WAIT


class BitbucketClient:
    """Async HTTP client for the Bitbucket Cloud REST API v2.0.

    Handles authentication, transient error retries with exponential backoff,
    and rate-limit retries independently. Exposes a generic `request()` method
    that all higher-level API methods should use.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._http = httpx.AsyncClient(
            base_url="https://api.bitbucket.org/2.0",
            auth=settings.basic_auth,
            headers={"Accept": "application/json"},
            timeout=60.0,
            follow_redirects=True,
        )

    async def aclose(self) -> None:
        """Close the underlying HTTP client."""
        await self._http.aclose()

    async def __aenter__(self) -> "BitbucketClient":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.aclose()

    async def request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        json: Any | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        """Issue an HTTP request with full retry/auth/rate-limit handling.

        Retry counters are independent:
        - Up to 3 retries for transient errors (5xx, network failures)
          with exponential backoff (1s, 2s, 4s) capped at 30s.
        - Up to 3 retries for rate-limit (429) responses using Retry-After
          header value (default 60s if absent).

        Raises:
            AuthenticationError: On 401 response (no retry).
            InsufficientPermissionsError: On 403 response (no retry).
            TransientError: After exhausting transient retries.
            RateLimitError: After exhausting rate-limit retries.
            BitbucketClientError: For other non-success HTTP responses.
        """
        transient_attempts = 0
        rate_limit_attempts = 0

        while True:
            try:
                response = await self._http.request(
                    method, url, params=params, json=json, **kwargs
                )
            except (
                httpx.ConnectTimeout,
                httpx.ReadTimeout,
                httpx.WriteTimeout,
                httpx.PoolTimeout,
                httpx.ConnectError,
                httpx.RemoteProtocolError,
            ) as exc:
                # Network-level failure — counts as a transient error
                transient_attempts += 1
                if transient_attempts > _MAX_TRANSIENT_RETRIES:
                    raise TransientError(
                        f"Network error after {transient_attempts} attempts: {exc!s} "
                        f"(endpoint: {method} {url})",
                        url=url,
                        attempts=transient_attempts,
                    ) from exc

                delay = compute_backoff_delay(transient_attempts)
                log.warning(
                    "%s %s -> network error (%s), transient retry %d/%d in %.1fs",
                    method,
                    url,
                    type(exc).__name__,
                    transient_attempts,
                    _MAX_TRANSIENT_RETRIES,
                    delay,
                )
                await asyncio.sleep(delay)
                continue

            status = response.status_code

            # 401: Auth failure — no retry
            if status == 401:
                raise AuthenticationError(
                    f"Authentication failed (401) for {method} {url}. "
                    "Check BITBUCKET_EMAIL and BITBUCKET_API_TOKEN credentials.",
                    status_code=401,
                    url=url,
                )

            # 403: Insufficient permissions — no retry
            if status == 403:
                raise InsufficientPermissionsError(
                    f"Insufficient permissions (403) for {method} {url}. "
                    "The API token lacks the required scope for this operation.",
                    status_code=403,
                    url=url,
                )

            # 429: Rate limited — use Retry-After, independent counter
            if status == 429:
                rate_limit_attempts += 1
                if rate_limit_attempts > _MAX_RATE_LIMIT_RETRIES:
                    raise RateLimitError(
                        f"Rate limited (429) after {rate_limit_attempts} attempts "
                        f"for {method} {url}.",
                        url=url,
                        attempts=rate_limit_attempts,
                    )

                wait = parse_retry_after(response)
                log.warning(
                    "%s %s -> 429 rate limited, rate-limit retry %d/%d in %.1fs",
                    method,
                    url,
                    rate_limit_attempts,
                    _MAX_RATE_LIMIT_RETRIES,
                    wait,
                )
                await asyncio.sleep(wait)
                continue

            # 5xx: Transient server error — exponential backoff
            if status in _TRANSIENT_STATUSES:
                transient_attempts += 1
                if transient_attempts > _MAX_TRANSIENT_RETRIES:
                    raise TransientError(
                        f"Server error ({status}) after {transient_attempts} attempts "
                        f"for {method} {url}.",
                        status_code=status,
                        url=url,
                        attempts=transient_attempts,
                    )

                delay = compute_backoff_delay(transient_attempts)
                log.warning(
                    "%s %s -> %d, transient retry %d/%d in %.1fs",
                    method,
                    url,
                    status,
                    transient_attempts,
                    _MAX_TRANSIENT_RETRIES,
                    delay,
                )
                await asyncio.sleep(delay)
                continue

            # Any other non-success status — fail immediately
            if status >= 400:
                detail = (response.text or "")[:200].replace("\n", " ").strip()
                raise BitbucketClientError(
                    f"HTTP {status} for {method} {url}: {detail}",
                    status_code=status,
                    url=url,
                )

            # Success
            return response
