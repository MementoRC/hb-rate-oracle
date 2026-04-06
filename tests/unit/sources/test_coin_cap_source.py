"""Unit tests for rate_oracle.sources.coin_cap_source.CoinCapRateSource."""

import logging
from decimal import Decimal

import pytest

from rate_oracle.sources.coin_cap_source import CoinCapRateSource


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
        source = CoinCapRateSource(assets_map=assets_map)

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
        source = CoinCapRateSource(assets_map=assets_map)

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
        source = CoinCapRateSource(assets_map=assets_map)

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
        source = CoinCapRateSource(assets_map=assets_map)
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
        source = CoinCapRateSource(assets_map=assets_map)

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
        source = CoinCapRateSource(assets_map={"bitcoin": "BTC"})

        with caplog.at_level(logging.WARNING, logger="rate_oracle.sources.coin_cap_source"):
            prices = await source.get_prices(quote_token="EUR")

        assert prices == {}
        assert any("USD" in record.message for record in caplog.records)

    @pytest.mark.asyncio
    async def test_get_prices_lowercase_usd_is_accepted(self):
        """'usd' (lowercase) is treated as USD."""
        assets_map = {"bitcoin": "BTC"}
        source = CoinCapRateSource(assets_map=assets_map)

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
        source = CoinCapRateSource(assets_map=assets_map)

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
        """HTTP errors are caught and return empty dict."""
        assets_map = {"bitcoin": "BTC"}
        source = CoinCapRateSource(assets_map=assets_map)

        async def mock_request(endpoint, params=None):
            raise Exception("Connection refused")

        source._request = mock_request

        prices = await source.get_prices(quote_token="USD")
        assert prices == {}
