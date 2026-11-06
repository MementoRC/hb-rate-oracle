"""Tests for rate_oracle.hb_compat RateOracle surface."""

from decimal import Decimal

import pytest

import rate_oracle.hb_compat as hb_compat
from rate_oracle.core.rate_oracle import RateOracle as CoreRateOracle
from rate_oracle.hb_compat.rate_oracle import RateOracle


async def test_sync_start_creates_task_and_stop_cancels():
    oracle = RateOracle()
    oracle.start()
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


def test_start_outside_loop_raises():
    oracle = RateOracle()
    with pytest.raises(RuntimeError, match="running event loop"):
        oracle.start()
    assert oracle._started is False


def test_get_pair_rate_none_on_miss_and_decimal_on_hit():
    oracle = RateOracle()
    assert oracle.get_pair_rate("BTC-USD") is None
    oracle.set_price("BTC-USD", Decimal("5"))
    assert oracle.get_pair_rate("BTC-USD") == Decimal("5")


async def test_start_stop_network():
    oracle = RateOracle()
    await oracle.start_network()
    assert oracle._started is True
    assert oracle._update_task is not None
    await oracle.stop_network()
    assert oracle._started is False
    assert oracle._update_task is None


def test_exports():
    assert issubclass(hb_compat.RateOracle, CoreRateOracle)
    assert hb_compat.RateOracle is RateOracle
    for name in ("RATE_ORACLE_SOURCES", "register_source", "RateConnectorProtocol"):
        assert hasattr(hb_compat, name)
