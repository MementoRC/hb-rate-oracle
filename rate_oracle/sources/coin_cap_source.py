"""CoinCap rate source — standalone HTTP implementation (v3 REST API)."""

import logging
import time
from decimal import Decimal
from typing import Any, override

import aiohttp
from rate_limit import Clock, RateLimiter

from rate_oracle.core.rate_source_base import RateSourceBase
from rate_oracle.core.utils import combine_trading_pair
from rate_oracle.sources.rate_limit import (
    RateLimitedError,
    build_limiter,
    paced_get,
)
from rate_oracle.sources.rate_limit import requests_per_minute as _requests_per_minute

logger = logging.getLogger(__name__)

LIMIT_ID = "coin_cap"
# CoinCap v3 free plan: `X-RateLimit-Limit: 5` per ~sliding 60s (verified against live responses
# 2026-10-26). Paid plans allow more; pass `requests_per_minute` to match.
FREE_TIER_REQUESTS_PER_MINUTE = 5
# Server-side `cache-control: max-age=30`; no point refetching sooner.
SERVER_CACHE_SECONDS = 30.0

BASE_REST_URL = "https://rest.coincap.io/v3"
ALL_ASSETS_ENDPOINT = "/assets"


class CoinCapRateSource(RateSourceBase):
    """Fetches prices from the CoinCap v3 REST API (an API key is required)."""

    def __init__(
        self,
        assets_map: dict[str, str] | None = None,
        api_key: str = "",
        rate_limiter: RateLimiter | None = None,
        requests_per_minute: int = FREE_TIER_REQUESTS_PER_MINUTE,
        cache_ttl: float | None = None,
        clock: Clock = time.monotonic,
    ):
        if requests_per_minute < 1:
            raise ValueError(f"requests_per_minute must be >= 1, got {requests_per_minute}")
        self._assets_map = assets_map or {}
        self._api_key = api_key
        self._prices: dict[str, Decimal] = {}
        self._session: aiohttp.ClientSession | None = None
        self._limiter = rate_limiter or build_limiter()
        self._limiter.add_limit(_requests_per_minute(LIMIT_ID, requests_per_minute))
        self._last_prices: dict[str, Decimal] = {}  # last successful fetch
        self._cache_ttl = (
            cache_ttl
            if cache_ttl is not None
            else max(SERVER_CACHE_SECONDS, 60.0 / requests_per_minute)
        )
        self._clock = clock
        self._fetched_at: float | None = None
        self._warned_no_key = False

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

        if not self._api_key:
            if not self._warned_no_key:
                self._warned_no_key = True
                logger.warning("CoinCap v3 requires an API key; no CoinCap prices will be fetched.")
            return {}

        if self._fetched_at is not None and self._clock() - self._fetched_at < self._cache_ttl:
            return dict(self._last_prices)

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
            self._fetched_at = self._clock()
            return results
        except RateLimitedError:
            return dict(self._last_prices)
        except Exception as e:
            logger.error(f"Error fetching CoinCap prices: {e}")
            return dict(self._last_prices)

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
