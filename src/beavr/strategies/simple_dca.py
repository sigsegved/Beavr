"""Simple DCA strategy implementation."""

from datetime import datetime
from typing import ClassVar, Type

from pydantic import BaseModel

from beavr.models.config import SimpleDCAParams
from beavr.models.signal import Signal
from beavr.strategies.base import BaseStrategy
from beavr.strategies.context import StrategyContext
from beavr.strategies.registry import register_strategy


@register_strategy("simple_dca")
class SimpleDCAStrategy(BaseStrategy):
    """Simple Dollar-Cost Averaging strategy.

    Buys a fixed dollar amount at regular intervals (weekly, biweekly, or monthly).
    The investment is split equally among all configured symbols.

    Logic:
        Every [frequency] on [day]:
            For each symbol:
                Buy [amount / num_symbols] dollars worth

    Example Configuration:
        symbols: ["SPY", "QQQ"]
        amount: 500
        frequency: monthly
        day_of_month: 1

        Result: Buy $250 of SPY and $250 of QQQ on the 1st of each month.
    """

    name: ClassVar[str] = "Simple DCA"
    description: ClassVar[str] = "Buy fixed amount at regular intervals"
    version: ClassVar[str] = "1.0.0"
    param_model: ClassVar[Type[BaseModel]] = SimpleDCAParams

    def __init__(self, params: SimpleDCAParams) -> None:
        """Initialize the strategy.

        Args:
            params: Strategy configuration parameters
        """
        self.params = params

    @property
    def symbols(self) -> list[str]:
        """Get the symbols this strategy trades."""
        return list(self.params.symbols)

    def evaluate(self, ctx: StrategyContext) -> list[Signal]:
        """Evaluate the strategy and return trading signals.

        Args:
            ctx: Strategy context with market data and portfolio state

        Returns:
            List of buy signals if it's a buy day, empty list otherwise
        """
        signals = []

        if not self._is_buy_day(ctx):
            return signals

        # Calculate per-symbol amount
        num_symbols = len(self.params.symbols)
        amount_per_symbol = self.params.amount / num_symbols

        # Track remaining cash (signals consume cash during evaluation)
        remaining_cash = ctx.cash

        for symbol in self.params.symbols:
            # Check if we have enough cash
            if remaining_cash >= amount_per_symbol:
                signals.append(
                    Signal(
                        symbol=symbol,
                        action="buy",
                        amount=amount_per_symbol,
                        reason="scheduled",
                        timestamp=datetime.combine(ctx.current_date, datetime.min.time()),
                    )
                )
                remaining_cash -= amount_per_symbol

        return signals

    def _is_buy_day(self, ctx: StrategyContext) -> bool:
        """Check if today is a buy day.

        Args:
            ctx: Strategy context

        Returns:
            True if today matches the configured buy schedule
        """
        if self.params.frequency == "monthly":
            # For monthly, check if day of month matches
            # Handle case where target day doesn't exist (e.g., 31st in February)
            # In that case, buy on the last trading day of month
            if ctx.day_of_month == self.params.day_of_month:
                return True
            # If we're past the target day and it hasn't occurred yet this month
            # (e.g., target is 31st but month only has 30 days)
            # Buy on last trading day
            if ctx.is_last_trading_day_of_month and ctx.day_of_month < self.params.day_of_month:
                return True
            return False

        elif self.params.frequency == "weekly":
            # For weekly, check day of week (0=Monday)
            return ctx.day_of_week == self.params.day_of_week

        elif self.params.frequency == "biweekly":
            # For biweekly, check day of week and week number
            # Buy every other week starting from week 1
            if ctx.day_of_week != self.params.day_of_week:
                return False
            # Use ISO week number, buy on odd weeks
            week_num = ctx.current_date.isocalendar()[1]
            return week_num % 2 == 1

        return False
