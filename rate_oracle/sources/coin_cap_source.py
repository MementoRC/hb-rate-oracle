"""CoinCap rate source — standalone HTTP + WebSocket implementation."""

import logging
from decimal import Decimal
from typing import Any, override

import aiohttp
from rate_limit import RateLimiter

from rate_oracle.core.rate_source_base import RateSourceBase
from rate_oracle.core.utils import combine_trading_pair
from rate_oracle.sources.rate_limit import (
    RateLimitedError,
    build_limiter,
    paced_get,
    requests_per_minute,
)

logger = logging.getLogger(__name__)

LIMIT_ID = "coin_cap"
# CoinCap's published unauthenticated allowance is 200 requests/minute (recalled from its docs,
# not re-verified); kept for keyed use too, as the conservative choice.
REQUESTS_PER_MINUTE = 200

BASE_REST_URL = "https://api.coincap.io/v2"
BASE_WS_URL = "wss://ws.coincap.io/prices?assets="
ALL_ASSETS_ENDPOINT = "/assets"


class CoinCapRateSource(RateSourceBase):
    """Fetches prices from CoinCap API."""

    def __init__(
        self,
        assets_map: dict[str, str] | None = None,
        api_key: str = "",
        rate_limiter: RateLimiter | None = None,
    ):
        self._assets_map = assets_map or {}
        self._api_key = api_key
        self._prices: dict[str, Decimal] = {}
        self._session: aiohttp.ClientSession | None = None
        self._limiter = rate_limiter or build_limiter()
        self._limiter.add_limit(requests_per_minute(LIMIT_ID, REQUESTS_PER_MINUTE))
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
        return await paced_get(
            self._limiter,
            LIMIT_ID,
            session,
            f"{BASE_REST_URL}{endpoint}",
            params=params,
            headers=self._get_headers(),
            source="CoinCap",
        )

    @override
    async def get_prices(self, quote_token: str | None = None) -> dict[str, Decimal]:
        if quote_token and quote_token.upper() != "USD":
            logger.warning("CoinCapRateSource only supports USD as quote token.")
            return {}

        if not self._assets_map:
            return {}

        if self._limiter.is_paused(LIMIT_ID):
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
        except RateLimitedError:
            return dict(self._last_prices)
        except Exception as e:
            logger.error(f"Error fetching CoinCap prices: {e}")
            return {}

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
