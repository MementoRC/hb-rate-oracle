"""Unit tests for rate_oracle.sources.coin_cap_source.CoinCapRateSource."""

import asyncio
import logging
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from rate_limit.testing import ManualClock

from rate_oracle.sources.coin_cap_source import (
    BASE_REST_URL,
    FREE_TIER_REQUESTS_PER_MINUTE,
    LIMIT_ID,
    CoinCapRateSource,
)
from rate_oracle.sources.rate_limit import RateLimitedError, build_limiter


def _make_asset(asset_id: str, symbol: str, price_usd: str) -> dict:
    return {"id": asset_id, "symbol": symbol, "priceUsd": price_usd}


class TestCoinCapRateSourceName:
    def test_name(self):
        source = CoinCapRateSource()
        assert source.name == "coin_cap"


class TestCoinCapGetPricesUSD:
    @pytest.mark.asyncio
    async def test_get_prices_usd(self):
        """Returns parsed USD prices for assets in the assets_map."""
        assets_map = {"bitcoin": "BTC", "ethereum": "ETH"}
        source = CoinCapRateSource(assets_map=assets_map, api_key="key")

        async def mock_request(endpoint, params=None):
            return {
                "data": [
                    _make_asset("bitcoin", "BTC", "50000.00"),
                    _make_asset("ethereum", "ETH", "3000.00"),
                ]
            }

        source._request = mock_request

        prices = await source.get_prices(quote_token="USD")

        assert "BTC-USD" in prices
        assert "ETH-USD" in prices
        assert prices["BTC-USD"] == Decimal("50000.00")
        assert prices["ETH-USD"] == Decimal("3000.00")

    @pytest.mark.asyncio
    async def test_get_prices_uses_assets_map_symbol(self):
        """Symbol from assets_map overrides the API symbol."""
        assets_map = {"wrapped-bitcoin": "WBTC"}
        source = CoinCapRateSource(assets_map=assets_map, api_key="key")

        async def mock_request(endpoint, params=None):
            return {
                "data": [
                    _make_asset("wrapped-bitcoin", "wbtc", "49500.00"),
                ]
            }

        source._request = mock_request

        prices = await source.get_prices(quote_token="USD")
        # assets_map symbol "WBTC" takes priority; uppercased
        assert "WBTC-USD" in prices

    @pytest.mark.asyncio
    async def test_get_prices_falls_back_to_api_symbol(self):
        """When asset ID is not in assets_map, uses uppercased API symbol."""
        # No override for 'solana' in the map
        assets_map = {"bitcoin": "BTC"}
        source = CoinCapRateSource(assets_map=assets_map, api_key="key")

        async def mock_request(endpoint, params=None):
            return {
                "data": [
                    _make_asset("bitcoin", "BTC", "50000.00"),
                    _make_asset("solana", "sol", "100.00"),
                ]
            }

        source._request = mock_request

        prices = await source.get_prices(quote_token="USD")
        # solana falls back to uppercased API symbol
        assert "SOL-USD" in prices

    @pytest.mark.asyncio
    async def test_get_prices_passes_ids_param(self):
        """The request includes comma-joined asset IDs from the map."""
        assets_map = {"bitcoin": "BTC", "ethereum": "ETH"}
        source = CoinCapRateSource(assets_map=assets_map, api_key="key")
        captured_params = {}

        async def mock_request(endpoint, params=None):
            captured_params.update(params or {})
            return {"data": []}

        source._request = mock_request

        await source.get_prices(quote_token="USD")

        ids = captured_params.get("ids", "")
        assert "bitcoin" in ids
        assert "ethereum" in ids

    @pytest.mark.asyncio
    async def test_get_prices_skips_none_price(self):
        """Assets with None/missing priceUsd are not included."""
        assets_map = {"bitcoin": "BTC", "badcoin": "BAD"}
        source = CoinCapRateSource(assets_map=assets_map, api_key="key")

        async def mock_request(endpoint, params=None):
            return {
                "data": [
                    _make_asset("bitcoin", "BTC", "50000.00"),
                    {"id": "badcoin", "symbol": "BAD", "priceUsd": None},
                ]
            }

        source._request = mock_request

        prices = await source.get_prices(quote_token="USD")
        assert "BTC-USD" in prices
        assert "BAD-USD" not in prices


