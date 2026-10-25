"""Unit tests for rate_oracle.sources.rate_limit."""

from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest
from rate_limit.testing import ManualClock

from rate_oracle.sources.rate_limit import (
    DEFAULT_BACKOFF_SECONDS,
    MAX_RETRY_AFTER,
    RateLimitedError,
    build_limiter,
    paced_get,
    requests_per_minute,
)

LIMIT_ID = "test"
URL = "https://example.test/api"


def _response(status: int, headers: dict | None = None, body=None):
    resp = AsyncMock()
    resp.status = status
    resp.headers = headers or {}
    resp.json = AsyncMock(return_value=body)
    resp.raise_for_status = MagicMock()
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=resp)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


def _session(*responses):
    session = MagicMock()
    session.get = MagicMock(side_effect=list(responses))
    return session


def _limiter(requests: int = 10):
    clock = ManualClock()
    limiter = build_limiter(clock=clock, sleep=clock.sleep)
    limiter.add_limit(requests_per_minute(LIMIT_ID, requests))
    return limiter, clock


async def _get(limiter, session):
    return await paced_get(limiter, LIMIT_ID, session, URL, params=None, headers={}, source="Test")


class TestRateLimitedError:
    def test_is_oserror_and_carries_retry_after(self):
        err = RateLimitedError(120.0)
        assert isinstance(err, OSError)
        assert err.retry_after == 120.0


class TestRequestsPerMinute:
    def test_token_bucket_over_one_minute(self):
        limit = requests_per_minute(LIMIT_ID, 50)
        assert (limit.limit, limit.time_interval, limit.kind) == (50, 60.0, "token_bucket")


class TestPacing:
    async def test_burst_up_to_capacity_does_not_wait(self):
        limiter, clock = _limiter(requests=3)
        session = _session(*[_response(200, body={"ok": 1}) for _ in range(3)])

        for _ in range(3):
            assert await _get(limiter, session) == {"ok": 1}

        assert clock.sleeps == []

    async def test_request_beyond_capacity_waits_for_refill(self):
        limiter, clock = _limiter(requests=3)  # 3 per 60s -> one token per 20s
        session = _session(*[_response(200, body={}) for _ in range(4)])

        for _ in range(4):
            await _get(limiter, session)

        assert clock.sleeps == [pytest.approx(20.0)]
        assert session.get.call_count == 4

    async def test_unsent_request_refunds_its_token(self):
        limiter, clock = _limiter(requests=1)
        refused = aiohttp.ClientConnectorError(MagicMock(), OSError("refused"))
        session = _session(refused, _response(200, body={}))

        with pytest.raises(aiohttp.ClientConnectorError):
            await _get(limiter, session)
        await _get(limiter, session)

        assert clock.sleeps == []  # the single token came back

    async def test_sent_request_failure_keeps_its_token(self):
        limiter, clock = _limiter(requests=1)
        session = _session(aiohttp.ServerDisconnectedError(), _response(200, body={}))

        with pytest.raises(aiohttp.ServerDisconnectedError):
            await _get(limiter, session)
        await _get(limiter, session)

        assert clock.sleeps == [pytest.approx(60.0)]


class TestThrottling:
    async def test_429_raises_and_pauses_from_retry_after(self):
        limiter, clock = _limiter()
        session = _session(_response(429, {"Retry-After": "120"}))

        with pytest.raises(RateLimitedError) as exc_info:
            await _get(limiter, session)

        assert exc_info.value.retry_after == 120.0
        assert limiter.is_paused(LIMIT_ID)
        clock.advance(119.0)
        assert limiter.is_paused(LIMIT_ID)
        clock.advance(2.0)
        assert not limiter.is_paused(LIMIT_ID)
        assert clock.sleeps == []

    async def test_429_without_header_uses_default_backoff(self):
        limiter, _ = _limiter()

        with pytest.raises(RateLimitedError) as exc_info:
            await _get(limiter, _session(_response(429)))

        assert exc_info.value.retry_after == DEFAULT_BACKOFF_SECONDS

    async def test_consecutive_429s_escalate_up_to_cap(self):
        limiter, clock = _limiter()
        delays = []
        for _ in range(6):
            with pytest.raises(RateLimitedError) as exc_info:
                await _get(limiter, _session(_response(429)))
            delays.append(exc_info.value.retry_after)
            clock.advance(MAX_RETRY_AFTER + 1)

        assert delays[:2] == [DEFAULT_BACKOFF_SECONDS, DEFAULT_BACKOFF_SECONDS * 2]
        assert delays[-1] == MAX_RETRY_AFTER

    async def test_retry_after_is_capped(self):
        limiter, _ = _limiter()

        with pytest.raises(RateLimitedError) as exc_info:
            await _get(limiter, _session(_response(429, {"Retry-After": "999999"})))

        assert exc_info.value.retry_after == MAX_RETRY_AFTER

    async def test_success_resets_backoff_streak(self):
        limiter, clock = _limiter()
        with pytest.raises(RateLimitedError):
            await _get(limiter, _session(_response(429)))
        clock.advance(MAX_RETRY_AFTER)
        await _get(limiter, _session(_response(200, body={})))

        with pytest.raises(RateLimitedError) as exc_info:
            await _get(limiter, _session(_response(429)))

        assert exc_info.value.retry_after == DEFAULT_BACKOFF_SECONDS

    async def test_request_during_backoff_raises_without_http_or_sleep(self):
        limiter, clock = _limiter()
        with pytest.raises(RateLimitedError):
            await _get(limiter, _session(_response(429, {"Retry-After": "120"})))
        session = _session()
        clock.advance(20.0)

        with pytest.raises(RateLimitedError) as exc_info:
            await _get(limiter, session)

        assert exc_info.value.retry_after == pytest.approx(100.0)
        session.get.assert_not_called()
        assert clock.sleeps == []
