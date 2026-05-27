"""Shared pytest fixtures for hb-rate-oracle tests."""

import pytest


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
