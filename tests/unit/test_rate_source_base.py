"""Unit tests for rate_oracle.core.rate_source_base.RateSourceBase."""

from decimal import Decimal
from typing import Dict, Optional

import pytest

from rate_oracle.core.rate_source_base import RateSourceBase


class TestRateSourceBaseAbstract:
    def test_cannot_instantiate(self):
        """RateSourceBase is abstract and cannot be instantiated directly."""
        with pytest.raises(TypeError):
            RateSourceBase()  # type: ignore[abstract]

    def test_subclass_missing_name_cannot_instantiate(self):
        """Subclass that only implements get_prices but not name cannot be instantiated."""

        class PartialSource(RateSourceBase):
            async def get_prices(self, quote_token=None):
                return {}

        with pytest.raises(TypeError):
            PartialSource()

    def test_subclass_missing_get_prices_cannot_instantiate(self):
        """Subclass that only implements name but not get_prices cannot be instantiated."""

        class PartialSource(RateSourceBase):
            @property
            def name(self) -> str:
                return "partial"

        with pytest.raises(TypeError):
            PartialSource()


class TestRateSourceBaseSubclass:
    def test_subclass_with_methods(self):
        """A complete concrete subclass can be instantiated and called."""

        class ConcreteSource(RateSourceBase):
            @property
            def name(self) -> str:
                return "concrete"

            async def get_prices(self, quote_token: Optional[str] = None) -> Dict[str, Decimal]:
                return {"BTC-USD": Decimal("50000")}

        source = ConcreteSource()
        assert source.name == "concrete"

    def test_subclass_name_property(self):
        class NamedSource(RateSourceBase):
            @property
            def name(self) -> str:
                return "my_source"

            async def get_prices(self, quote_token=None):
                return {}

        source = NamedSource()
        assert source.name == "my_source"

    @pytest.mark.asyncio
    async def test_subclass_get_prices(self):
        class PricedSource(RateSourceBase):
            @property
            def name(self) -> str:
                return "priced"

            async def get_prices(self, quote_token=None) -> Dict[str, Decimal]:
                return {"ETH-USD": Decimal("3000"), "BTC-USD": Decimal("50000")}

        source = PricedSource()
        prices = await source.get_prices()
        assert "ETH-USD" in prices
        assert prices["ETH-USD"] == Decimal("3000")

    @pytest.mark.asyncio
    async def test_subclass_get_prices_with_quote_token(self):
        class QuoteAwareSource(RateSourceBase):
            @property
            def name(self) -> str:
                return "quote_aware"

            async def get_prices(self, quote_token: Optional[str] = None) -> Dict[str, Decimal]:
                token = quote_token or "USD"
                return {f"BTC-{token}": Decimal("50000")}

        source = QuoteAwareSource()
        prices = await source.get_prices(quote_token="EUR")
        assert "BTC-EUR" in prices
