"""Unit tests for connector registration and connector-derived rates."""

from decimal import Decimal

from rate_oracle.core.connector import RateConnectorProtocol
from rate_oracle.core.rate_oracle import RateOracle


class FakeConnector:
    def __init__(self, name, mids=None, raises=False):
        self.name = name
        self._mids = mids or {}
        self._raises = raises
        self.order_books = dict.fromkeys(self._mids, object())

    def get_mid_price(self, trading_pair):
        if self._raises:
            raise RuntimeError("boom")
        return self._mids[trading_pair]


def test_fake_connector_matches_protocol():
    assert isinstance(FakeConnector("a"), RateConnectorProtocol)


def test_register_and_unregister():
    oracle = RateOracle()
    conn = FakeConnector("binance", {"BTC-USD": Decimal("50000")})
    oracle.register_connector(conn)
    assert oracle.get_pair_rate("BTC-USD") == Decimal("50000")
    oracle.unregister_connector("binance")
    assert oracle.get_pair_rate("BTC-USD") == Decimal("0")


def test_unregister_missing_is_noop():
    RateOracle().unregister_connector("nope")


def test_cached_direct_beats_connector():
    oracle = RateOracle()
    oracle.set_price("BTC-USD", Decimal("1"))
    oracle.register_connector(FakeConnector("a", {"BTC-USD": Decimal("2")}))
    assert oracle.get_pair_rate("BTC-USD") == Decimal("1")


def test_connector_beats_inverted_cache():
    oracle = RateOracle()
    oracle.set_price("USD-BTC", Decimal("0.5"))
    oracle.register_connector(FakeConnector("a", {"BTC-USD": Decimal("4")}))
    assert oracle.get_pair_rate("BTC-USD") == Decimal("4")


def test_reverse_pair_uses_inverse_mid():
    oracle = RateOracle()
    oracle.register_connector(FakeConnector("a", {"USD-BTC": Decimal("0.25")}))
    assert oracle.get_pair_rate("BTC-USD") == Decimal("4")


def test_raising_connector_is_skipped():
    oracle = RateOracle()
    oracle.register_connector(FakeConnector("a", {"BTC-USD": Decimal("1")}, raises=True))
    oracle.register_connector(FakeConnector("b", {"BTC-USD": Decimal("7")}))
    assert oracle.get_pair_rate("BTC-USD") == Decimal("7")


def test_sorted_by_name_first_positive_wins():
    oracle = RateOracle()
    oracle.register_connector(FakeConnector("b", {"BTC-USD": Decimal("2")}))
    oracle.register_connector(FakeConnector("a", {"BTC-USD": Decimal("1")}))
    assert oracle.get_pair_rate("BTC-USD") == Decimal("1")


def test_zero_mid_skipped():
    oracle = RateOracle()
    oracle.register_connector(FakeConnector("a", {"BTC-USD": Decimal("0")}))
    oracle.register_connector(FakeConnector("b", {"BTC-USD": Decimal("3")}))
    assert oracle.get_pair_rate("BTC-USD") == Decimal("3")


def test_zero_reverse_mid_skipped():
    oracle = RateOracle()
    oracle.register_connector(FakeConnector("a", {"USD-BTC": Decimal("0")}))
    assert oracle.get_pair_rate("BTC-USD") == Decimal("0")
