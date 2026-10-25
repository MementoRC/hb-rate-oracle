"""Unit tests for rate_oracle.sources.coin_gecko_source.CoinGeckoRateSource."""

import asyncio
import logging
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from rate_oracle.sources import coin_gecko_source
from rate_oracle.sources.coin_gecko_source import (
    COOLOFF_AFTER_BAN,
    CoinGeckoAPITier,
    CoinGeckoRateSource,
)
from rate_oracle.sources.rate_limit import RateLimitedError


def _make_coin(symbol: str, price: float) -> dict:
    return {"symbol": symbol, "current_price": price, "id": symbol.lower()}


def _make_mock_response(json_data, status=200):
    """Create a mock aiohttp response context manager."""
    resp = AsyncMock()
    resp.status = status
    resp.json = AsyncMock(return_value=json_data)
    resp.raise_for_status = MagicMock()
    # Make it usable as async context manager
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=resp)
    cm.__aexit__ = AsyncMock(return_value=False)
    return resp, cm


def _make_429_response(retry_after: str | None):
    resp, cm = _make_mock_response(None, status=429)
    resp.headers = {"Retry-After": retry_after} if retry_after is not None else {}
    return cm


def _make_ok_response(json_data):
    _, cm = _make_mock_response(json_data)
    return cm


def _make_session(response_cm):
    session = MagicMock()
    session.closed = False
    session.get = MagicMock(return_value=response_cm)
    return session


class TestCoinGeckoRateSourceName:
    def test_name(self):
        source = CoinGeckoRateSource()
        assert source.name == "coin_gecko"


class TestCoinGeckoAPITiers:
    def test_public_tier(self):
        tier = CoinGeckoAPITier.PUBLIC
        assert tier.tier_name == "public"
        assert tier.header_key == ""
        assert "coingecko.com" in tier.base_url
        assert tier.rate_limit == 10

    def test_demo_tier(self):
        tier = CoinGeckoAPITier.DEMO
        assert tier.tier_name == "demo"
        assert tier.header_key == "x-cg-demo-api-key"
        assert tier.rate_limit == 50

    def test_pro_tier(self):
        tier = CoinGeckoAPITier.PRO
        assert tier.tier_name == "pro"
        assert tier.header_key == "x-cg-pro-api-key"
        assert "pro-api" in tier.base_url
        assert tier.rate_limit == 500

    def test_source_uses_public_by_default(self):
        source = CoinGeckoRateSource()
        assert source._api_tier == CoinGeckoAPITier.PUBLIC

    def test_source_accepts_pro_tier(self):
        source = CoinGeckoRateSource(api_key="test_key", api_tier=CoinGeckoAPITier.PRO)
        assert source._api_tier == CoinGeckoAPITier.PRO

    def test_get_headers_with_api_key(self):
        source = CoinGeckoRateSource(api_key="mykey", api_tier=CoinGeckoAPITier.DEMO)
        headers = source._get_headers()
        assert headers == {"x-cg-demo-api-key": "mykey"}

    def test_get_headers_public_no_key(self):
        source = CoinGeckoRateSource()
        headers = source._get_headers()
        assert headers == {}


