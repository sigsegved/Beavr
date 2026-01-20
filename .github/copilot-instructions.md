# Beavr Development Guidelines

## Project Overview
Beavr is an open-source automated trading platform for retail investors. It emphasizes simplicity and extensibility - strategies are Python classes with a common interface, configured via TOML.

## Tech Stack
- **Language**: Python 3.11+
- **Type Checking**: Pydantic for models, mypy for static analysis
- **Broker Integration**: alpaca-py (official Alpaca SDK)
- **CLI**: Typer + Rich
- **Configuration**: TOML + Pydantic Settings
- **Database**: SQLite
- **Testing**: pytest
- **Linting**: ruff

## Code Style Guidelines

### General
- Use type hints for all function parameters and return values
- Use `Decimal` for all money/price/quantity fields (never float)
- Use Pydantic models for data validation and serialization
- Use `frozen=True` for immutable models where appropriate
- Follow the single responsibility principle
- Write docstrings for all public functions and classes

### File Organization
```
src/beavr/
├── models/       # Pydantic data models
├── strategies/   # Strategy implementations  
├── backtest/     # Backtesting engine
├── data/         # Data fetching (Alpaca)
├── db/           # Database layer
├── core/         # Core utilities
└── cli/          # CLI commands
```

### Naming Conventions
- Classes: PascalCase (e.g., `BacktestEngine`, `SimpleDCAStrategy`)
- Functions/methods: snake_case (e.g., `get_bars`, `calculate_metrics`)
- Constants: UPPER_SNAKE_CASE (e.g., `DEFAULT_TIMEFRAME`)
- Private methods: prefix with underscore (e.g., `_fetch_from_alpaca`)

### Error Handling
- Use custom exceptions for domain-specific errors
- Provide helpful error messages with context
- Log errors appropriately

### Testing
- Write unit tests for all business logic
- Use pytest fixtures for common setup
- Use in-memory SQLite for database tests
- Aim for >80% code coverage

## Key Patterns

### Strategy Interface
All strategies inherit from `BaseStrategy` and implement `evaluate()`:
```python
class MyStrategy(BaseStrategy):
    def evaluate(self, ctx: StrategyContext) -> list[Signal]:
        # Return trading signals based on context
        pass
```

### Repository Pattern
Database access is abstracted through repository classes:
```python
class BarCache:
    def get_bars(self, symbol, start, end) -> pd.DataFrame | None
    def save_bars(self, symbol, bars) -> None
```

### Configuration
- App config uses Pydantic Settings with env var support
- Strategy params are defined as Pydantic Fields with validation
- Users configure via TOML files
