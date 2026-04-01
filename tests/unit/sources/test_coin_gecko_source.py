"""Unit tests for rate_oracle.sources.coin_gecko_source.CoinGeckoRateSource."""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from rate_oracle.sources.coin_gecko_source import CoinGeckoAPITier, CoinGeckoRateSource


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
        source.get_prices.cache_clear()

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
        source.get_prices.cache_clear()

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
        source.get_prices.cache_clear()

        prices = await source.get_prices(quote_token="USD")
        assert "BTC-USD" not in prices
        assert "ETH-USD" in prices


class TestCoinGeckoGetPricesRateLimited:
    @pytest.mark.asyncio
    async def test_get_prices_rate_limited(self):
        """A 429 response from _request raises IOError and breaks the page loop."""
        source = CoinGeckoRateSource()

        async def mock_get_page(vs_currency, page):
            raise OSError("Rate limited by CoinGecko")

        source._get_prices_page = mock_get_page
        source._extra_token_ids = []
        source.get_prices.cache_clear()

        # Should not raise — the exception is caught per-page and breaks
        prices = await source.get_prices(quote_token="USD")
        assert prices == {}

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
        source.get_prices.cache_clear()

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
        source.get_prices.cache_clear()

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
        source.get_prices.cache_clear()

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
        source.get_prices.cache_clear()

        await source.get_prices(quote_token="USD")
        assert by_ids_called == []
