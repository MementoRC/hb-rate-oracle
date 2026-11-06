"""Rate Oracle — cryptocurrency price conversion service."""

import asyncio
import logging
from decimal import Decimal

from rate_oracle.core.connector import RateConnectorProtocol
from rate_oracle.core.rate_source_base import RateSourceBase
from rate_oracle.core.utils import combine_trading_pair, find_rate, split_trading_pair

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
        self._connectors: dict[str, RateConnectorProtocol] = {}
        self._ready_event = asyncio.Event()

    @property
    def source(self) -> RateSourceBase | None:
        return self._source

    @source.setter
    def source(self, value: RateSourceBase):
        self._source = value

    @property
    def name(self) -> str:
        return "rate_oracle"

    @property
    def quote_token(self) -> str:
        return self._quote_token

    @quote_token.setter
    def quote_token(self, value: str):
        self._quote_token = value
        self._prices = {}

    @property
    def prices(self) -> dict[str, Decimal]:
        return self._prices.copy()

    def register_connector(self, connector: RateConnectorProtocol) -> None:
        """Register a connector whose order books can provide rates."""
        self._connectors[connector.name] = connector

    def unregister_connector(self, connector_name: str) -> None:
        """Remove a registered connector; no error if missing."""
        self._connectors.pop(connector_name, None)

    def _get_rate_from_connectors(self, pair: str) -> Decimal | None:
        """Return the first positive mid-price rate from connectors (sorted by name)."""
        base, quote = split_trading_pair(pair)
        reverse = combine_trading_pair(quote, base)
        for _, connector in sorted(self._connectors.items()):
            try:
                if pair in connector.order_books:
                    rate = connector.get_mid_price(pair)
                elif reverse in connector.order_books:
                    mid = connector.get_mid_price(reverse)
                    rate = Decimal("1") / mid if mid else Decimal("0")
                else:
                    continue
            except Exception as e:
                logger.debug(f"Connector {connector.name} failed to price {pair}: {e}")
                continue
            if rate > 0:
                return rate
        return None

    def get_pair_rate(self, pair: str) -> Decimal:
        """Get the exchange rate for a trading pair."""
        if pair in self._prices:
            return self._prices[pair]
        rate = self._get_rate_from_connectors(pair)
        if rate is not None:
            return rate
        return find_rate(self._prices, pair)

    def set_price(self, pair: str, price: Decimal) -> None:
        self._prices[pair] = price

    async def rate_async(self, pair: str) -> Decimal:
        """Fetch a live rate from the source, bypassing the cache."""
        if self._source is None:
            return Decimal("0")
        prices = await self._source.get_prices(quote_token=self._quote_token)
        return find_rate(prices, pair)

    async def stored_or_live_rate(self, pair: str) -> Decimal:
        """Use cached prices when available, otherwise fetch live."""
        if self._prices:
            return self.get_pair_rate(pair)
        return await self.rate_async(pair)

    async def get_value(self, amount: Decimal, base_token: str) -> Decimal:
        """Convert an amount of base_token into the quote token."""
        return amount * await self.get_rate(base_token)

    async def get_ready(self) -> None:
        """Wait until prices have been fetched at least once."""
        await self._ready_event.wait()

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
            new_prices = await self._source.get_prices(quote_token=self._quote_token)
            # Merge like in-tree _fetch_price_loop so set_price() values and pairs missing from a partial fetch survive refreshes.
            self._prices.update(new_prices)
            if self._prices:
                self._ready_event.set()
        except Exception as e:
            logger.warning(f"Failed to fetch prices from {self._source.name}: {e}")
