"""Rate source registry.

Name -> class mapping used by client config to validate/select ``source``.
The core registers its in-tree exchange sources via ``register_source``.
"""

from rate_oracle.core.rate_source_base import RateSourceBase
from rate_oracle.sources.coin_cap_source import CoinCapRateSource
from rate_oracle.sources.coin_gecko_source import CoinGeckoRateSource

RATE_ORACLE_SOURCES: dict[str, type[RateSourceBase]] = {
    "coin_gecko": CoinGeckoRateSource,
    "coin_cap": CoinCapRateSource,
}


def register_source(name: str, source_cls: type[RateSourceBase], *, replace: bool = False) -> None:
    """Register a rate source class under ``name``."""
    if not (isinstance(source_cls, type) and issubclass(source_cls, RateSourceBase)):
        raise TypeError(f"{source_cls!r} is not a RateSourceBase subclass")
    if name in RATE_ORACLE_SOURCES and not replace:
        raise ValueError(f"Rate source '{name}' is already registered")
    RATE_ORACLE_SOURCES[name] = source_cls


def unregister_source(name: str) -> None:
    """Remove a registered source; no error if missing."""
    RATE_ORACLE_SOURCES.pop(name, None)


def get_source_class(name: str) -> type[RateSourceBase]:
    """Look up a registered source class by name."""
    try:
        return RATE_ORACLE_SOURCES[name]
    except KeyError:
        available = ", ".join(sorted(RATE_ORACLE_SOURCES))
        raise KeyError(f"Unknown rate source '{name}'. Available: {available}") from None
