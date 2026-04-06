# hb-rate-oracle

Token rate oracle for hummingbot price feeds.

## Overview

Provides real-time token price rates from multiple sources for use in trading strategy calculations, portfolio valuation, and cross-exchange arbitrage detection.

## Features

- Multi-source price aggregation
- Configurable rate providers
- Drop-in replacement for hummingbot via `hb_compat` layer

## Installation

```bash
pixi install
```

## Development

```bash
pixi run check    # lint + format + test
pixi run test     # run all tests
pixi run lint     # ruff check
pixi run format   # ruff format
```

## License

Apache-2.0 — see [LICENSE](LICENSE)
