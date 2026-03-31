"""Abstract base class for rate sources."""

import logging
from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class RateSourceBase(ABC):
    """Base class for all rate sources (exchange-based, CoinGecko, CoinCap, etc.)."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name of this rate source."""
        ...

    @abstractmethod
    async def get_prices(self, quote_token: Optional[str] = None) -> Dict[str, Decimal]:
        """Fetch current prices. Returns dict of 'BASE-QUOTE' -> price."""
        ...
