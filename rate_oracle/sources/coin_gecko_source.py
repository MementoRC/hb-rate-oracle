"""CoinGecko rate source — standalone HTTP implementation."""

import asyncio
import logging
from decimal import Decimal
from enum import Enum
from typing import Any, override

import aiohttp

from rate_oracle.core.rate_source_base import RateSourceBase
from rate_oracle.core.utils import async_ttl_cache, combine_trading_pair

logger = logging.getLogger(__name__)

COOLOFF_AFTER_BAN = 60.0 * 1.05


class CoinGeckoAPITier(Enum):
    PUBLIC = ("public", "", "https://api.coingecko.com/api/v3", 10)
    DEMO = ("demo", "x-cg-demo-api-key", "https://api.coingecko.com/api/v3", 50)
    PRO = ("pro", "x-cg-pro-api-key", "https://pro-api.coingecko.com/api/v3", 500)

    def __init__(self, tier_name: str, header_key: str, base_url: str, rate_limit: int):
        self.tier_name = tier_name
        self.header_key = header_key
        self.base_url = base_url
        self.rate_limit = rate_limit


class CoinGeckoRateSource(RateSourceBase):
    """Fetches prices from CoinGecko API."""

    PRICES_ENDPOINT = "/coins/markets"
    SUPPORTED_VS_ENDPOINT = "/simple/supported_vs_currencies"

    def __init__(
        self,
        extra_token_ids: list[str] | None = None,
        api_key: str = "",
        api_tier: CoinGeckoAPITier = CoinGeckoAPITier.PUBLIC,
    ):
        self._extra_token_ids = extra_token_ids or []
        self._api_key = api_key
        self._api_tier = api_tier
        self._session: aiohttp.ClientSession | None = None

    @override
    @property
    def name(self) -> str:
        return "coin_gecko"

    def _get_headers(self) -> dict[str, str]:
        if self._api_key and self._api_tier.header_key:
            return {self._api_tier.header_key: self._api_key}
        return {}

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def _request(self, endpoint: str, params: dict | None = None) -> Any:
        session = await self._ensure_session()
        url = f"{self._api_tier.base_url}{endpoint}"
        headers = self._get_headers()
        async with session.get(url, params=params, headers=headers) as resp:
            if resp.status == 429:
                logger.warning(f"CoinGecko rate limit hit, cooling off {COOLOFF_AFTER_BAN}s")
                await asyncio.sleep(COOLOFF_AFTER_BAN)
                raise OSError("Rate limited by CoinGecko")
            resp.raise_for_status()
            return await resp.json()

    async def _get_prices_page(self, vs_currency: str, page: int) -> list[dict]:
        params = {
            "vs_currency": vs_currency,
            "order": "market_cap_desc",
            "per_page": "250",
            "page": str(page),
            "sparkline": "false",
        }
        return await self._request(self.PRICES_ENDPOINT, params)

    async def _get_prices_by_ids(self, vs_currency: str, token_ids: list[str]) -> list[dict]:
        params = {
            "vs_currency": vs_currency,
            "ids": ",".join(token_ids),
            "sparkline": "false",
        }
        return await self._request(self.PRICES_ENDPOINT, params)

    @override
    @async_ttl_cache(ttl=int(COOLOFF_AFTER_BAN), maxsize=1)
    async def get_prices(self, quote_token: str | None = None) -> dict[str, Decimal]:
        if not quote_token:
            quote_token = "USD"
        vs_currency = quote_token.lower()
        results: dict[str, Decimal] = {}

        # Fetch 7 pages of top coins by market cap
        for page in range(1, 8):
            try:
                data = await self._get_prices_page(vs_currency, page)
                for coin in data:
                    symbol = coin.get("symbol", "").upper()
                    price = coin.get("current_price")
                    if symbol and price is not None:
                        pair = combine_trading_pair(symbol, quote_token.upper())
                        results[pair] = Decimal(str(price))
            except Exception as e:
                logger.warning(f"Error fetching CoinGecko page {page}: {e}")
                break

        # Fetch extra token IDs
        if self._extra_token_ids:
            try:
                data = await self._get_prices_by_ids(vs_currency, self._extra_token_ids)
                for coin in data:
                    symbol = coin.get("symbol", "").upper()
                    price = coin.get("current_price")
                    if symbol and price is not None:
                        pair = combine_trading_pair(symbol, quote_token.upper())
                        results[pair] = Decimal(str(price))
            except Exception as e:
                logger.warning(f"Error fetching extra token IDs: {e}")

        return results

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
