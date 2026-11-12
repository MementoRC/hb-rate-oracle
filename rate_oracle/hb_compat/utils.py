"""Hummingbot-exact helpers: port of in-tree ``hummingbot.core.rate_oracle.utils``."""

from decimal import Decimal

from rate_oracle.core.utils import combine_trading_pair, split_trading_pair

# Symbols treated as interchangeable with USDT for rate lookups. Mutable on purpose:
# the parent overrides it at startup (in-tree ``global_token`` client config).
USD_EQUIVALENT_TOKENS: list[str] = ["USD"]


def normalize_token_symbol(token_symbol: str) -> str:
    """Map USD-equivalent symbols to USDT."""
    if token_symbol in USD_EQUIVALENT_TOKENS:
        return "USDT"
    return token_symbol


def find_rate(prices: dict[str, Decimal], pair: str) -> Decimal | None:
    """Find a pair rate (direct, reverse or one-hop bridged); None when not available.

    A direct zero price is returned as-is; zero reverse/bridge prices are skipped.
    """
    if pair in prices:
        return prices[pair]
    base, quote = split_trading_pair(pair)
    base = normalize_token_symbol(base)
    quote = normalize_token_symbol(quote)
    if base == quote:
        return Decimal("1")
    normalized_pair = combine_trading_pair(base, quote)
    if normalized_pair in prices:
        return prices[normalized_pair]
    reverse_pair = combine_trading_pair(quote, base)
    if reverse_pair in prices and prices[reverse_pair] > Decimal("0"):
        return Decimal("1") / prices[reverse_pair]
    for base_pair, proxy_price in [(k, v) for k, v in prices.items() if k.startswith(f"{base}-")]:
        link_quote = split_trading_pair(base_pair)[1]
        link_pair = combine_trading_pair(link_quote, quote)
        if link_pair in prices:
            return proxy_price * prices[link_pair]
        common_denom_pair = combine_trading_pair(quote, link_quote)
        if common_denom_pair in prices and prices[common_denom_pair] > Decimal("0"):
            return proxy_price / prices[common_denom_pair]
    return None
