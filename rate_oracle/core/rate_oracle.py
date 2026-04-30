"""Rate Oracle — cryptocurrency price conversion service."""

import asyncio
import logging
from decimal import Decimal

from rate_oracle.core.rate_source_base import RateSourceBase
from rate_oracle.core.utils import find_rate

logger = logging.getLogger(__name__)


class RateOracle:
    """Fetches and caches cryptocurrency prices from a configurable rate source."""

    def __init__(
        self,
        source: RateSourceBase | None = None,
        quote_token: str = "USD",
    ):
        self._source = source
        self._quote_token = quote_token
        self._prices: dict[str, Decimal] = {}
        self._started = False
        self._update_task: asyncio.Task | None = None
        self._update_interval: float = 5.0

    @property
    def source(self) -> RateSourceBase | None:
        return self._source

    @source.setter
    def source(self, value: RateSourceBase):
        self._source = value

    @property
    def quote_token(self) -> str:
        return self._quote_token

    @property
    def prices(self) -> dict[str, Decimal]:
        return self._prices.copy()

    def get_pair_rate(self, pair: str) -> Decimal:
        """Get the exchange rate for a trading pair."""
        return find_rate(self._prices, pair)

    async def get_rate(self, token: str) -> Decimal:
        """Get the rate for a token in terms of the quote token."""
        from rate_oracle.core.utils import combine_trading_pair

        pair = combine_trading_pair(token, self._quote_token)
        rate = find_rate(self._prices, pair)
        if rate == Decimal("0"):
            await self._update_prices()
            rate = find_rate(self._prices, pair)
        return rate

    async def start(self):
        """Start periodic price updates."""
        if self._started:
            return
        self._started = True
        self._update_task = asyncio.create_task(self._update_loop())

    async def stop(self):
        """Stop periodic price updates."""
        self._started = False
        if self._update_task:
            self._update_task.cancel()
            self._update_task = None

    async def _update_loop(self):
        """Periodically fetch prices from the configured source."""
        while self._started:
            try:
                await self._update_prices()
            except Exception as e:
                logger.error(f"Error updating prices: {e}")
            await asyncio.sleep(self._update_interval)

    async def _update_prices(self):
        """Fetch latest prices from the source."""
        if self._source is None:
            return
        try:
            self._prices = await self._source.get_prices(quote_token=self._quote_token)
        except Exception as e:
            logger.warning(f"Failed to fetch prices from {self._source.name}: {e}")
