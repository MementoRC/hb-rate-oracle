"""Hummingbot-exact RateOracle surface (sync start/stop, Decimal | None rates)."""

import asyncio
from decimal import Decimal

from rate_oracle.core.rate_oracle import RateOracle as RateOracleCore


class RateOracle(RateOracleCore):
    """RateOracle with the in-tree NetworkBase-style API."""

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
        self._update_task = loop.create_task(self._update_loop())

    def stop(self) -> None:  # type: ignore[override]
        self._started = False
        if self._update_task:
            self._update_task.cancel()
            self._update_task = None

    def get_pair_rate(self, pair: str) -> Decimal | None:  # type: ignore[override]
        rate = super().get_pair_rate(pair)
        return None if rate == Decimal("0") else rate

    async def rate_async(self, pair: str) -> Decimal | None:  # type: ignore[override]
        rate = await super().rate_async(pair)
        return None if rate == Decimal("0") else rate

    async def stored_or_live_rate(self, pair: str) -> Decimal | None:  # type: ignore[override]
        if self._prices:
            return self.get_pair_rate(pair)
        return await self.rate_async(pair)

    async def get_rate(self, base_token: str) -> Decimal | None:  # type: ignore[override]
        rate = await super().get_rate(base_token)
        return None if rate == Decimal("0") else rate

    async def get_value(self, amount: Decimal, base_token: str) -> Decimal:
        rate = await self.get_rate(base_token)
        return amount * (rate or Decimal("0"))

    async def start_network(self) -> None:
        await super().start()

    async def stop_network(self) -> None:
        await super().stop()
