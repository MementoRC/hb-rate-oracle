# hb-rate-oracle

A modular rate oracle for cryptocurrency price conversion, designed as a drop-in replacement for `hummingbot.core.rate_oracle`.

## Overview

`hb-rate-oracle` provides real-time cryptocurrency price conversion rates from multiple sources. It is architected as an independent sub-package of the Hummingbot ecosystem, enabling standalone usage or seamless integration with Hummingbot via the compatibility layer.

### Supported Rate Sources

| Source | Description | API Key Required |
|--------|-------------|-----------------|
| **CoinGecko** | Broad market coverage, free tier available | Optional (Pro) |
| **CoinCap** | Real-time price data | No |

## Installation

```bash
pip install hb-rate-oracle
```

Or with pixi:

```bash
pixi add hb-rate-oracle
```

## Quick Start

```python
import asyncio
from rate_oracle import RateOracle
from rate_oracle.sources.coin_gecko_source import CoinGeckoRateSource

async def main():
    # Create a rate oracle with CoinGecko as the source
    source = CoinGeckoRateSource()
    oracle = RateOracle(source=source)

    # Start the oracle
    await oracle.start()

    # Get conversion rate
    rate = oracle.get_price("BTC", "USD")
    print(f"BTC/USD: {rate}")

    # Stop the oracle
    await oracle.stop()

asyncio.run(main())
```

### Using CoinCap

```python
from rate_oracle import RateOracle
from rate_oracle.sources.coin_cap_source import CoinCapRateSource

async def main():
    source = CoinCapRateSource()
    oracle = RateOracle(source=source)
    await oracle.start()

    rate = oracle.get_price("ETH", "USD")
    print(f"ETH/USD: {rate}")

    await oracle.stop()
```

## Hummingbot Integration

When used with Hummingbot, the `hb_compat` layer provides a drop-in replacement for `hummingbot.core.rate_oracle`:

```python
# Instead of:
# from hummingbot.core.rate_oracle.rate_oracle import RateOracle

# Use:
from rate_oracle.hb_compat import RateOracle
```

The `hb_compat` module maintains API compatibility with the original Hummingbot rate oracle implementation, allowing existing strategies and connectors to work without modification.

### Supersedes

This package supersedes:
- `hummingbot.core.rate_oracle`
- Test paths: `test/hummingbot/core/rate_oracle`

## Development Setup

### Prerequisites

- Python 3.10 or higher
- [pixi](https://pixi.sh) (recommended) or hatch/uv

### Setup with pixi

```bash
# Clone the repository
git clone https://github.com/MementoRC/hb-rate-oracle.git
cd hb-rate-oracle

# Install dependencies and set up environment
pixi install

# Run tests
pixi run test-unit

# Run linting
pixi run lint

# Run all quality checks
pixi run quality
```

### Setup with hatch

```bash
hatch env create
hatch run pytest tests/unit/
```

### Available Tasks

| Task | Description |
|------|-------------|
| `pixi run test` | Run all tests |
| `pixi run test-unit` | Run unit tests only |
| `pixi run lint` | Run ruff linter |
| `pixi run format` | Format code with ruff |
| `pixi run format-check` | Check formatting without changes |
| `pixi run typecheck` | Run mypy type checking |
| `pixi run quality` | Run lint and type checks |
| `pixi run check` | Run all quality checks and tests |

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `COINGECKO_API_KEY` | CoinGecko Pro API key | None (free tier) |

## Architecture

```
rate_oracle/
├── core/
│   ├── rate_oracle.py        # Main RateOracle class
│   ├── rate_source_base.py   # Abstract base for rate sources
│   └── utils.py              # Utility functions
├── sources/
│   ├── coin_gecko_source.py  # CoinGecko rate source
│   └── coin_cap_source.py    # CoinCap rate source
└── hb_compat/
    └── __init__.py           # Hummingbot compatibility layer
```

## Features

- Multi-source price aggregation
- Configurable rate providers
- Drop-in replacement for hummingbot via `hb_compat` layer

## Contributing

See [CONTRIBUTING.md](.github/CONTRIBUTING.md) for guidelines on contributing to this project.

## License

Apache-2.0 — see [LICENSE](LICENSE)

## Related Projects

- [hb-candles-feed](https://github.com/MementoRC/hb-candles-feed) - Modular candles feed sub-package
- [Hummingbot](https://github.com/hummingbot/hummingbot) - The parent project
