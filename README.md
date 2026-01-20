# Beavr - Auto Trading Platform

An open-source automated trading platform for retail investors.

## Features

- **Backtesting Engine** - Test strategies against historical data
- **DCA Strategies** - Dollar-cost averaging with dip buying
- **Alpaca Integration** - Historical data from Alpaca Markets
- **TOML Configuration** - Configure strategies without writing code

## Installation

```bash
# Clone the repository
git clone https://github.com/sigsegved/Beavr.git
cd Beavr

# Install dependencies
pip install -e ".[dev]"
```

## Quick Start

```bash
# Set up Alpaca API credentials
cp .env.example .env
# Edit .env with your API keys

# Run a backtest
bvr backtest simple_dca --start 2020-01-01 --end 2025-01-01
```

## Configuration

Create a strategy configuration file in `~/.beavr/strategies/`:

```toml
template = "dip_buy_dca"

[params]
symbols = ["SPY", "QQQ"]
monthly_budget = 500
dip_threshold = 0.02
```

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run linter
ruff check .

# Run type checker
mypy src/
```

## License

MIT License - see [LICENSE](LICENSE) for details.
