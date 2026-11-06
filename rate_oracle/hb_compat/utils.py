"""Hummingbot-exact helpers (None instead of Decimal("0") on a miss)."""

from decimal import Decimal

from rate_oracle.core.utils import find_rate as _core_find_rate


def find_rate(prices: dict[str, Decimal], pair: str) -> Decimal | None:
    """Find a pair rate (direct or reverse); None when not available."""
    rate = _core_find_rate(prices, pair)
    return None if rate == Decimal("0") else rate
