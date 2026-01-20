"""Strategy context for evaluation."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Optional

import pandas as pd


@dataclass
class StrategyContext:
    """Context provided to strategy during evaluation.

    This dataclass contains all the information a strategy needs to make
    trading decisions on a given day.

    Attributes:
        current_date: The date being evaluated
        prices: Current closing prices by symbol
        bars: Historical bar data up to current_date by symbol
        hourly_bars: Optional hourly bar data for intraday analysis
        cash: Available cash in portfolio
        positions: Current share holdings by symbol
        period_budget: Budget allocated for the current period (month)
        period_spent: Amount already spent this period
        day_of_month: Day of the month (1-31)
        day_of_week: Day of the week (0=Monday, 6=Sunday)
        days_to_month_end: Trading days remaining in month
        is_first_trading_day_of_month: True if first trading day of month
        is_last_trading_day_of_month: True if last trading day of month
    """

    # Current evaluation point
    current_date: date

    # Market data
    prices: dict[str, Decimal]  # symbol -> current close price
    bars: dict[str, pd.DataFrame]  # symbol -> historical bars up to current_date

    # Portfolio state
    cash: Decimal
    positions: dict[str, Decimal]  # symbol -> shares held

    # Budget tracking (for DCA strategies)
    period_budget: Decimal
    period_spent: Decimal

    # Calendar helpers
    day_of_month: int
    day_of_week: int  # 0=Monday
    days_to_month_end: int
    is_first_trading_day_of_month: bool
    is_last_trading_day_of_month: bool
    
    # Optional hourly data (must be last due to default value)
    hourly_bars: Optional[dict[str, pd.DataFrame]] = field(default=None)  # symbol -> hourly bars

    @property
    def remaining_budget(self) -> Decimal:
        """Get remaining budget for the current period."""
        return self.period_budget - self.period_spent

    def get_position_value(self, symbol: str) -> Decimal:
        """Get current value of position in a symbol."""
        shares = self.positions.get(symbol, Decimal(0))
        price = self.prices.get(symbol, Decimal(0))
        return shares * price

    def get_total_position_value(self) -> Decimal:
        """Get total value of all positions."""
        return sum(
            self.positions.get(symbol, Decimal(0)) * price
            for symbol, price in self.prices.items()
        )

    def get_portfolio_value(self) -> Decimal:
        """Get total portfolio value (cash + positions)."""
        return self.cash + self.get_total_position_value()
