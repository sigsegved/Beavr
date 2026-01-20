"""Dip Buy DCA strategy implementation."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import ClassVar, Optional, Type

import pandas as pd
from pydantic import BaseModel

from beavr.models.config import DipBuyDCAParams
from beavr.models.signal import Signal
from beavr.strategies.base import BaseStrategy
from beavr.strategies.context import StrategyContext
from beavr.strategies.registry import register_strategy


@register_strategy("dip_buy_dca")
class DipBuyDCAStrategy(BaseStrategy):
    """Dip Buy Dollar-Cost Averaging strategy.

    Attempts to buy on price dips throughout the month, with a fallback
    mechanism to ensure all budget is deployed by month-end.

    Logic:
        Each day:
            Calculate recent high (lookback_days)
            If current price <= recent_high * (1 - dip_threshold):
                Buy dip_buy_pct of remaining monthly budget

        On last fallback_days of month:
            Deploy remaining budget evenly

    Example Configuration:
        symbols: ["VOO"]
        monthly_budget: 500
        dip_threshold: 0.02 (2% drop triggers buy)
        dip_buy_pct: 0.5 (deploy 50% of remaining budget on dip)
        lookback_days: 5
        fallback_days: 3

        Result: Buy on 2%+ dips, or spread remaining budget over last 3 days.
    """

    name: ClassVar[str] = "Dip Buy DCA"
    description: ClassVar[str] = "Buy on dips with month-end fallback"
    version: ClassVar[str] = "1.0.0"
    param_model: ClassVar[Type[BaseModel]] = DipBuyDCAParams

    def __init__(self, params: DipBuyDCAParams) -> None:
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
            List of buy signals based on dip detection or fallback logic
        """
        signals = []
        remaining_budget = ctx.period_budget - ctx.period_spent

        if remaining_budget <= Decimal("0"):
            return signals

        # Track remaining budget as we generate signals
        budget_left = remaining_budget

        for symbol in self.params.symbols:
            if symbol not in ctx.prices or symbol not in ctx.bars:
                continue

            price = ctx.prices[symbol]
            bars = ctx.bars[symbol]

            # Check for dip
            if self._is_dip(price, bars):
                # Buy a portion of remaining budget
                amount = budget_left * Decimal(str(self.params.dip_buy_pct))
                if amount >= self.params.min_buy_amount:
                    signals.append(
                        Signal(
                            symbol=symbol,
                            action="buy",
                            amount=amount,
                            reason="dip_buy",
                            timestamp=datetime.combine(
                                ctx.current_date, datetime.min.time()
                            ),
                        )
                    )
                    budget_left -= amount

            # Check for month-end fallback
            elif self._should_fallback(ctx):
                # Spread remaining budget over remaining days
                # Divide by number of symbols and remaining days
                num_fallback_days_left = max(1, ctx.days_to_month_end + 1)
                amount_per_day = budget_left / Decimal(str(num_fallback_days_left))
                amount_per_symbol = amount_per_day / len(self.params.symbols)

                if amount_per_symbol >= self.params.min_buy_amount:
                    signals.append(
                        Signal(
                            symbol=symbol,
                            action="buy",
                            amount=amount_per_symbol,
                            reason="fallback",
                            timestamp=datetime.combine(
                                ctx.current_date, datetime.min.time()
                            ),
                        )
                    )
                    budget_left -= amount_per_symbol

        return signals

    def _is_dip(self, current_price: Decimal, bars: pd.DataFrame) -> bool:
        """Check if current price represents a dip.

        A dip is defined as the current price being at least dip_threshold
        below the recent high (highest close in lookback period).

        Args:
            current_price: Current price
            bars: Historical bar data

        Returns:
            True if price is a dip
        """
        recent_high = self._get_recent_high(bars)
        if recent_high is None or recent_high == Decimal("0"):
            return False

        drop_pct = float((recent_high - current_price) / recent_high)
        return drop_pct >= self.params.dip_threshold

    def _get_recent_high(self, bars: pd.DataFrame) -> Optional[Decimal]:
        """Get highest close in lookback period.

        Args:
            bars: Historical bar data

        Returns:
            Highest close price in lookback period, or None if no data
        """
        if bars.empty or len(bars) < 1:
            return None

        recent = bars.tail(self.params.lookback_days)
        if "close" not in recent.columns:
            return None

        max_close = recent["close"].max()
        return Decimal(str(max_close))

    def _should_fallback(self, ctx: StrategyContext) -> bool:
        """Check if we should trigger fallback buy.

        Fallback is triggered on the last N days of the month.

        Args:
            ctx: Strategy context

        Returns:
            True if fallback should be triggered
        """
        return ctx.days_to_month_end < self.params.fallback_days
