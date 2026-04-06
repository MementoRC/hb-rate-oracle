"""Unit tests for rate_oracle.core.utils."""

from decimal import Decimal

import pytest

from rate_oracle.core.utils import (
    async_ttl_cache,
    combine_trading_pair,
    find_rate,
    split_trading_pair,
    unwrap_token_symbol,
)


class TestSplitTradingPair:
    def test_split_trading_pair(self):
        base, quote = split_trading_pair("BTC-USD")
        assert base == "BTC"
        assert quote == "USD"

    def test_split_trading_pair_three_letter(self):
        base, quote = split_trading_pair("ETH-USDT")
        assert base == "ETH"
        assert quote == "USDT"

    def test_split_trading_pair_no_quote(self):
        base, quote = split_trading_pair("BTC")
        assert base == "BTC"
        assert quote == ""

    def test_split_trading_pair_preserves_case(self):
        base, quote = split_trading_pair("wETH-BTC")
        assert base == "wETH"
        assert quote == "BTC"


class TestCombineTradingPair:
    def test_combine_trading_pair(self):
        result = combine_trading_pair("BTC", "USD")
        assert result == "BTC-USD"

    def test_combine_trading_pair_various(self):
        assert combine_trading_pair("ETH", "USDT") == "ETH-USDT"
        assert combine_trading_pair("SOL", "BTC") == "SOL-BTC"

    def test_combine_roundtrip(self):
        pair = "XRP-EUR"
        base, quote = split_trading_pair(pair)
        assert combine_trading_pair(base, quote) == pair


class TestUnwrapTokenSymbol:
    def test_unwrap_weth(self):
        assert unwrap_token_symbol("wETH") == "ETH"

    def test_unwrap_wbtc(self):
        assert unwrap_token_symbol("wBTC") == "BTC"

    def test_btc_stays_btc(self):
        assert unwrap_token_symbol("BTC") == "BTC"

    def test_eth_stays_eth(self):
        assert unwrap_token_symbol("ETH") == "ETH"

    def test_lowercase_w_no_upper_next(self):
        # "wabc" — second char is lowercase, not a wrapper prefix
        assert unwrap_token_symbol("wabc") == "wabc"

    def test_single_char_w(self):
        # Just "w" — too short to unwrap
        assert unwrap_token_symbol("w") == "w"

    def test_usdt_stays_usdt(self):
        assert unwrap_token_symbol("USDT") == "USDT"


class TestFindRate:
    def test_find_rate_direct(self):
        prices = {"BTC-USD": Decimal("50000"), "ETH-USD": Decimal("3000")}
        assert find_rate(prices, "BTC-USD") == Decimal("50000")

    def test_find_rate_reverse(self):
        prices = {"USD-BTC": Decimal("0.00002")}
        result = find_rate(prices, "BTC-USD")
        assert result == Decimal("1") / Decimal("0.00002")

    def test_find_rate_same_token(self):
        prices = {"BTC-USD": Decimal("50000")}
        result = find_rate(prices, "ETH-ETH")
        assert result == Decimal("1")

    def test_find_rate_same_token_after_unwrap(self):
        # wETH-ETH: after unwrap both become ETH
        prices = {}
        result = find_rate(prices, "wETH-ETH")
        assert result == Decimal("1")

    def test_find_rate_one_hop(self):
        # BTC-USD via BTC-ETH and ETH-USD
        prices = {
            "BTC-ETH": Decimal("16"),
            "ETH-USD": Decimal("3000"),
        }
        result = find_rate(prices, "BTC-USD")
        assert result == Decimal("16") * Decimal("3000")

    def test_find_rate_one_hop_via_reverse_link(self):
        # BTC-USD via BTC-ETH and USD-ETH (reverse link)
        prices = {
            "BTC-ETH": Decimal("16"),
            "USD-ETH": Decimal("0.00033333"),
        }
        result = find_rate(prices, "BTC-USD")
        expected = Decimal("16") / Decimal("0.00033333")
        assert result == expected

    def test_find_rate_not_found(self):
        prices = {"ETH-USD": Decimal("3000")}
        result = find_rate(prices, "XRP-BTC")
        assert result == Decimal("0")

    def test_find_rate_empty_prices(self):
        assert find_rate({}, "BTC-USD") == Decimal("0")


class TestAsyncTtlCache:
    @pytest.mark.asyncio
    async def test_async_ttl_cache_returns_value(self):
        call_count = 0

        @async_ttl_cache(ttl=60, maxsize=10)
        async def fetch(x):
            nonlocal call_count
            call_count += 1
            return x * 2

        result = await fetch(5)
        assert result == 10
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_async_ttl_cache_caches(self):
        call_count = 0

        @async_ttl_cache(ttl=60, maxsize=10)
        async def fetch(x):
            nonlocal call_count
            call_count += 1
            return x * 2

        await fetch(3)
        await fetch(3)
        assert call_count == 1  # second call hits cache

    @pytest.mark.asyncio
    async def test_async_ttl_cache_different_args(self):
        call_count = 0

        @async_ttl_cache(ttl=60, maxsize=10)
        async def fetch(x):
            nonlocal call_count
            call_count += 1
            return x * 2

        r1 = await fetch(1)
        r2 = await fetch(2)
        assert r1 == 2
        assert r2 == 4
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_async_ttl_cache_clear(self):
        call_count = 0

        @async_ttl_cache(ttl=60, maxsize=10)
        async def fetch(x):
            nonlocal call_count
            call_count += 1
            return x

        await fetch(7)
        fetch.cache_clear()
        await fetch(7)
        assert call_count == 2  # cache was cleared, refetched
