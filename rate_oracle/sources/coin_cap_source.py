"""CoinCap rate source — standalone HTTP + WebSocket implementation."""

import logging
import time
from decimal import Decimal
from typing import Any, override

import aiohttp

from rate_oracle.core.rate_source_base import RateSourceBase
from rate_oracle.core.utils import combine_trading_pair
from rate_oracle.sources.rate_limit import RateLimitedError, parse_retry_after

logger = logging.getLogger(__name__)

COOLOFF_AFTER_BAN = 60.0 * 1.05

BASE_REST_URL = "https://api.coincap.io/v2"
BASE_WS_URL = "wss://ws.coincap.io/prices?assets="
ALL_ASSETS_ENDPOINT = "/assets"


class CoinCapRateSource(RateSourceBase):
    """Fetches prices from CoinCap API."""

    def __init__(
        self,
        assets_map: dict[str, str] | None = None,
        api_key: str = "",
    ):
        self._assets_map = assets_map or {}
        self._api_key = api_key
        self._prices: dict[str, Decimal] = {}
        self._session: aiohttp.ClientSession | None = None
        self._rate_limited_until = 0.0  # time.monotonic() deadline
        self._last_prices: dict[str, Decimal] = {}  # last successful fetch

    @override
    @property
    def name(self) -> str:
        return "coin_cap"

    def _get_headers(self) -> dict[str, str]:
        if self._api_key:
            return {"Authorization": f"Bearer {self._api_key}"}
        return {}

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def _request(self, endpoint: str, params: dict | None = None) -> Any:
        session = await self._ensure_session()
        url = f"{BASE_REST_URL}{endpoint}"
        headers = self._get_headers()
        async with session.get(url, params=params, headers=headers) as resp:
            if resp.status == 429:
                raise RateLimitedError(
                    parse_retry_after(resp.headers.get("Retry-After"), COOLOFF_AFTER_BAN),
                    "Rate limited by CoinCap",
                )
            resp.raise_for_status()
            return await resp.json()

    @override
    async def get_prices(self, quote_token: str | None = None) -> dict[str, Decimal]:
        if quote_token and quote_token.upper() != "USD":
            logger.warning("CoinCapRateSource only supports USD as quote token.")
            return {}

        if not self._assets_map:
            return {}

        if time.monotonic() < self._rate_limited_until:
            logger.debug("CoinCap rate-limit backoff active, skipping fetch")
            return dict(self._last_prices)

        asset_ids = ",".join(self._assets_map.keys())
        try:
            data = await self._request(ALL_ASSETS_ENDPOINT, params={"ids": asset_ids})
            results: dict[str, Decimal] = {}
            for asset in data.get("data", []):
                asset_id = asset.get("id", "")
                symbol = self._assets_map.get(asset_id, asset.get("symbol", "").upper())
                price = asset.get("priceUsd")
                if symbol and price:
                    pair = combine_trading_pair(symbol.upper(), "USD")
                    results[pair] = Decimal(str(price))
            self._last_prices = results
            return results
        except RateLimitedError as e:
            self._rate_limited_until = time.monotonic() + e.retry_after
            logger.warning(f"CoinCap rate limit hit, backing off {e.retry_after:.0f}s")
            return dict(self._last_prices)
        except Exception as e:
            logger.error(f"Error fetching CoinCap prices: {e}")
            return {}

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
