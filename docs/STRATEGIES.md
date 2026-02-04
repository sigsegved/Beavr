# Strategy Guide

Learn about Beavr's built-in strategies and how to create your own.

## Built-in Strategies

### Simple DCA (Dollar-Cost Averaging)

**Template name:** `simple_dca`

The simplest and most popular investment strategy. Invest a fixed amount on a regular schedule, regardless of market conditions.

**How it works:**
1. On each scheduled day, generate a BUY signal
2. Buy a fixed dollar amount of each configured symbol
3. Repeat on the next scheduled day

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `symbols` | list[str] | `["SPY"]` | Symbols to buy |
| `amount` | Decimal | `500` | Amount to invest per period |
| `frequency` | str | `"monthly"` | Investment frequency |
| `day_of_month` | int | `1` | Day of month to buy |

**Example configuration:**

```toml
template = "simple_dca"

[params]
symbols = ["SPY", "VTI"]
amount = 250
frequency = "monthly"
day_of_month = 15
```

**Best for:**
- Long-term investors
- Removing emotion from investing
- Building positions in index funds

---

### Dip Buy DCA

**Template name:** `dip_buy_dca`

An enhanced DCA strategy that buys on market dips and deploys remaining budget at month-end.

**How it works:**
1. Track the recent high price over a lookback window
2. When price drops by `dip_threshold` from the high, buy with a portion of the budget
3. If budget remains at month-end, deploy it in the final `fallback_days`

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `symbols` | list[str] | `["SPY"]` | Symbols to buy |
| `monthly_budget` | Decimal | `500` | Total budget per month |
| `dip_threshold` | float | `0.02` | Drop from high to trigger buy (2%) |
| `dip_buy_pct` | float | `0.5` | % of remaining budget per dip |
| `lookback_days` | int | `5` | Days to look back for high |
| `fallback_days` | int | `3` | Days before month-end for fallback |

**Example configuration:**

```toml
template = "dip_buy_dca"

[params]
symbols = ["QQQ"]
monthly_budget = 1000
dip_threshold = 0.03    # Buy on 3% dips
dip_buy_pct = 0.40      # Deploy 40% per dip
lookback_days = 10
fallback_days = 5
```

**Best for:**
- Investors who want to buy dips
- Those with a monthly budget to deploy
- Balancing opportunism with consistency

---

## Strategy Interface

All strategies inherit from `BaseStrategy`:

```python
from beavr.strategies.base import BaseStrategy, StrategyContext, Signal

class MyStrategy(BaseStrategy):
    """My custom strategy."""
    
    name: str = "My Strategy"
    description: str = "Does something cool"
    
    # Parameters with defaults
    symbols: list[str] = ["SPY"]
    
    def evaluate(self, ctx: StrategyContext) -> list[Signal]:
        """Evaluate and return trading signals."""
        signals = []
        
        for symbol in self.symbols:
            # Your logic here
            if should_buy(ctx, symbol):
                signals.append(
                    Signal(
                        symbol=symbol,
                        action="BUY",
                        amount=Decimal("100"),
                        reason="My reason",
                    )
                )
        
        return signals
```

## Strategy Context

The `StrategyContext` provides:

```python
@dataclass
class StrategyContext:
    current_date: date          # Current simulation date
    cash: Decimal               # Available cash
    positions: dict[str, int]   # Current holdings {symbol: shares}
    prices: dict[str, Decimal]  # Current prices {symbol: price}
```

## Signals

Strategies return `Signal` objects:

```python
@dataclass
class Signal:
    symbol: str           # Symbol to trade
    action: str           # "BUY" or "SELL"
    amount: Decimal       # Dollar amount
    reason: str           # Reason for the trade
```

## Comparing Strategies

Use the CLI to compare strategies:

```bash
bvr backtest compare simple_dca dip_buy_dca SPY --start 2020-01-01 --end 2024-01-01
```

**Sample comparison output:**

```
┏━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━┓
┃ Metric        ┃ Simple DCA     ┃ Dip Buy DCA    ┃
┡━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━┩
│ Final Value   │ $15,234.56     │ $15,891.23     │
│ Total Return  │ +52.35%        │ +58.91%        │
│ CAGR          │ 11.12%         │ 12.34%         │
│ Max Drawdown  │ -15.23%        │ -13.45%        │
│ Sharpe Ratio  │ 1.45           │ 1.67           │
│ Total Trades  │ 48             │ 63             │
└───────────────┴────────────────┴────────────────┘
```

## Creating Custom Strategies

1. Create a new file in `src/beavr/strategies/`:

```python
# src/beavr/strategies/my_strategy.py
from __future__ import annotations

from decimal import Decimal
from beavr.strategies.base import BaseStrategy, StrategyContext, Signal


class MyCustomStrategy(BaseStrategy):
    """My custom strategy."""
    
    name: str = "My Custom Strategy"
    description: str = "Description here"
    
    # Parameters
    symbols: list[str] = ["SPY"]
    my_param: Decimal = Decimal("100")
    
    def evaluate(self, ctx: StrategyContext) -> list[Signal]:
        signals = []
        # Your logic here
        return signals
```

2. Register in the strategy registry (if using TOML configs):

```python
# src/beavr/strategies/__init__.py
from beavr.strategies.my_strategy import MyCustomStrategy

STRATEGIES = {
    "simple_dca": SimpleDCAStrategy,
    "dip_buy_dca": DipBuyDCAStrategy,
    "my_strategy": MyCustomStrategy,
}
```

3. Create a TOML config:

```toml
# ~/.beavr/strategies/my_config.toml
template = "my_strategy"

[params]
symbols = ["AAPL", "GOOGL"]
my_param = 200
```