class TestCoinCapGetPricesNonUSD:
    @pytest.mark.asyncio
    async def test_get_prices_non_usd_warns(self, caplog):
        """Non-USD quote tokens log a warning and return empty dict."""
        source = CoinCapRateSource(assets_map={"bitcoin": "BTC"}, api_key="key")

        with caplog.at_level(logging.WARNING, logger="rate_oracle.sources.coin_cap_source"):
            prices = await source.get_prices(quote_token="EUR")

        assert prices == {}
        assert any("USD" in record.message for record in caplog.records)

    @pytest.mark.asyncio
    async def test_get_prices_lowercase_usd_is_accepted(self):
        """'usd' (lowercase) is treated as USD."""
        assets_map = {"bitcoin": "BTC"}
        source = CoinCapRateSource(assets_map=assets_map, api_key="key")

        async def mock_request(endpoint, params=None):
            return {"data": [_make_asset("bitcoin", "BTC", "50000.00")]}

        source._request = mock_request

        # lowercase "usd" should still work (quote_token.upper() == "USD")
        prices = await source.get_prices(quote_token="usd")
        assert "BTC-USD" in prices

    @pytest.mark.asyncio
    async def test_get_prices_none_quote_is_accepted(self):
        """None quote_token falls through to USD path (no warning)."""
        assets_map = {"bitcoin": "BTC"}
        source = CoinCapRateSource(assets_map=assets_map, api_key="key")

        async def mock_request(endpoint, params=None):
            return {"data": [_make_asset("bitcoin", "BTC", "50000.00")]}

        source._request = mock_request

        prices = await source.get_prices(quote_token=None)
        assert "BTC-USD" in prices


class TestCoinCapGetPricesEmptyMap:
    @pytest.mark.asyncio
    async def test_get_prices_empty_map(self):
        """Empty assets_map returns empty dict without making any HTTP request."""
        source = CoinCapRateSource(assets_map={})
        request_called = []

        async def mock_request(endpoint, params=None):
            request_called.append(True)
            return {"data": []}

        source._request = mock_request

        prices = await source.get_prices(quote_token="USD")
        assert prices == {}
        assert request_called == []  # no HTTP call made

    @pytest.mark.asyncio
    async def test_get_prices_default_empty_map(self):
        """Default CoinCapRateSource has empty assets_map, returns empty dict."""
        source = CoinCapRateSource()
        prices = await source.get_prices(quote_token="USD")
        assert prices == {}

    @pytest.mark.asyncio
    async def test_get_prices_exception_returns_empty(self):
        """HTTP errors with no prior success are caught and return empty dict."""
        assets_map = {"bitcoin": "BTC"}
        source = CoinCapRateSource(assets_map=assets_map, api_key="key")

        async def mock_request(endpoint, params=None):
            raise Exception("Connection refused")

        source._request = mock_request

        prices = await source.get_prices(quote_token="USD")
        assert prices == {}
        assert not source._limiter.is_paused(LIMIT_ID)


def _make_429_response(retry_after: str | None):
    resp = AsyncMock()
    resp.status = 429
    resp.headers = {"Retry-After": retry_after} if retry_after is not None else {}
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=resp)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


def _make_ok_response(json_data):
    resp = AsyncMock()
    resp.status = 200
    resp.headers = {}
    resp.json = AsyncMock(return_value=json_data)
    resp.raise_for_status = MagicMock()
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=resp)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


