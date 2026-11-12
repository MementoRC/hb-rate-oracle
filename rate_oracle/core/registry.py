"""Rate source registry.

Name -> class mapping used by client config to validate/select ``source``.
The core registers its in-tree exchange sources via ``register_source``.
"""

import inspect
from decimal import Decimal
from typing import Protocol, runtime_checkable

from rate_oracle.sources.coin_cap_source import CoinCapRateSource
from rate_oracle.sources.coin_gecko_source import CoinGeckoRateSource


@runtime_checkable
class RateSourceProtocol(Protocol):
    """Structural type of a rate source: a ``name`` and an async ``get_prices``."""

    @property
    def name(self) -> str: ...

    async def get_prices(self, quote_token: str | None = None) -> dict[str, Decimal]: ...


RATE_ORACLE_SOURCES: dict[str, type[RateSourceProtocol]] = {
    "coin_gecko": CoinGeckoRateSource,
    "coin_cap": CoinCapRateSource,
}


def _conforms(source_cls: object) -> bool:
    return (
        isinstance(source_cls, type)
        and hasattr(source_cls, "name")
        and inspect.iscoroutinefunction(getattr(source_cls, "get_prices", None))
    )


def register_source(
    name: str, source_cls: type[RateSourceProtocol], *, replace: bool = False
) -> None:
    """Register a rate source class under ``name``.

    Accepts any class with a ``name`` attribute/property and a coroutine
    ``get_prices``; ``RateSourceBase`` subclasses qualify.
    """
    if not _conforms(source_cls):
        raise TypeError(f"{source_cls!r} does not conform to RateSourceProtocol")
    if name in RATE_ORACLE_SOURCES and not replace:
        raise ValueError(f"Rate source '{name}' is already registered")
    RATE_ORACLE_SOURCES[name] = source_cls


def unregister_source(name: str) -> None:
    """Remove a registered source; no error if missing."""
    RATE_ORACLE_SOURCES.pop(name, None)


def get_source_class(name: str) -> type[RateSourceProtocol]:
    """Look up a registered source class by name."""
    try:
        return RATE_ORACLE_SOURCES[name]
    except KeyError:
        available = ", ".join(sorted(RATE_ORACLE_SOURCES))
        raise KeyError(f"Unknown rate source '{name}'. Available: {available}") from None
