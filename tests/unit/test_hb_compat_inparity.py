"""In-tree API parity tests for the hb_compat RateOracle (issue #64)."""

import asyncio
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from rate_oracle.core.rate_source_base import RateSourceBase
from rate_oracle.core.registry import RATE_ORACLE_SOURCES, register_source
from rate_oracle.hb_compat import RateOracle, RateSourceProtocol, find_rate
from rate_oracle.hb_compat import utils as compat_utils

MID = object()


class DummyRateSource:
    """Structural rate source (not a RateSourceBase subclass)."""

    name = "dummy_source"

    def __init__(self, price_dict: dict[str, Decimal] | None = None):
        self.price_dict = price_dict or {}
        self.calls = 0

    async def get_prices(self, quote_token: str | None = None) -> dict[str, Decimal]:
        self.calls += 1
        return dict(self.price_dict)


class BrokenSource(DummyRateSource):
    async def get_prices(self, quote_token: str | None = None) -> dict[str, Decimal]:
        self.calls += 1
        raise RuntimeError("boom")


def make_connector(name: str, books: dict[str, Decimal]) -> MagicMock:
    connector = MagicMock()
    connector.name = name
    connector.order_books = {pair: object() for pair in books}
    connector.get_price_by_type.side_effect = lambda pair, price_type: books[pair]
    return connector


@pytest.fixture(autouse=True)
def reset_state():
    RateOracle._shared_instance = None
    RateOracle.default_source_factory = None
    RateOracle.mid_price_type = None
    yield
    RateOracle._shared_instance = None
    RateOracle.default_source_factory = None
    RateOracle.mid_price_type = None


# --- constructor / hooks / singleton -------------------------------------------------


def test_ctor_defaults():
    oracle = RateOracle()
    assert oracle.source is None
    assert oracle.quote_token == "USD"
    assert oracle._fetch_price_task is None
    assert oracle._connectors == {}


def test_ctor_kwargs():
    source = DummyRateSource()
    oracle = RateOracle(source=source, quote_token="USDT")
    assert oracle.source is source
    assert oracle.quote_token == "USDT"


def test_default_source_factory_hook():
    made = DummyRateSource()
    RateOracle.default_source_factory = lambda: made
    assert RateOracle().source is made
    explicit = DummyRateSource()
    assert RateOracle(source=explicit).source is explicit


def test_get_instance_identity_and_reset():
    first = RateOracle.get_instance()
    assert RateOracle.get_instance() is first
    RateOracle._shared_instance = None
    assert RateOracle.get_instance() is not first


def test_name_and_str():
    assert RateOracle().name == "rate_oracle"
    assert str(RateOracle(source=DummyRateSource())) == "dummy_source rate oracle"
    assert "rate oracle" in str(RateOracle())


def test_quote_token_setter_clears_prices_only_on_change():
    oracle = RateOracle(quote_token="USD")
    oracle.set_price("BTC-USD", Decimal("1"))
    oracle.quote_token = "USD"
    assert oracle.prices == {"BTC-USD": Decimal("1")}
    oracle.quote_token = "EUR"
    assert oracle.quote_token == "EUR"
    assert oracle.prices == {}


def test_source_setter_plain_assign():
    oracle = RateOracle()
    source = DummyRateSource()
    oracle.source = source
    assert oracle.source is source


# --- lifecycle ----------------------------------------------------------------------


async def test_network_flow():
    source = DummyRateSource({"SOMETOKEN-USD": Decimal("100")})
    oracle = RateOracle(source=source)
    oracle.start()
    await oracle.get_ready()
    assert oracle.prices
    assert oracle.get_pair_rate("SOMETOKEN-USD") == Decimal("100")
    await oracle.stop_network()
    assert oracle._fetch_price_task is None


async def test_start_is_sync_and_returns_none():
    oracle = RateOracle(source=DummyRateSource({"A-USD": Decimal("1")}))
    assert oracle.start() is None
    assert oracle._started is True
    await oracle.get_ready()
    assert oracle.stop() is None
    assert oracle._started is False
    assert oracle._fetch_price_task is None


