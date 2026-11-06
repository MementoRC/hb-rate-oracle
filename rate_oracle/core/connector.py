"""Connector protocol used by RateOracle to derive rates from live order books."""

from collections.abc import Mapping
from decimal import Decimal
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class RateConnectorProtocol(Protocol):
    """Structural match for hummingbot ConnectorBase/ExchangeBase."""

    @property
    def name(self) -> str: ...

    @property
    def order_books(self) -> Mapping[str, Any]: ...

    def get_mid_price(self, trading_pair: str) -> Decimal: ...