class TestCoinGeckoGetPricesSuccess:
    @pytest.mark.asyncio
    async def test_get_prices_success(self):
        """get_prices returns parsed prices on successful HTTP response."""
        page_data = [
            _make_coin("btc", 50000.0),
            _make_coin("eth", 3000.0),
        ]
        source = CoinGeckoRateSource()
        # Patch _get_prices_page to return data on page 1 then empty for pages 2-7
        call_count = 0

        async def mock_get_page(vs_currency, page):
            nonlocal call_count
            call_count += 1
            if page == 1:
                return page_data
            return []

        source._get_prices_page = mock_get_page
        source._extra_token_ids = []

        # Clear the TTL cache so our mock is actually called
        source._fetch_prices.cache_clear()

        prices = await source.get_prices(quote_token="USD")

        assert "BTC-USD" in prices
        assert "ETH-USD" in prices
        assert prices["BTC-USD"] == Decimal("50000.0")
        assert prices["ETH-USD"] == Decimal("3000.0")

    @pytest.mark.asyncio
    async def test_get_prices_upcases_symbol(self):
        """Symbols from API are uppercased in the resulting pair key."""
        source = CoinGeckoRateSource()

        async def mock_get_page(vs_currency, page):
            if page == 1:
                return [{"symbol": "sol", "current_price": 100.0}]
            return []

        source._get_prices_page = mock_get_page
        source._extra_token_ids = []
        source._fetch_prices.cache_clear()

        prices = await source.get_prices(quote_token="USD")
        assert "SOL-USD" in prices

    @pytest.mark.asyncio
    async def test_get_prices_skips_none_price(self):
        """Coins with null current_price are skipped."""
        source = CoinGeckoRateSource()

        async def mock_get_page(vs_currency, page):
            if page == 1:
                return [
                    {"symbol": "btc", "current_price": None},
                    {"symbol": "eth", "current_price": 3000.0},
                ]
            return []

        source._get_prices_page = mock_get_page
        source._extra_token_ids = []
        source._fetch_prices.cache_clear()

        prices = await source.get_prices(quote_token="USD")
        assert "BTC-USD" not in prices
        assert "ETH-USD" in prices


class TestCoinGeckoGetPricesRateLimited:
    @pytest.mark.asyncio
    async def test_get_prices_rate_limited(self):
        """A RateLimitedError breaks the page loop, skips extra ids and sets backoff."""
        source = CoinGeckoRateSource(extra_token_ids=["pepe"])
        by_ids_called = []

        async def mock_get_page(vs_currency, page):
            raise RateLimitedError(120.0)

        async def mock_get_by_ids(vs_currency, token_ids):
            by_ids_called.append(True)
            return []

        source._get_prices_page = mock_get_page
        source._get_prices_by_ids = mock_get_by_ids
        source._fetch_prices.cache_clear()

        # Should not raise — the exception is caught per-page and breaks
        prices = await source.get_prices(quote_token="USD")
        assert prices == {}
        assert by_ids_called == []
        assert source._rate_limited_until > 0.0

    @pytest.mark.asyncio
    async def test_request_429_raises_without_sleeping(self, monkeypatch):
        """A 429 raises RateLimitedError carrying Retry-After and never sleeps."""
        sleep = AsyncMock()
        monkeypatch.setattr(asyncio, "sleep", sleep)
        source = CoinGeckoRateSource()
        source._session = _make_session(_make_429_response("120"))

        with pytest.raises(RateLimitedError) as exc_info:
            await source._request("/coins/markets")

        assert exc_info.value.retry_after == 120.0
        sleep.assert_not_called()

    @pytest.mark.asyncio
    async def test_request_429_without_header_uses_default(self):
        source = CoinGeckoRateSource()
        source._session = _make_session(_make_429_response(None))

        with pytest.raises(RateLimitedError) as exc_info:
            await source._request("/coins/markets")

        assert exc_info.value.retry_after == COOLOFF_AFTER_BAN

    @pytest.mark.asyncio
    async def test_backoff_short_circuits_then_resumes(self, monkeypatch, caplog):
        """429 on page 2: partial returned uncached, no HTTP inside the window, refetch after."""
        clock = [1000.0]
        monkeypatch.setattr(coin_gecko_source, "time", SimpleNamespace(monotonic=lambda: clock[0]))
        sleep = AsyncMock()
        monkeypatch.setattr(asyncio, "sleep", sleep)
        source = CoinGeckoRateSource()
        source._fetch_prices.cache_clear()
        limited = True

        def fake_get(url, params=None, headers=None):
            if limited and params["page"] == "2":
                return _make_429_response("120")
            return _make_ok_response([_make_coin(f"c{params['page']}", float(params["page"]))])

        session = _make_session(None)
        session.get = MagicMock(side_effect=fake_get)
        source._session = session

        with caplog.at_level(logging.WARNING, logger="rate_oracle.sources.coin_gecko_source"):
            partial = await source.get_prices(quote_token="USD")
        assert set(partial) == {"C1-USD"}
        assert session.get.call_count == 2
        sleep.assert_not_called()
        assert sum("rate limit" in r.message.lower() for r in caplog.records) == 1

        # Inside the window: zero HTTP calls, no further warnings
        caplog.clear()
        clock[0] += 119.0
        with caplog.at_level(logging.WARNING, logger="rate_oracle.sources.coin_gecko_source"):
            assert await source.get_prices(quote_token="USD") == {}
        assert session.get.call_count == 2
        assert not caplog.records

        # After the window: fetches again (partial was not cached)
        limited = False
        clock[0] += 2.0
        full = await source.get_prices(quote_token="USD")
        assert session.get.call_count == 2 + 7
        assert len(full) == 7

    @pytest.mark.asyncio
    async def test_get_prices_page_error_stops_pagination(self):
        """An error on page 3 stops fetching further pages."""
        fetched_pages = []
        source = CoinGeckoRateSource()

        async def mock_get_page(vs_currency, page):
            fetched_pages.append(page)
            if page >= 3:
                raise OSError("network error")
            return [_make_coin("btc", 50000.0)]

        source._get_prices_page = mock_get_page
        source._extra_token_ids = []
        source._fetch_prices.cache_clear()

        await source.get_prices(quote_token="USD")
        # Pages 1, 2 succeed; page 3 fails and breaks
        assert fetched_pages == [1, 2, 3]


