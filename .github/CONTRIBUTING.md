# Contributing to hb-rate-oracle

Thank you for your interest in contributing to hb-rate-oracle! This document provides guidelines and information for contributors.

## Getting Started

### Prerequisites

- Python 3.10 or higher
- Git
- Either pixi, hatch, or uv package manager

### Development Setup

1. **Clone the repository**:
   ```bash
   git clone https://github.com/MementoRC/hb-rate-oracle.git
   cd hb-rate-oracle
   ```

2. **Set up development environment**:
   ```bash
   # Using pixi (recommended)
   pixi run pytest --version

   # Or using hatch
   hatch run dev:pytest --version
   ```

3. **Install pre-commit hooks**:
   ```bash
   pixi run pre-commit install
   ```

## Development Process

### Branch Strategy

- **main**: Production-ready code
- **development**: Main development branch for integration
- **feature/your-feature**: Feature development branches

### Workflow

1. **Create a feature branch**:
   ```bash
   git checkout development
   git pull origin development
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes**:
   - Follow coding standards (see below)
   - Write tests for new functionality
   - Update documentation as needed

3. **Run quality checks**:
   ```bash
   pixi run pytest                        # Run tests
   pixi run ruff check --select=F,E9      # Critical lint checks
   pixi run pre-commit run --all-files    # All hooks
   ```

4. **Commit your changes**:
   ```bash
   git add specific-files  # Be selective, don't use 'git add .'
   git commit -m "feat: add your feature description"
   ```

5. **Push and create PR**:
   ```bash
   git push origin feature/your-feature-name
   # Create PR through GitHub interface
   ```

## Coding Standards

### Python Style Guidelines

- **Type annotations**: Use modern Python 3.12 syntax (`list[T]`, `dict[K, V]`, `T | None`)
- **Import organization**: Use relative imports within packages
- **Line length**: 88 characters (Black default)
- **Naming**: snake_case for variables/functions, PascalCase for classes

### Code Quality Requirements

- **Zero critical violations**: No F or E9 lint errors allowed
- **Test coverage**: All new code must include tests
- **Type safety**: Use proper type annotations
- **Documentation**: Include docstrings for public APIs

### Example Code Style

```python
from typing import Any
from .core import RateSource

def fetch_rates(
    base_currency: str,
    quote_currencies: list[str],
    *,
    timeout: float = 10.0,
) -> dict[str, float]:
    """Fetch conversion rates for the given currency pair.

    :param base_currency: The base currency symbol (e.g., "USD")
    :param quote_currencies: List of quote currency symbols to fetch rates for
    :param timeout: Request timeout in seconds
    :return: Dictionary mapping quote currency to conversion rate
    :raises ValueError: If base_currency is empty or invalid
    """
    if not base_currency:
        raise ValueError("base_currency cannot be empty")

    return {
        "currency": base_currency,
        "count": len(quote_currencies),
    }
```

## Testing Guidelines

### Test Organization

- **unit/**: Testing isolated components
- **integration/**: Testing component interactions
- **e2e/**: Testing complete workflows

### Writing Tests

```python
import pytest
from unittest.mock import patch, MagicMock

from rate_oracle.sources.coin_gecko_source import CoinGeckoRateSource

class TestCoinGeckoRateSource:
    def test_source_initialization(self):
        """Test rate source initializes correctly."""
        source = CoinGeckoRateSource()
        assert source is not None

    @patch('rate_oracle.sources.coin_gecko_source.aiohttp.ClientSession')
    async def test_fetch_rates(self, mock_session):
        """Test rate fetching functionality."""
        # Test implementation
        pass
```

### Running Tests

```bash
# Run all tests
pixi run pytest

# Run specific test types
pixi run pytest tests/unit/
pixi run pytest tests/integration/

# Run with coverage
pixi run pytest --cov=rate_oracle
```

## Documentation

### Code Documentation

- Use reStructuredText format for docstrings
- Document all public APIs
- Include examples for complex functionality
- Keep documentation up-to-date with code changes

## Security Considerations

### Security Best Practices

- **Never commit secrets**: Use environment variables for sensitive data
- **Validate inputs**: Sanitize all external inputs
- **Follow secure coding**: Use static analysis tools
- **Report vulnerabilities**: Use private vulnerability reporting

### Security Testing

All contributions are automatically scanned for:
- Secret detection
- Dependency vulnerabilities
- Code security issues (CodeQL)

## Adding New Rate Sources

### Implementing a New Source

1. **Create source structure**:
   ```
   rate_oracle/sources/your_source.py
   ```

2. **Implement required methods** by inheriting from `RateSourceBase`:
   - `fetch_rates()`
   - `get_prices()`

3. **Add comprehensive tests**:
   - Unit tests for all methods
   - Error handling tests
   - Mock API responses

4. **Update documentation**:
   - Add to supported sources list in README
   - Include usage examples
   - Document any special requirements (e.g., API keys)

## Pull Request Guidelines

### PR Description Template

```markdown
## Summary
Brief description of changes

## Changes Made
- List specific changes
- Include any breaking changes
- Note documentation updates

## Testing
- [ ] Unit tests pass
- [ ] Integration tests pass
- [ ] Manual testing completed
- [ ] No critical lint violations

## Security Review
- [ ] No secrets committed
- [ ] Dependencies reviewed
- [ ] Security scan passed
```

### Review Process

1. **Automated checks**: All CI checks must pass
2. **Code review**: At least one maintainer review required
3. **Security review**: Automatic security scanning
4. **Documentation**: Updates reviewed for accuracy

## Getting Help

### Resources

- **Documentation**: https://github.com/MementoRC/hb-rate-oracle
- **Issues**: Report bugs or request features
- **Discussions**: Ask questions or discuss ideas

### Contact

- **Security issues**: Use private vulnerability reporting
- **General questions**: Create a GitHub issue
- **Feature requests**: Create a GitHub issue with "enhancement" label

## Recognition

Contributors will be recognized in:
- Release notes for significant contributions
- Contributors list in repository
- Security advisories (for security researchers)

Thank you for contributing to hb-rate-oracle!
