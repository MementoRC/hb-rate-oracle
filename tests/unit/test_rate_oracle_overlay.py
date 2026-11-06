"""Tests for overlay-contract additions to RateOracle."""

import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from rate_oracle.core.rate_oracle import RateOracle
from rate_oracle.core.rate_source_base import RateSourceBase


def _make_source(prices=None):
    source = MagicMock(spec=RateSourceBase)
    source.name = "mock_source"
    source.get_prices = AsyncMock(return_value=prices or {})
    return source


def test_name():
    assert RateOracle().name == "rate_oracle"


def test_set_price():
    oracle = RateOracle()
    oracle.set_price("BTC-USD", Decimal("5"))
    assert oracle.get_pair_rate("BTC-USD") == Decimal("5")


def test_quote_token_setter_clears_prices():
    oracle = RateOracle()
    oracle.set_price("BTC-USD", Decimal("5"))
    oracle.quote_token = "EUR"
    assert oracle.quote_token == "EUR"
    assert oracle.prices == {}


async def test_rate_async_live_fetch():
    source = _make_source({"BTC-USD": Decimal("50000")})
    oracle = RateOracle(source=source)
    assert await oracle.rate_async("BTC-USD") == Decimal("50000")
    source.get_prices.assert_called_once_with(quote_token="USD")
    assert oracle.prices == {}


async def test_rate_async_no_source():
    assert await RateOracle().rate_async("BTC-USD") == Decimal("0")


async def test_stored_or_live_rate_cached():
    source = _make_source({"BTC-USD": Decimal("1")})
    oracle = RateOracle(source=source)
    oracle.set_price("BTC-USD", Decimal("2"))
    assert await oracle.stored_or_live_rate("BTC-USD") == Decimal("2")
    source.get_prices.assert_not_called()


async def test_stored_or_live_rate_live():
    source = _make_source({"BTC-USD": Decimal("1")})
    oracle = RateOracle(source=source)
    assert await oracle.stored_or_live_rate("BTC-USD") == Decimal("1")
    source.get_prices.assert_called_once()


async def test_get_value():
    oracle = RateOracle()
    oracle.set_price("ETH-USD", Decimal("3000"))
    assert await oracle.get_value(Decimal("2"), "ETH") == Decimal("6000")


async def test_get_ready_set_after_update():
    oracle = RateOracle(source=_make_source({"BTC-USD": Decimal("1")}))
    waiter = asyncio.create_task(oracle.get_ready())
    await asyncio.sleep(0)
    assert not waiter.done()
    await oracle._update_prices()
    await asyncio.wait_for(waiter, timeout=1)


async def test_set_price_survives_update_when_source_omits_pair():
    oracle = RateOracle(source=_make_source({"ETH-USD": Decimal("3000")}))
    oracle.set_price("BTC-USD", Decimal("5"))
    await oracle._update_prices()
    assert oracle.get_pair_rate("BTC-USD") == Decimal("5")
    assert oracle.get_pair_rate("ETH-USD") == Decimal("3000")


async def test_update_overwrites_cached_pair_returned_by_source():
    oracle = RateOracle(source=_make_source({"BTC-USD": Decimal("50000")}))
    oracle.set_price("BTC-USD", Decimal("5"))
    await oracle._update_prices()
    assert oracle.get_pair_rate("BTC-USD") == Decimal("50000")


async def test_ready_not_set_on_empty_prices():
    oracle = RateOracle(source=_make_source({}))
    await oracle._update_prices()
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(oracle.get_ready(), timeout=0.05)
