"""Tests for rate_oracle.hb_compat RateOracle surface."""

import asyncio
from decimal import Decimal

import rate_oracle
import rate_oracle.hb_compat as hb_compat
from rate_oracle.core.rate_oracle import RateOracle as CoreRateOracle
from rate_oracle.core.utils import find_rate as core_find_rate
from rate_oracle.hb_compat.rate_oracle import RateOracle


async def test_sync_start_creates_task_and_stop_cancels():
    oracle = RateOracle()
    oracle.start()
    await __import__("asyncio").sleep(0)
    task = oracle._update_task
    assert task is not None
    assert oracle._started is True
    oracle.start()
    assert oracle._update_task is task
    oracle.stop()
    assert oracle._started is False
    assert oracle._update_task is None
    await __import__("asyncio").sleep(0)
    assert task.cancelled()


def test_start_outside_loop_schedules_on_current_loop():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        oracle = RateOracle()
        oracle.start()
        assert oracle._started is True
        assert oracle._start_task is not None
        loop.run_until_complete(asyncio.sleep(0))
        assert oracle._update_task is not None
        loop.run_until_complete(oracle.stop_network())
        assert oracle._update_task is None
    finally:
        loop.close()
        asyncio.set_event_loop(None)


def test_get_pair_rate_none_on_miss_and_decimal_on_hit():
    oracle = RateOracle()
    assert oracle.get_pair_rate("BTC-USD") is None
    oracle.set_price("BTC-USD", Decimal("5"))
    assert oracle.get_pair_rate("BTC-USD") == Decimal("5")


async def test_start_stop_network():
    oracle = RateOracle()
    await oracle.start_network()
    assert oracle._update_task is not None
    await oracle.stop_network()
    assert oracle._update_task is None


class _FakeSource:
    name = "fake"

    def __init__(self, prices: dict[str, Decimal]):
        self._prices = prices

    async def get_prices(self, quote_token: str = "USD") -> dict[str, Decimal]:
        return dict(self._prices)


def test_find_rate_none_on_miss_value_on_hit_and_reverse():
    # In-tree find_rate normalizes USD to USDT, so the reverse case uses a non-USD quote.
    prices = {"BTC-EUR": Decimal("4")}
    assert hb_compat.find_rate(prices, "ETH-EUR") is None
    assert hb_compat.find_rate(prices, "BTC-EUR") == Decimal("4")
    assert hb_compat.find_rate(prices, "EUR-BTC") == Decimal("0.25")


def test_find_rate_identity_hb_compat_vs_core():
    assert hb_compat.find_rate is not rate_oracle.find_rate
    assert rate_oracle.find_rate is core_find_rate


async def test_get_rate_keyword_none_on_miss_decimal_on_hit():
    oracle = RateOracle(source=_FakeSource({"BTC-USD": Decimal("7")}))
    assert await oracle.get_rate(base_token="BTC") == Decimal("7")
    assert await oracle.get_rate("BTC") == Decimal("7")
    assert await oracle.get_rate(base_token="XYZ") is None


async def test_rate_async_none_on_miss():
    oracle = RateOracle(source=_FakeSource({"BTC-USD": Decimal("7")}))
    assert await oracle.rate_async("BTC-USD") == Decimal("7")
    assert await oracle.rate_async("XYZ-USD") is None
    assert await RateOracle().rate_async("BTC-USD") is None


async def test_get_value_zero_on_miss_and_product_on_hit():
    oracle = RateOracle(source=_FakeSource({"BTC-USD": Decimal("7")}))
    assert await oracle.get_value(Decimal("2"), "BTC") == Decimal("14")
    assert await oracle.get_value(Decimal("2"), "XYZ") == Decimal("0")


async def test_stored_or_live_rate_none_on_miss_both_branches():
    live = RateOracle(source=_FakeSource({"BTC-USD": Decimal("7")}))
    assert await live.stored_or_live_rate("XYZ-USD") is None
    assert await live.stored_or_live_rate("BTC-USD") == Decimal("7")

    cached = RateOracle()
    cached.set_price("BTC-USD", Decimal("5"))
    assert await cached.stored_or_live_rate("XYZ-USD") is None
    assert await cached.stored_or_live_rate("BTC-USD") == Decimal("5")


def test_source_public_accessor():
    source = _FakeSource({})
    assert RateOracle(source=source).source is source
    assert RateOracle().source is None


def test_exports():
    assert issubclass(hb_compat.RateOracle, CoreRateOracle)
    assert hb_compat.RateOracle is RateOracle
    for name in ("RATE_ORACLE_SOURCES", "register_source", "RateConnectorProtocol"):
        assert hasattr(hb_compat, name)
