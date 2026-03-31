"""Hummingbot compatibility layer for rate-oracle.

Provides drop-in replacements for:
- RateOracle (hummingbot.core.rate_oracle.rate_oracle)
- RateSourceBase (hummingbot.core.rate_oracle.sources.rate_source_base)
- CoinGeckoRateSource (hummingbot.core.rate_oracle.sources.coin_gecko_rate_source)
- CoinCapRateSource (hummingbot.core.rate_oracle.sources.coin_cap_rate_source)
"""

from rate_oracle.core.rate_oracle import RateOracle
from rate_oracle.core.rate_source_base import RateSourceBase
from rate_oracle.core.utils import find_rate
from rate_oracle.sources.coin_cap_source import CoinCapRateSource
from rate_oracle.sources.coin_gecko_source import CoinGeckoAPITier, CoinGeckoRateSource

__all__ = [
    "CoinCapRateSource",
    "CoinGeckoAPITier",
    "CoinGeckoRateSource",
    "RateOracle",
    "RateSourceBase",
    "find_rate",
]
