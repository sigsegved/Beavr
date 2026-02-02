"""Buy and Hold strategy implementation."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import ClassVar, Type

from pydantic import BaseModel

from beavr.models.config import BuyAndHoldParams
from beavr.models.signal import Signal
from beavr.strategies.base import BaseStrategy
from beavr.strategies.context import StrategyContext
from beavr.strategies.registry import register_strategy


@register_strategy("buy_and_hold")
class BuyAndHoldStrategy(BaseStrategy):
    """Buy and Hold strategy.

    The simplest strategy: buy everything on day 1, hold forever.
    Classic passive investing baseline for comparison.

    Logic:
        On first day:
            Buy with all available cash

        Every other day:
            Do nothing (hold)
    """

    name: ClassVar[str] = "Buy and Hold"
    description: ClassVar[str] = "Buy once on day 1, hold forever"
    version: ClassVar[str] = "1.0.0"
    param_model: ClassVar[Type[BaseModel]] = BuyAndHoldParams

    def __init__(self, params: BuyAndHoldParams) -> None:
        """Initialize the strategy.

        Args:
            params: Strategy configuration parameters
        """
        self.params = params
        self._bought: bool = False

    @property
    def symbols(self) -> list[str]:
        """Get the symbols this strategy trades."""
        return list(self.params.symbols)

    def evaluate(self, ctx: StrategyContext) -> list[Signal]:
        """Evaluate the strategy and return trading signals.

        Args:
            ctx: Strategy context with market data and portfolio state

        Returns:
            Buy signal on first day, empty list thereafter
        """
        if self._bought:
            return []

        signals = []
        
        # Buy all symbols with equal allocation
        amount_per_symbol = ctx.cash / Decimal(len(self.params.symbols))

        for symbol in self.params.symbols:
            if symbol not in ctx.prices:
                continue

            if amount_per_symbol > Decimal("1"):
                signals.append(
                    Signal(
                        symbol=symbol,
                        action="buy",
                        amount=amount_per_symbol,
                        reason="buy_and_hold",
                        timestamp=datetime.combine(
                            ctx.current_date, datetime.min.time()
                        ),
                    )
                )

        if signals:
            self._bought = True

        return signals
