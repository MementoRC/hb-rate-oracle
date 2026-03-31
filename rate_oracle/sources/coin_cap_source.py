"""CoinCap rate source — standalone HTTP + WebSocket implementation."""

import asyncio
import logging
from decimal import Decimal
from typing import Any, Dict, Optional

import aiohttp

from rate_oracle.core.rate_source_base import RateSourceBase
from rate_oracle.core.utils import combine_trading_pair

logger = logging.getLogger(__name__)

BASE_REST_URL = "https://api.coincap.io/v2"
BASE_WS_URL = "wss://ws.coincap.io/prices?assets="
ALL_ASSETS_ENDPOINT = "/assets"


class CoinCapRateSource(RateSourceBase):
    """Fetches prices from CoinCap API."""

    def __init__(
        self,
        assets_map: Optional[Dict[str, str]] = None,
        api_key: str = "",
    ):
        self._assets_map = assets_map or {}
        self._api_key = api_key
        self._prices: Dict[str, Decimal] = {}
        self._session: Optional[aiohttp.ClientSession] = None

    @property
    def name(self) -> str:
        return "coin_cap"

    def _get_headers(self) -> Dict[str, str]:
        if self._api_key:
            return {"Authorization": f"Bearer {self._api_key}"}
        return {}

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def _request(self, endpoint: str, params: Optional[Dict] = None) -> Any:
        session = await self._ensure_session()
        url = f"{BASE_REST_URL}{endpoint}"
        headers = self._get_headers()
        async with session.get(url, params=params, headers=headers) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def get_prices(self, quote_token: Optional[str] = None) -> Dict[str, Decimal]:
        if quote_token and quote_token.upper() != "USD":
            logger.warning("CoinCapRateSource only supports USD as quote token.")
            return {}

        if not self._assets_map:
            return {}

        asset_ids = ",".join(self._assets_map.keys())
        try:
            data = await self._request(ALL_ASSETS_ENDPOINT, params={"ids": asset_ids})
            results: Dict[str, Decimal] = {}
            for asset in data.get("data", []):
                asset_id = asset.get("id", "")
                symbol = self._assets_map.get(asset_id, asset.get("symbol", "").upper())
                price = asset.get("priceUsd")
                if symbol and price:
                    pair = combine_trading_pair(symbol.upper(), "USD")
                    results[pair] = Decimal(str(price))
            return results
        except Exception as e:
            logger.error(f"Error fetching CoinCap prices: {e}")
            return {}

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