def _make_paced_source(
    assets_map: dict[str, str] | None = None,
) -> tuple[CoinCapRateSource, ManualClock]:
    """A source whose limiter runs on a manual clock (sleeping just advances it)."""
    clock = ManualClock()
    limiter = build_limiter(clock=clock, sleep=clock.sleep)
    source = CoinCapRateSource(
        assets_map=assets_map or {"bitcoin": "BTC"},
        api_key="key",
        rate_limiter=limiter,
        clock=clock,
    )
    return source, clock


def _make_session(*responses):
    session = MagicMock()
    session.closed = False
    session.get = MagicMock(side_effect=list(responses))
    return session


class TestCoinCapPacing:
    async def test_budget_is_sent_without_waiting_then_next_waits(self):
        source, clock = _make_paced_source()
        rpm = FREE_TIER_REQUESTS_PER_MINUTE
        source._session = _make_session(*[_make_ok_response({"data": []}) for _ in range(rpm + 1)])

        for _ in range(rpm):
            await source._request("/assets")
        assert clock.sleeps == []

        await source._request("/assets")
        assert clock.sleeps == [pytest.approx(60.0 / rpm)]


class TestCoinCapRateLimited:
    @pytest.mark.asyncio
    async def test_request_429_raises_without_sleeping(self, monkeypatch):
        """A 429 raises RateLimitedError carrying Retry-After and never sleeps."""
        sleep = AsyncMock()
        monkeypatch.setattr(asyncio, "sleep", sleep)
        source = CoinCapRateSource(assets_map={"bitcoin": "BTC"}, api_key="key")
        session = MagicMock()
        session.closed = False
        session.get = MagicMock(return_value=_make_429_response("120"))
        source._session = session

        with pytest.raises(RateLimitedError) as exc_info:
            await source._request("/assets")

        assert exc_info.value.retry_after == 120.0
        sleep.assert_not_called()

    @pytest.mark.asyncio
    async def test_backoff_short_circuits_then_resumes(self, caplog):
        """After a 429, get_prices makes no requests until the window passes."""
        source, clock = _make_paced_source()
        ok = _make_ok_response({"data": [_make_asset("bitcoin", "BTC", "50000.00")]})
        session = _make_session(_make_429_response("120"), ok)
        source._session = session

        with caplog.at_level(logging.WARNING):
            assert await source.get_prices(quote_token="USD") == {}
        assert session.get.call_count == 1
        assert sum("rate limited" in r.message.lower() for r in caplog.records) == 1

        # Inside the window: no request, no further warnings
        caplog.clear()
        clock.advance(119.0)
        with caplog.at_level(logging.WARNING):
            assert await source.get_prices(quote_token="USD") == {}
        assert session.get.call_count == 1
        assert not caplog.records

        # After the window: fetches again
        clock.advance(2.0)
        prices = await source.get_prices(quote_token="USD")
        assert session.get.call_count == 2
        assert "BTC-USD" in prices
        assert clock.sleeps == []

    @pytest.mark.asyncio
    async def test_429_and_backoff_return_last_good_prices(self):
        """A 429 and the following backoff window keep the last successful prices."""
        source, clock = _make_paced_source()
        ok = _make_ok_response({"data": [_make_asset("bitcoin", "BTC", "50000.00")]})
        source._session = _make_session(ok, _make_429_response("120"))

        good = await source.get_prices(quote_token="USD")
        assert good == {"BTC-USD": Decimal("50000.00")}

        clock.advance(31.0)  # past cache ttl -> hits the 429
        assert await source.get_prices(quote_token="USD") == good
        clock.advance(60.0)
        assert await source.get_prices(quote_token="USD") == good

    @pytest.mark.asyncio
    async def test_non_429_error_returns_last_good_prices(self):
        """A generic fetch failure keeps serving the last successful prices."""
        source, clock = _make_paced_source()
        ok = _make_ok_response({"data": [_make_asset("bitcoin", "BTC", "50000.00")]})
        source._session = _make_session(ok, RuntimeError("boom"))

        good = await source.get_prices(quote_token="USD")
        clock.advance(31.0)
        assert await source.get_prices(quote_token="USD") == good


