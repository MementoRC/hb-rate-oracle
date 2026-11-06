"""Rate Oracle - Modular cryptocurrency price conversion and rate source framework."""

from rate_oracle.__about__ import __version__
from rate_oracle.core.connector import RateConnectorProtocol
from rate_oracle.core.rate_oracle import RateOracle
from rate_oracle.core.rate_source_base import RateSourceBase
from rate_oracle.core.registry import (
    RATE_ORACLE_SOURCES,
    get_source_class,
    register_source,
    unregister_source,
)
from rate_oracle.core.utils import find_rate
from rate_oracle.sources.coin_cap_source import CoinCapRateSource
from rate_oracle.sources.coin_gecko_source import CoinGeckoAPITier, CoinGeckoRateSource

__all__ = [
    "RATE_ORACLE_SOURCES",
    "CoinCapRateSource",
    "CoinGeckoAPITier",
    "CoinGeckoRateSource",
    "RateConnectorProtocol",
    "RateOracle",
    "RateSourceBase",
    "find_rate",
    "get_source_class",
    "register_source",
    "unregister_source",
    "__version__",
]
