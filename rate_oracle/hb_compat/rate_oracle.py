"""Hummingbot-exact RateOracle surface (sync start/stop, Decimal | None rates)."""

import asyncio
import logging
from collections.abc import Callable
from decimal import Decimal
from typing import Any, ClassVar

from rate_oracle.core.rate_oracle import RateOracle as RateOracleCore
from rate_oracle.core.utils import combine_trading_pair, split_trading_pair
from rate_oracle.core.utils import find_rate as _core_find_rate

logger = logging.getLogger(__name__)

_ZERO = Decimal("0")


class RateOracle(RateOracleCore):
    """RateOracle with the in-tree NetworkBase-style API.

    Class hooks, set by the parent shim:

    - ``default_source_factory``: zero-arg callable used to build the source when
      the constructor receives ``source=None`` (in-tree defaults to a Gate.io source).
    - ``mid_price_type``: the value passed as the price type to
      ``connector.get_price_by_type`` in the connector fallback (in-tree
      ``PriceType.MidPrice``).

    ``_update_task`` of the core is an alias of ``_fetch_price_task`` so the two
    loops cannot run side by side.
    """

    default_source_factory: ClassVar[Callable[[], Any] | None] = None
    mid_price_type: ClassVar[Any] = None
    _shared_instance: ClassVar["RateOracle | None"] = None

    def __init__(self, source: Any = None, quote_token: str | None = None):
        # Read via the class: a plain function set on the class must not bind to self.
        factory = type(self).default_source_factory
        if source is None and factory is not None:
            source = factory()
        self._fetch_price_task: asyncio.Task | None = None
        self._start_task: asyncio.Task | None = None
        super().__init__(source=source, quote_token="USD" if quote_token is None else quote_token)
        self._connectors: dict[str, Any] = {}

    @classmethod
    def get_instance(cls) -> "RateOracle":
        if cls._shared_instance is None:
            cls._shared_instance = cls()
        return cls._shared_instance

    def __str__(self) -> str:
        source_name = self._source.name if self._source is not None else "no source"
        return f"{source_name} rate oracle"

    @property
    def _update_task(self) -> asyncio.Task | None:  # type: ignore[override]
        return self._fetch_price_task

    @_update_task.setter
    def _update_task(self, value: asyncio.Task | None) -> None:
        self._fetch_price_task = value

    @property
    def quote_token(self) -> str:
        return self._quote_token

    @quote_token.setter
    def quote_token(self, value: str) -> None:
        if value != self._quote_token:
            self._quote_token = value
            self._prices = {}

    # In-tree NetworkBase API is sync, hence the override ignores below.
    def start(self) -> None:  # type: ignore[override]
        if self._started:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError as e:
            raise RuntimeError(
                "RateOracle.start() must be called from within a running event loop"
            ) from e
        self._started = True
        self._start_task = loop.create_task(self.start_network())

    def stop(self) -> None:  # type: ignore[override]
        if self._start_task is not None:
            self._start_task.cancel()
            self._start_task = None
        if self._fetch_price_task is not None:
            self._fetch_price_task.cancel()
        self._fetch_price_task = None
        self._started = False

    async def start_network(self) -> None:
        await self.stop_network()
        self._fetch_price_task = asyncio.get_running_loop().create_task(self._fetch_price_loop())

    async def stop_network(self) -> None:
        if self._fetch_price_task is not None:
            self._fetch_price_task.cancel()
            self._fetch_price_task = None

    async def _fetch_price_loop(self) -> None:
        while True:
            await self._update_prices()
            await asyncio.sleep(1.0)

    async def get_ready(self) -> None:
        try:
            if not self._ready_event.is_set():
                await self._ready_event.wait()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.error(
                "Unexpected error while waiting for data feed to get ready.", exc_info=True
            )

    def register_connector(self, connector: Any) -> None:
        self._connectors[connector.name] = connector

    def unregister_connector(self, connector: Any) -> None:  # type: ignore[override]
        name = connector if isinstance(connector, str) else connector.name
        self._connectors.pop(name, None)

    def _get_rate_from_connectors(self, pair: str) -> Decimal | None:
        base, quote = split_trading_pair(pair)
        reverse = combine_trading_pair(quote, base)
        for name in sorted(self._connectors):
            connector = self._connectors[name]
            order_books = getattr(connector, "order_books", None) or {}
            if pair in order_books:
                rate = connector.get_price_by_type(pair, self.mid_price_type)
                if rate is not None and rate > _ZERO:
                    return rate
            if reverse in order_books:
                reverse_rate = connector.get_price_by_type(reverse, self.mid_price_type)
                if reverse_rate is not None and reverse_rate > _ZERO:
                    return Decimal("1") / reverse_rate
        return None

    def get_pair_rate(self, pair: str) -> Decimal | None:  # type: ignore[override]
        rate = _core_find_rate(self._prices, pair)
        if rate > _ZERO:
            return rate
        connector_rate = self._get_rate_from_connectors(pair)
        if connector_rate is not None:
            return connector_rate
        base, quote = split_trading_pair(pair)
        reverse_rate = _core_find_rate(self._prices, combine_trading_pair(quote, base))
        if reverse_rate > _ZERO:
            return Decimal("1") / reverse_rate
        return None

    async def rate_async(self, pair: str) -> Decimal | None:  # type: ignore[override]
        rate = await super().rate_async(pair)
        return None if rate == _ZERO else rate

    async def stored_or_live_rate(self, pair: str) -> Decimal | None:  # type: ignore[override]
        if self._prices:
            return self.get_pair_rate(pair)
        return await self.rate_async(pair)

    async def get_rate(self, base_token: str) -> Decimal | None:  # type: ignore[override]
        rate = await super().get_rate(base_token)
        return None if rate == _ZERO else rate

    async def get_value(self, amount: Decimal, base_token: str) -> Decimal:
        rate = await self.get_rate(base_token)
        return amount * (rate or _ZERO)