def test_start_without_loop_raises():
    with pytest.raises(RuntimeError, match="running event loop"):
        RateOracle().start()


async def test_start_network_after_start_restarts_fetching():
    source = DummyRateSource({"A-USD": Decimal("1")})
    oracle = RateOracle(source=source)
    oracle.start()
    await oracle.get_ready()
    old_task = oracle._fetch_price_task
    assert oracle._started is True
    await oracle.start_network()
    assert oracle._fetch_price_task is not None
    assert oracle._fetch_price_task is not old_task
    await asyncio.sleep(0)
    assert old_task.cancelled()
    calls = source.calls
    await asyncio.sleep(1.2)
    assert source.calls > calls
    oracle.stop()


async def test_single_fetch_task_alias():
    oracle = RateOracle(source=DummyRateSource())
    await oracle.start_network()
    assert oracle._update_task is oracle._fetch_price_task
    await oracle.stop_network()
    assert oracle._update_task is None


async def test_stop_network_cancels_task():
    oracle = RateOracle(source=DummyRateSource())
    await oracle.start_network()
    task = oracle._fetch_price_task
    await oracle.stop_network()
    await asyncio.sleep(0)
    assert task.cancelled()
    assert oracle._fetch_price_task is None
    await oracle.stop_network()


async def test_fetch_loop_merges_prices():
    oracle = RateOracle(source=DummyRateSource({"A-USD": Decimal("2")}))
    oracle.set_price("B-USD", Decimal("3"))
    await oracle.start_network()
    await oracle.get_ready()
    assert oracle.prices == {"A-USD": Decimal("2"), "B-USD": Decimal("3")}
    await oracle.stop_network()


async def test_fetch_loop_survives_errors():
    source = BrokenSource()
    oracle = RateOracle(source=source)
    await oracle.start_network()
    await asyncio.sleep(0.05)
    assert source.calls >= 1
    assert oracle._fetch_price_task is not None
    assert not oracle._fetch_price_task.done()
    assert oracle.prices == {}
    await oracle.stop_network()


async def test_fetch_loop_without_source_does_not_crash():
    oracle = RateOracle()
    await oracle.start_network()
    await asyncio.sleep(0.01)
    assert not oracle._fetch_price_task.done()
    await oracle.stop_network()


async def test_get_ready_reraises_cancelled():
    oracle = RateOracle()
    task = asyncio.ensure_future(oracle.get_ready())
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


async def test_get_ready_logs_other_exceptions():
    oracle = RateOracle()
    oracle._ready_event = MagicMock()
    oracle._ready_event.is_set.return_value = False

    async def fail():
        raise ValueError("x")

    oracle._ready_event.wait = fail
    await oracle.get_ready()


# --- connectors ---------------------------------------------------------------------


def test_register_unregister_connector():
    oracle = RateOracle()
    connector = make_connector("binance", {})
    oracle.register_connector(connector)
    assert oracle._connectors == {"binance": connector}
    oracle.unregister_connector(connector)
    assert oracle._connectors == {}
    oracle.unregister_connector(connector)


def test_connector_direct_pair_passes_mid_price_type():
    RateOracle.mid_price_type = MID
    oracle = RateOracle(source=DummyRateSource())
    connector = make_connector("binance", {"BTC-USDT": Decimal("10")})
    oracle.register_connector(connector)
    assert oracle.get_pair_rate("BTC-USDT") == Decimal("10")
    connector.get_price_by_type.assert_called_with("BTC-USDT", MID)


def test_connector_reverse_pair():
    oracle = RateOracle()
    oracle.register_connector(make_connector("binance", {"USDT-BTC": Decimal("4")}))
    assert oracle.get_pair_rate("BTC-USDT") == Decimal("0.25")


def test_connector_reverse_zero_skipped():
    oracle = RateOracle()
    oracle.register_connector(make_connector("binance", {"USDT-BTC": Decimal("0")}))
    assert oracle.get_pair_rate("BTC-USDT") is None


