"""Standalone utilities replacing hummingbot.connector.utils and hummingbot.core.utils."""

import functools
from decimal import Decimal

import cachetools


def split_trading_pair(trading_pair: str) -> tuple[str, str]:
    """Split 'BASE-QUOTE' into (base, quote)."""
    parts = trading_pair.split("-")
    return parts[0], parts[1] if len(parts) > 1 else ""


def combine_trading_pair(base: str, quote: str) -> str:
    """Combine base and quote into 'BASE-QUOTE'."""
    return f"{base}-{quote}"


def unwrap_token_symbol(token: str) -> str:
    """Strip common wrapper prefixes (e.g., wETH -> ETH)."""
    if token.startswith("w") and len(token) > 1 and token[1].isupper():
        return token[1:]
    return token


def find_rate(prices: dict[str, Decimal], pair: str) -> Decimal:
    """Find exchange rate for a trading pair, supporting reverse and one-hop lookups."""
    if pair in prices:
        return prices[pair]
    base, quote = split_trading_pair(pair)
    base = unwrap_token_symbol(base)
    quote = unwrap_token_symbol(quote)
    if base == quote:
        return Decimal("1")
    reverse_pair = combine_trading_pair(base=quote, quote=base)
    if reverse_pair in prices:
        return Decimal("1") / prices[reverse_pair]
    # One-hop via shared intermediate token
    base_prices = {k: v for k, v in prices.items() if k.startswith(f"{base}-")}
    for base_pair, proxy_price in base_prices.items():
        link_quote = split_trading_pair(base_pair)[1]
        link_pair = combine_trading_pair(base=link_quote, quote=quote)
        if link_pair in prices:
            return proxy_price * prices[link_pair]
        common_denom_pair = combine_trading_pair(base=quote, quote=link_quote)
        if common_denom_pair in prices:
            return proxy_price / prices[common_denom_pair]
    return Decimal("0")


def async_ttl_cache(ttl: int = 3600, maxsize: int = 1):
    """Async TTL cache decorator using cachetools."""
    cache: cachetools.TTLCache[str, object] = cachetools.TTLCache(ttl=ttl, maxsize=maxsize)

    def decorator(fn):
        @functools.wraps(fn)
        async def memoize(*args, **kwargs):
            key = str((args, kwargs))
            try:
                return cache[key]
            except KeyError:
                cache[key] = await fn(*args, **kwargs)
                return cache[key]

        memoize.cache_clear = lambda: cache.clear()
        return memoize

    return decorator
