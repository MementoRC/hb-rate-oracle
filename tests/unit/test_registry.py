"""Unit tests for rate_oracle.core.registry."""

import pytest

from rate_oracle.core.rate_source_base import RateSourceBase
from rate_oracle.core.registry import (
    RATE_ORACLE_SOURCES,
    get_source_class,
    register_source,
    unregister_source,
)
from rate_oracle.sources.coin_cap_source import CoinCapRateSource
from rate_oracle.sources.coin_gecko_source import CoinGeckoRateSource


class DummySource(RateSourceBase):
    @property
    def name(self) -> str:
        return "dummy"

    async def get_prices(self, quote_token=None):
        return {}


@pytest.fixture(autouse=True)
def restore_registry():
    snapshot = dict(RATE_ORACLE_SOURCES)
    yield
    RATE_ORACLE_SOURCES.clear()
    RATE_ORACLE_SOURCES.update(snapshot)


def test_defaults_present():
    assert RATE_ORACLE_SOURCES["coin_gecko"] is CoinGeckoRateSource
    assert RATE_ORACLE_SOURCES["coin_cap"] is CoinCapRateSource


def test_register_new():
    register_source("dummy", DummySource)
    assert get_source_class("dummy") is DummySource


def test_duplicate_raises():
    with pytest.raises(ValueError):
        register_source("coin_gecko", DummySource)


def test_replace_overwrites():
    register_source("coin_gecko", DummySource, replace=True)
    assert get_source_class("coin_gecko") is DummySource


def test_non_subclass_raises_type_error():
    with pytest.raises(TypeError):
        register_source("bad", dict)  # type: ignore[arg-type]


def test_unregister():
    register_source("dummy", DummySource)
    unregister_source("dummy")
    assert "dummy" not in RATE_ORACLE_SOURCES
    unregister_source("dummy")


def test_get_source_class_unknown_lists_available():
    with pytest.raises(KeyError, match="coin_cap"):
        get_source_class("missing")