def test_source_preferred_over_connectors():
    oracle = RateOracle()
    oracle.set_price("BTC-USDT", Decimal("7"))
    connector = make_connector("binance", {"BTC-USDT": Decimal("10")})
    oracle.register_connector(connector)
    assert oracle.get_pair_rate("BTC-USDT") == Decimal("7")
    connector.get_price_by_type.assert_not_called()


def test_reverse_on_source_after_connector_miss():
    oracle = RateOracle()
    oracle.set_price("USDT-BTC", Decimal("4"))
    oracle.register_connector(make_connector("binance", {"ETH-USDT": Decimal("2")}))
    assert oracle.get_pair_rate("BTC-USDT") == Decimal("0.25")


def test_none_when_no_route():
    oracle = RateOracle()
    oracle.register_connector(make_connector("binance", {"ETH-USDT": Decimal("2")}))
    assert oracle.get_pair_rate("BTC-USDT") is None
    assert RateOracle().get_pair_rate("BTC-USDT") is None


def test_connector_name_order_is_deterministic():
    oracle = RateOracle()
    oracle.register_connector(make_connector("zeta", {"BTC-USDT": Decimal("2")}))
    oracle.register_connector(make_connector("alpha", {"BTC-USDT": Decimal("1")}))
    assert oracle.get_pair_rate("BTC-USDT") == Decimal("1")


def test_connector_without_order_books_ignored():
    oracle = RateOracle()
    bare = SimpleNamespace(name="bare")
    oracle.register_connector(bare)  # type: ignore[arg-type]
    assert oracle.get_pair_rate("BTC-USDT") is None


# --- registry -----------------------------------------------------------------------


class StructuralSource:
    name = "structural"

    async def get_prices(self, quote_token=None):
        return {}


class NoCoroutine:
    name = "nope"

    def get_prices(self, quote_token=None):
        return {}


class NoName:
    async def get_prices(self, quote_token=None):
        return {}


def test_registry_accepts_structural_class():
    try:
        register_source("structural_test", StructuralSource)
        assert RATE_ORACLE_SOURCES["structural_test"] is StructuralSource
    finally:
        RATE_ORACLE_SOURCES.pop("structural_test", None)


@pytest.mark.parametrize("bad", [dict, NoCoroutine, NoName, StructuralSource()])
def test_registry_rejects_non_conforming(bad):
    with pytest.raises(TypeError):
        register_source("bad_test", bad)  # type: ignore[arg-type]
    assert "bad_test" not in RATE_ORACLE_SOURCES


def test_registry_rejects_abstract_class():
    class Abstract(RateSourceBase):
        pass

    with pytest.raises(TypeError):
        register_source("abstract_test", Abstract)  # type: ignore[arg-type]
    assert "abstract_test" not in RATE_ORACLE_SOURCES


# --- alias exports ------------------------------------------------------------------


def test_rate_oracle_module_reexports():
    from rate_oracle.hb_compat import rate_oracle as module

    assert module.RATE_ORACLE_SOURCES is RATE_ORACLE_SOURCES
    assert module.RateOracle is RateOracle


# --- find_rate (ported from upstream) -----------------------------------------------


def test_find_rate():
    prices = {"HBOT-USDT": Decimal("100"), "AAVE-USDT": Decimal("50"), "USDT-GBP": Decimal("0.75")}
    assert find_rate(prices, "HBOT-USDT") == Decimal("100")
    assert find_rate(prices, "ZBOT-USDT") is None
    assert find_rate(prices, "USDT-HBOT") == Decimal("0.01")
    assert find_rate(prices, "HBOT-AAVE") == Decimal("2")
    assert find_rate(prices, "AAVE-HBOT") == Decimal("0.5")
    assert find_rate(prices, "HBOT-GBP") == Decimal("75")


