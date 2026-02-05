# Beavr - Automated Trading Platform

## Overview
Beavr is a Python automated trading platform for retail investors featuring:
- Multi-agent AI trading system (LLM-powered)
- Strategy framework (DCA, Swing trading)
- Backtesting engine
- Alpaca broker integration

## Tech Stack
- **Python 3.11+** with complete type hints
- **Pydantic v2** for all data models
- **alpaca-py** for broker integration
- **Typer + Rich** for CLI
- **SQLite** for local database
- **pytest** for testing
- **ruff** for linting

## Critical Rules

### ALWAYS use Decimal for money
```python
# ✅ Correct
price: Decimal = Decimal("100.50")

# ❌ Never - causes financial bugs
price: float = 100.50
```

### ALWAYS add type hints
```python
# ✅ Correct
def calculate(entry: Decimal, exit: Decimal) -> Decimal:

# ❌ Never
def calculate(entry, exit):
```

### ALWAYS use Pydantic for domain objects
```python
# ✅ Correct
class Position(BaseModel):
    symbol: str
    shares: Decimal

# ❌ Never
position = {"symbol": "SPY", "shares": 10}
```

## Project Structure
```
src/beavr/
├── models/        # Pydantic data models
├── strategies/    # Trading strategies (BaseStrategy)
├── agents/        # AI agents (BaseAgent)
├── orchestrator/  # Multi-agent coordination
├── backtest/      # Backtesting engine
├── data/          # Market data (Alpaca)
├── db/            # Database (SQLite)
├── cli/           # CLI commands
└── llm/           # LLM client
```

## Build & Test Commands
```bash
# Install
pip install -e ".[dev,ai]"

# Run all tests
pytest

# Run unit tests only
pytest tests/unit/ -v

# Lint
ruff check src/

# CLI
bvr --help
bvr ai status
bvr ai analyze --amount 1000
```

## Validation Steps
After making changes, always run:
1. `pytest tests/unit/` - unit tests must pass
2. `ruff check src/` - no linting errors
3. Verify type hints are complete