class TestCoinGeckoGetPricesWithExtraIds:
    @pytest.mark.asyncio
    async def test_get_prices_with_extra_ids(self):
        """Extra token IDs are fetched via _get_prices_by_ids."""
        source = CoinGeckoRateSource(extra_token_ids=["shiba-inu", "pepe"])

        async def mock_get_page(vs_currency, page):
            return []

        async def mock_get_by_ids(vs_currency, token_ids):
            assert "shiba-inu" in token_ids
            assert "pepe" in token_ids
            return [
                {"symbol": "shib", "current_price": 0.00001},
                {"symbol": "pepe", "current_price": 0.000001},
            ]

        source._get_prices_page = mock_get_page
        source._get_prices_by_ids = mock_get_by_ids
        source._fetch_prices.cache_clear()

        prices = await source.get_prices(quote_token="USD")
        assert "SHIB-USD" in prices
        assert "PEPE-USD" in prices

    @pytest.mark.asyncio
    async def test_get_prices_extra_ids_error_does_not_raise(self):
        """Errors fetching extra token IDs are caught and logged."""
        source = CoinGeckoRateSource(extra_token_ids=["bad-id"])

        async def mock_get_page(vs_currency, page):
            return []

        async def mock_get_by_ids(vs_currency, token_ids):
            raise Exception("API error")

        source._get_prices_page = mock_get_page
        source._get_prices_by_ids = mock_get_by_ids
        source._fetch_prices.cache_clear()

        prices = await source.get_prices(quote_token="USD")
        assert prices == {}

    @pytest.mark.asyncio
    async def test_get_prices_no_extra_ids_skips_ids_request(self):
        """When no extra_token_ids are set, _get_prices_by_ids is never called."""
        source = CoinGeckoRateSource(extra_token_ids=[])
        by_ids_called = []

        async def mock_get_page(vs_currency, page):
            return []

        async def mock_get_by_ids(vs_currency, token_ids):
            by_ids_called.append(True)
            return []

        source._get_prices_page = mock_get_page
        source._get_prices_by_ids = mock_get_by_ids
        source._fetch_prices.cache_clear()

        await source.get_prices(quote_token="USD")
        assert by_ids_called == []