def test_find_rate_unwraps_usd_quote_to_usdt():
    prices = {"HYPE-USDT": Decimal("60"), "SOL-USDT": Decimal("70")}
    assert find_rate(prices, "HYPE-USD") == Decimal("60")
    assert find_rate(prices, "SOL-USD") == Decimal("70")
    assert find_rate(prices, "USD-USDT") == Decimal("1")
    assert find_rate(prices, "USDT-USD") == Decimal("1")


def test_find_rate_usd_equivalence_is_a_fallback_not_an_override():
    assert find_rate({"USDT-USD": Decimal("0.999")}, "USDT-USD") == Decimal("0.999")
    with patch.object(compat_utils, "USD_EQUIVALENT_TOKENS", []):
        assert find_rate({"USDT-USD": Decimal("0.999")}, "USDT-USD") == Decimal("0.999")
    prices = {"HYPE-USDT": Decimal("60")}
    with patch.object(compat_utils, "USD_EQUIVALENT_TOKENS", []):
        assert find_rate(prices, "HYPE-USD") is None
        assert find_rate(prices, "USD-USDT") is None
        assert find_rate(prices, "USDT-USD") is None


def test_find_rate_skips_zero_prices():
    assert find_rate({"SOL-FARTCOIN": Decimal("0")}, "FARTCOIN-SOL") is None
    zero_common = {"HBOT-USDT": Decimal("100"), "GBP-USDT": Decimal("0")}
    assert find_rate(zero_common, "HBOT-GBP") is None
    assert find_rate({"FARTCOIN-SOL": Decimal("0")}, "FARTCOIN-SOL") == Decimal("0")


def test_find_rate_no_lowercase_w_unwrap():
    assert find_rate({"ETH-USDT": Decimal("2")}, "wETH-USDT") is None


# --- live get_rate / rate_async / lifecycle fixes -----------------------------------


async def test_get_rate_is_live_without_side_effects():
    source = DummyRateSource({"BTC-USD": Decimal("7")})
    oracle = RateOracle(source=source)
    assert await oracle.get_rate(base_token="BTC") == Decimal("7")
    assert source.calls == 1
    assert oracle.prices == {}
    assert not oracle._ready_event.is_set()
    source.price_dict["BTC-USD"] = Decimal("8")
    assert await oracle.get_rate("BTC") == Decimal("8")
    assert await oracle.get_rate("XYZ") is None


async def test_direct_zero_returned_as_is():
    oracle = RateOracle(source=DummyRateSource({"BTC-USD": Decimal("0")}))
    assert await oracle.get_rate("BTC") == Decimal("0")
    assert await oracle.rate_async("BTC-USD") == Decimal("0")
    assert await oracle.get_value(Decimal("2"), "BTC") == Decimal("0")


async def test_double_start_leaves_single_fetch_task():
    oracle = RateOracle(source=DummyRateSource({"A-USD": Decimal("1")}))
    oracle.start()
    oracle.start()
    await asyncio.sleep(0.05)
    live = [
        t for t in asyncio.all_tasks() if "_fetch_price_loop" in repr(t.get_coro()) and not t.done()
    ]
    assert len(live) == 1
    assert oracle._fetch_price_task is live[0]
    oracle.stop()


async def test_back_to_back_start_network_single_task():
    oracle = RateOracle(source=DummyRateSource())
    await asyncio.gather(oracle.start_network(), oracle.start_network())
    await asyncio.sleep(0)
    live = [
        t for t in asyncio.all_tasks() if "_fetch_price_loop" in repr(t.get_coro()) and not t.done()
    ]
    assert len(live) == 1
    await oracle.stop_network()


async def test_start_after_lone_stop_network_restarts():
    oracle = RateOracle(source=DummyRateSource())
    oracle.start()
    await asyncio.sleep(0)
    await oracle.stop_network()
    assert oracle._fetch_price_task is None
    oracle.start()
    await asyncio.sleep(0)
    assert oracle._fetch_price_task is not None
    assert oracle._started is True
    oracle.stop()


def test_protocol_exported_and_runtime_checkable():
    assert isinstance(StructuralSource(), RateSourceProtocol)
