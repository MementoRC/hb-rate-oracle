"""Hummingbot compatibility layer for rate-oracle.

Provides drop-in replacements for:
- RateOracle (hummingbot.core.rate_oracle.rate_oracle): sync start/stop,
  get_pair_rate returning None on miss, start_network/stop_network
- RateSourceBase (hummingbot.core.rate_oracle.sources.rate_source_base)
- CoinGeckoRateSource (hummingbot.core.rate_oracle.sources.coin_gecko_rate_source)
- CoinCapRateSource (hummingbot.core.rate_oracle.sources.coin_cap_rate_source)
- RATE_ORACLE_SOURCES / register_source: source registry
- RateConnectorProtocol: structural type for connectors feeding the oracle
"""

from rate_oracle.core.connector import RateConnectorProtocol
from rate_oracle.core.rate_source_base import RateSourceBase
from rate_oracle.core.registry import RATE_ORACLE_SOURCES, register_source
from rate_oracle.hb_compat.rate_oracle import RateOracle
from rate_oracle.hb_compat.utils import find_rate
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
    "register_source",
]
