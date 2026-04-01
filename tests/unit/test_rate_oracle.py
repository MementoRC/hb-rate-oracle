"""Unit tests for rate_oracle.core.rate_oracle.RateOracle."""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from rate_oracle.core.rate_oracle import RateOracle
from rate_oracle.core.rate_source_base import RateSourceBase


def _make_mock_source(prices=None, name="mock_source"):
    """Create a mock RateSourceBase with configurable get_prices return."""
    source = MagicMock(spec=RateSourceBase)
    source.name = name
    source.get_prices = AsyncMock(return_value=prices or {})
    return source


class TestRateOracleInit:
    def test_init_defaults(self):
        oracle = RateOracle()
        assert oracle.source is None
        assert oracle.quote_token == "USD"
        assert oracle.prices == {}
        assert oracle._started is False
        assert oracle._update_task is None

    def test_init_with_source(self):
        source = _make_mock_source()
        oracle = RateOracle(source=source)
        assert oracle.source is source

    def test_init_custom_quote_token(self):
        oracle = RateOracle(quote_token="EUR")
        assert oracle.quote_token == "EUR"


class TestSourceProperty:
    def test_source_property_get(self):
        source = _make_mock_source()
        oracle = RateOracle(source=source)
        assert oracle.source is source

    def test_source_property_set(self):
        oracle = RateOracle()
        source = _make_mock_source()
        oracle.source = source
        assert oracle.source is source

    def test_source_property_replace(self):
        source1 = _make_mock_source(name="s1")
        source2 = _make_mock_source(name="s2")
        oracle = RateOracle(source=source1)
        oracle.source = source2
        assert oracle.source is source2


class TestGetPairRate:
    def test_get_pair_rate_known(self):
        oracle = RateOracle()
        oracle._prices = {"BTC-USD": Decimal("50000")}
        assert oracle.get_pair_rate("BTC-USD") == Decimal("50000")

    def test_get_pair_rate_reverse(self):
        oracle = RateOracle()
        oracle._prices = {"USD-BTC": Decimal("0.00002")}
        result = oracle.get_pair_rate("BTC-USD")
        assert result == Decimal("1") / Decimal("0.00002")

    def test_get_pair_rate_not_found(self):
        oracle = RateOracle()
        assert oracle.get_pair_rate("XRP-EUR") == Decimal("0")

    def test_get_pair_rate_same_token(self):
        oracle = RateOracle()
        assert oracle.get_pair_rate("ETH-ETH") == Decimal("1")


class TestGetRateAsync:
    @pytest.mark.asyncio
    async def test_get_rate_cached(self):
        oracle = RateOracle()
        oracle._prices = {"ETH-USD": Decimal("3000")}
        result = await oracle.get_rate("ETH")
        assert result == Decimal("3000")

    @pytest.mark.asyncio
    async def test_get_rate_triggers_update_when_not_found(self):
        source = _make_mock_source({"BTC-USD": Decimal("50000")})
        oracle = RateOracle(source=source)
        # prices is empty, should trigger update
        result = await oracle.get_rate("BTC")
        assert result == Decimal("50000")
        source.get_prices.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_rate_no_source_returns_zero(self):
        oracle = RateOracle()
        result = await oracle.get_rate("BTC")
        assert result == Decimal("0")

    @pytest.mark.asyncio
    async def test_get_rate_uses_quote_token(self):
        source = _make_mock_source({"ETH-EUR": Decimal("2800")})
        oracle = RateOracle(source=source, quote_token="EUR")
        result = await oracle.get_rate("ETH")
        assert result == Decimal("2800")


class TestStartStop:
    @pytest.mark.asyncio
    async def test_start_sets_started_flag(self):
        oracle = RateOracle()
        await oracle.start()
        assert oracle._started is True
        # Clean up
        await oracle.stop()

    @pytest.mark.asyncio
    async def test_start_creates_update_task(self):
        oracle = RateOracle()
        await oracle.start()
        assert oracle._update_task is not None
        await oracle.stop()

    @pytest.mark.asyncio
    async def test_start_idempotent(self):
        oracle = RateOracle()
        await oracle.start()
        task1 = oracle._update_task
        await oracle.start()  # second call is a no-op
        assert oracle._update_task is task1
        await oracle.stop()

    @pytest.mark.asyncio
    async def test_stop_clears_started_flag(self):
        oracle = RateOracle()
        await oracle.start()
        await oracle.stop()
        assert oracle._started is False

    @pytest.mark.asyncio
    async def test_stop_cancels_task(self):
        oracle = RateOracle()
        await oracle.start()
        await oracle.stop()
        assert oracle._update_task is None

    @pytest.mark.asyncio
    async def test_stop_without_start_is_safe(self):
        oracle = RateOracle()
        await oracle.stop()  # should not raise
        assert oracle._started is False


class TestUpdatePrices:
    @pytest.mark.asyncio
    async def test_update_prices_calls_source(self):
        prices = {"BTC-USD": Decimal("50000"), "ETH-USD": Decimal("3000")}
        source = _make_mock_source(prices)
        oracle = RateOracle(source=source)
        await oracle._update_prices()
        assert oracle._prices == prices
        source.get_prices.assert_called_once_with(quote_token="USD")

    @pytest.mark.asyncio
    async def test_update_prices_no_source_is_noop(self):
        oracle = RateOracle()
        await oracle._update_prices()  # should not raise
        assert oracle._prices == {}

    @pytest.mark.asyncio
    async def test_update_prices_source_exception_logs_warning(self):
        source = _make_mock_source()
        source.get_prices = AsyncMock(side_effect=Exception("network error"))
        oracle = RateOracle(source=source)
        # Should not raise; exception is caught internally
        await oracle._update_prices()
        assert oracle._prices == {}

    @pytest.mark.asyncio
    async def test_update_prices_replaces_old_prices(self):
        oracle = RateOracle()
        oracle._prices = {"BTC-USD": Decimal("40000")}
        new_prices = {"BTC-USD": Decimal("50000"), "ETH-USD": Decimal("3000")}
        source = _make_mock_source(new_prices)
        oracle._source = source
        await oracle._update_prices()
        assert oracle._prices == new_prices

    @pytest.mark.asyncio
    async def test_update_prices_passes_custom_quote_token(self):
        prices = {"ETH-EUR": Decimal("2800")}
        source = _make_mock_source(prices)
        oracle = RateOracle(source=source, quote_token="EUR")
        await oracle._update_prices()
        source.get_prices.assert_called_once_with(quote_token="EUR")