class TestCoinCapV3:
    def test_v3_base_url(self):
        assert BASE_REST_URL == "https://rest.coincap.io/v3"

    @pytest.mark.asyncio
    async def test_request_uses_v3_url_and_bearer(self):
        source, _ = _make_paced_source()
        session = _make_session(_make_ok_response({"data": []}))
        source._session = session

        await source._request("/assets", params={"ids": "bitcoin"})

        assert session.get.call_args.args[0] == "https://rest.coincap.io/v3/assets"
        assert session.get.call_args.kwargs["headers"] == {"Authorization": "Bearer key"}

    @pytest.mark.asyncio
    async def test_keyless_makes_no_request_and_warns_once(self, caplog):
        source = CoinCapRateSource(assets_map={"bitcoin": "BTC"})
        session = _make_session()
        source._session = session

        with caplog.at_level(logging.WARNING):
            for _ in range(3):
                assert await source.get_prices(quote_token="USD") == {}

        session.get.assert_not_called()
        assert sum("api key" in r.message.lower() for r in caplog.records) == 1


class TestCoinCapCaching:
    @pytest.mark.asyncio
    async def test_second_call_within_ttl_is_cached_then_refetched(self):
        source, clock = _make_paced_source()
        session = _make_session(
            _make_ok_response({"data": [_make_asset("bitcoin", "BTC", "50000.00")]}),
            _make_ok_response({"data": [_make_asset("bitcoin", "BTC", "51000.00")]}),
        )
        source._session = session

        first = await source.get_prices(quote_token="USD")
        clock.advance(29.0)
        assert await source.get_prices(quote_token="USD") == first
        assert session.get.call_count == 1

        clock.advance(2.0)
        refreshed = await source.get_prices(quote_token="USD")
        assert session.get.call_count == 2
        assert refreshed == {"BTC-USD": Decimal("51000.00")}

    @pytest.mark.asyncio
    async def test_failures_are_not_cached(self):
        source, _ = _make_paced_source()
        ok = _make_ok_response({"data": [_make_asset("bitcoin", "BTC", "50000.00")]})
        session = _make_session(RuntimeError("boom"), ok)
        source._session = session

        assert await source.get_prices(quote_token="USD") == {}
        assert await source.get_prices(quote_token="USD") == {"BTC-USD": Decimal("50000.00")}
        assert session.get.call_count == 2

    @pytest.mark.parametrize(
        ("rpm", "expected"),
        [(FREE_TIER_REQUESTS_PER_MINUTE, 30.0), (120, 30.0), (1, 60.0)],
    )
    def test_default_ttl(self, rpm, expected):
        source = CoinCapRateSource(api_key="key", requests_per_minute=rpm)
        assert source._cache_ttl == expected

    @pytest.mark.parametrize("rpm", [0, -1])
    def test_requests_per_minute_must_be_positive(self, rpm):
        with pytest.raises(ValueError, match="requests_per_minute"):
            CoinCapRateSource(api_key="key", requests_per_minute=rpm)

    def test_explicit_ttl(self):
        assert CoinCapRateSource(api_key="key", cache_ttl=5.0)._cache_ttl == 5.0

    @pytest.mark.asyncio
    async def test_limiter_sized_from_requests_per_minute(self):
        clock = ManualClock()
        limiter = build_limiter(clock=clock, sleep=clock.sleep)
        source = CoinCapRateSource(api_key="key", requests_per_minute=7, rate_limiter=limiter)
        source._session = _make_session(*[_make_ok_response({"data": []}) for _ in range(8)])

        for _ in range(7):
            await source._request("/assets")
        assert clock.sleeps == []

        await source._request("/assets")
        assert clock.sleeps == [pytest.approx(60.0 / 7)]
