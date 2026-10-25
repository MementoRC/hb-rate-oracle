"""Shared request pacing and HTTP 429 handling for rate sources (built on hb-rate-limit)."""

import asyncio
import time
from typing import Any

import aiohttp
from rate_limit import BackoffPolicy, Clock, RateLimit, RateLimiter, Sleep

# Upper bound for server-supplied Retry-After values (and for escalated backoff), so a bogus
# or hostile header cannot silence a source for hours.
MAX_RETRY_AFTER = 600.0

# First pause after a 429 that carries no usable Retry-After; doubles per consecutive 429.
DEFAULT_BACKOFF_SECONDS = 60.0 * 1.05


class RateLimitedError(OSError):
    """Raised on HTTP 429; carries how long (seconds) the caller should back off."""

    def __init__(self, retry_after: float, message: str = "Rate limited"):
        super().__init__(f"{message} (retry after {retry_after:.0f}s)")
        self.retry_after = retry_after


def build_limiter(*, clock: Clock = time.monotonic, sleep: Sleep = asyncio.sleep) -> RateLimiter:
    """A limiter whose server-supplied Retry-After is capped at MAX_RETRY_AFTER.

    `clock` and `sleep` are injectable so tests can run on a manual clock.
    """
    return RateLimiter(
        clock=clock,
        sleep=sleep,
        max_retry_after_seconds=MAX_RETRY_AFTER,
        backoff_factory=lambda: BackoffPolicy(DEFAULT_BACKOFF_SECONDS, MAX_RETRY_AFTER),
    )


def requests_per_minute(limit_id: str, requests: int) -> RateLimit:
    """A token bucket holding `requests` tokens and refilling them over one minute."""
    return RateLimit(limit_id, requests, 60.0, kind="token_bucket")


async def paced_get(
    limiter: RateLimiter,
    limit_id: str,
    session: aiohttp.ClientSession,
    url: str,
    *,
    params: dict | None,
    headers: dict[str, str],
    source: str,
) -> Any:
    """GET `url` as a paced request and return its JSON body.

    Waits for a token before sending (never while a 429 backoff is active: raises instead),
    feeds the response to the limiter, and raises RateLimitedError when it signals throttling.
    A token is refunded when the connection could not be made, since nothing was sent.
    """
    if limiter.is_paused(limit_id):
        raise RateLimitedError(limiter.blocked_for(limit_id), f"{source} backoff active")
    charge = await limiter.reserve(limit_id)
    try:
        async with session.get(url, params=params, headers=headers) as resp:
            verdict = limiter.report_response(limit_id, resp.status, resp.headers)
            if verdict.rate_limited:
                raise RateLimitedError(verdict.delay, f"Rate limited by {source}")
            resp.raise_for_status()
            return await resp.json()
    except aiohttp.ClientConnectorError:
        charge.refund()
        raise
