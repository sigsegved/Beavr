---
applyTo: "src/beavr/strategies/**/*.py"
---

# Strategy Development Rules

All strategies inherit from `BaseStrategy` and implement `evaluate()`.

## Required Pattern

```python
from __future__ import annotations

from decimal import Decimal
from typing import ClassVar

from pydantic import Field

from beavr.models.signal import Signal
from beavr.strategies.base import BaseStrategy, StrategyContext


class MyStrategy(BaseStrategy):
    """
    Brief description of strategy.
    
    Detailed explanation of:
    - When it buys
    - When it sells
    - Risk management approach
    """
    
    name: ClassVar[str] = "my_strategy"
    description: ClassVar[str] = "Brief description"
    
    # Parameters with validation
    threshold: float = Field(
        default=0.05,
        ge=0.01,
        le=0.50,
        description="Trigger threshold"
    )
    
    def evaluate(self, ctx: StrategyContext) -> list[Signal]:
        """
        Generate trading signals based on context.
        
        Args:
            ctx: Market and portfolio state
            
        Returns:
            List of Signal objects (may be empty)
        """
        signals: list[Signal] = []
        
        # Access market data via ctx.bars, ctx.prices
        # Access portfolio via ctx.portfolio
        # Use self.threshold for parameters
        
        return signals
```

## Rules

1. **Decimal for money** - prices, quantities, values
2. **Parameters via Field()** - with ge/le validation
3. **Docstrings required** - explain buy/sell logic
4. **Return empty list** - when no action needed

## Required Test File
`tests/unit/test_strategy_<name>.py`