class TestCoinGeckoPartialResultsNotCached:
    async def test_page_failure_not_cached(self):
        """A partial result from a failed page is returned but refetched next call."""
        source = CoinGeckoRateSource()
        source._fetch_prices.cache_clear()
        calls: list[int] = []
        fail = True

        async def mock_get_page(vs_currency, page):
            calls.append(page)
            if fail and page == 2:
                raise OSError("network error")
            return [_make_coin(f"c{page}", float(page))]

        source._get_prices_page = mock_get_page

        partial = await source.get_prices(quote_token="USD")
        assert set(partial) == {"C1-USD"}

        fail = False
        calls.clear()
        full = await source.get_prices(quote_token="USD")
        assert calls == [1, 2, 3, 4, 5, 6, 7]
        assert len(full) == 7

    async def test_extra_ids_failure_not_cached(self):
        """A failed extra-ids fetch returns results without extras and is refetched."""
        source = CoinGeckoRateSource(extra_token_ids=["pepe"])
        source._fetch_prices.cache_clear()
        by_ids_calls = 0
        fail = True

        async def mock_get_page(vs_currency, page):
            return [_make_coin("btc", 50000.0)] if page == 1 else []

        async def mock_get_by_ids(vs_currency, token_ids):
            nonlocal by_ids_calls
            by_ids_calls += 1
            if fail:
                raise Exception("API error")
            return [_make_coin("pepe", 0.1)]

        source._get_prices_page = mock_get_page
        source._get_prices_by_ids = mock_get_by_ids

        partial = await source.get_prices(quote_token="USD")
        assert set(partial) == {"BTC-USD"}

        fail = False
        full = await source.get_prices(quote_token="USD")
        assert by_ids_calls == 2
        assert set(full) == {"BTC-USD", "PEPE-USD"}

    async def test_complete_fetch_is_cached(self):
        """A complete fetch is cached; the second call does not hit the fetchers."""
        source = CoinGeckoRateSource(extra_token_ids=["pepe"])
        source._fetch_prices.cache_clear()
        page_calls = 0
        by_ids_calls = 0

        async def mock_get_page(vs_currency, page):
            nonlocal page_calls
            page_calls += 1
            return [_make_coin("btc", 50000.0)] if page == 1 else []

        async def mock_get_by_ids(vs_currency, token_ids):
            nonlocal by_ids_calls
            by_ids_calls += 1
            return [_make_coin("pepe", 0.1)]

        source._get_prices_page = mock_get_page
        source._get_prices_by_ids = mock_get_by_ids

        first = await source.get_prices(quote_token="USD")
        second = await source.get_prices(quote_token="USD")
        assert first == second
        assert page_calls == 7
        assert by_ids_calls == 1


class TestCoinGeckoLastGoodPrices:
    async def test_rate_limited_partial_merges_over_last_good(self, monkeypatch):
        """A 429 mid-cycle keeps last known prices for unfetched pages; backoff returns them."""
        clock = [1000.0]
        monkeypatch.setattr(coin_gecko_source, "time", SimpleNamespace(monotonic=lambda: clock[0]))
        source = CoinGeckoRateSource()
        source._fetch_prices.cache_clear()
        limited = False
        price_scale = 1.0

        async def mock_get_page(vs_currency, page):
            if limited and page == 2:
                raise RateLimitedError(120.0)
            return [_make_coin(f"c{page}", page * price_scale)]

        source._get_prices_page = mock_get_page

        good = await source.get_prices(quote_token="USD")
        assert len(good) == 7

        source._fetch_prices.cache_clear()
        limited = True
        price_scale = 10.0
        merged = await source.get_prices(quote_token="USD")
        assert merged["C1-USD"] == Decimal("10.0")  # fresh from page 1
        assert merged["C2-USD"] == good["C2-USD"]  # last known
        assert len(merged) == 7

        # Partial must not overwrite the last good snapshot
        assert await source.get_prices(quote_token="USD") == good

    async def test_cold_start_backoff_returns_empty(self, monkeypatch):
        clock = [1000.0]
        monkeypatch.setattr(coin_gecko_source, "time", SimpleNamespace(monotonic=lambda: clock[0]))
        source = CoinGeckoRateSource()
        source._fetch_prices.cache_clear()

        async def mock_get_page(vs_currency, page):
            raise RateLimitedError(120.0)

        source._get_prices_page = mock_get_page
        assert await source.get_prices(quote_token="USD") == {}
        assert await source.get_prices(quote_token="USD") == {}
