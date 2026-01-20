# Beavr 🦫

> An open-source automated trading platform for retail investors

[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## Features

- 📊 **Backtesting Engine** - Test strategies against historical data
- 💰 **DCA Strategies** - Dollar-cost averaging with dip buying
- 📈 **Alpaca Integration** - Historical data from Alpaca Markets
- ⚙️ **TOML Configuration** - Configure strategies without writing code
- 🎨 **Rich CLI** - Beautiful terminal output with tables and colors

## Installation

```bash
# Clone the repository
git clone https://github.com/sigsegved/Beavr.git
cd Beavr

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -e ".[dev]"
```

## Quick Start

1. **Set up Alpaca API credentials:**

```bash
cp .env.example .env
# Edit .env with your API keys from https://app.alpaca.markets/
export $(grep -v '^#' .env | xargs)
```

2. **Run a backtest:**

```bash
bvr backtest run simple_dca SPY --start 2024-01-01 --end 2024-06-30
```

3. **Compare strategies:**

```bash
bvr backtest compare simple_dca dip_buy_dca SPY --start 2024-01-01 --end 2024-06-30
```

4. **List available strategies:**

```bash
bvr backtest strategies
```

## Documentation

- 📖 [Quick Start Guide](docs/QUICKSTART.md) - Get up and running in 5 minutes
- ⚙️ [Configuration](docs/CONFIGURATION.md) - Environment variables and TOML configs
- 📊 [Strategies](docs/STRATEGIES.md) - Built-in strategies and creating your own

## Available Strategies

| Strategy | Description |
|----------|-------------|
| `simple_dca` | Dollar-cost average on a fixed schedule |
| `dip_buy_dca` | Buy on dips with month-end fallback |

See [examples/strategies/](examples/strategies/) for sample configurations.

## CLI Commands

```bash
bvr backtest run <strategy> <symbols>  # Run a backtest
bvr backtest compare <s1> <s2> <symbols>  # Compare strategies
bvr backtest list                      # List past backtests
bvr backtest show <run-id>             # Show backtest details
bvr backtest export <run-id> <file>    # Export to CSV
bvr backtest strategies                # List available strategies
```

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run tests with coverage
pytest --cov=src/beavr

# Run slow integration tests (requires Alpaca credentials)
pytest -m slow

# Run linter
ruff check .

# Run type checker
mypy src/
```

## Project Structure

```
src/beavr/
├── backtest/     # Backtesting engine
├── cli/          # Command-line interface
├── data/         # Data fetching (Alpaca)
├── db/           # Database layer
├── models/       # Pydantic data models
└── strategies/   # Strategy implementations
```

## License

MIT License - see [LICENSE](LICENSE) for details.
