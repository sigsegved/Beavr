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
            
            # Use hourly bars for dip detection if available and enabled
            hourly = None
            if self.params.use_hourly_data and ctx.hourly_bars:
                hourly = ctx.hourly_bars.get(symbol)

            # Check for dip (using hourly data if available)
            if self._is_dip(price, bars, hourly):
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

    def _is_dip(
        self,
        current_price: Decimal,
        bars: pd.DataFrame,
        hourly_bars: Optional[pd.DataFrame] = None,
    ) -> bool:
        """Check if current price represents a dip.

        A dip is defined as the current price being at least dip_threshold
        below the recent high (highest close in lookback period).

        Args:
            current_price: Current price
            bars: Historical daily bar data
            hourly_bars: Optional hourly bar data for finer granularity

        Returns:
            True if price is a dip
        """
        recent_high = self._get_recent_high(bars, hourly_bars)
        if recent_high is None or recent_high == Decimal("0"):
            return False

        drop_pct = float((recent_high - current_price) / recent_high)
        return drop_pct >= self.params.dip_threshold

    def _get_recent_high(
        self,
        bars: pd.DataFrame,
        hourly_bars: Optional[pd.DataFrame] = None,
    ) -> Optional[Decimal]:
        """Get highest close/high in lookback period.

        Uses hourly data if available for more precise high detection.

        Args:
            bars: Historical daily bar data
            hourly_bars: Optional hourly bar data

        Returns:
            Highest price in lookback period, or None if no data
        """
        # Use hourly data if available and enabled
        if hourly_bars is not None and not hourly_bars.empty:
            # Use lookback_hours parameter
            recent = hourly_bars.tail(self.params.lookback_hours)
            if "high" in recent.columns:
                max_high = recent["high"].max()
                return Decimal(str(max_high))
            elif "close" in recent.columns:
                max_close = recent["close"].max()
                return Decimal(str(max_close))

        # Fall back to daily data
        if bars.empty or len(bars) < 1:
            return None

        recent = bars.tail(self.params.lookback_days)
        
        # Use high column if available, else close
        if "high" in recent.columns:
            max_price = recent["high"].max()
        elif "close" in recent.columns:
            max_price = recent["close"].max()
        else:
            return None
            
        return Decimal(str(max_price))

    def _should_fallback(self, ctx: StrategyContext) -> bool:
        """Check if we should trigger fallback buy.

        Fallback is triggered on the last N days of the month.

        Args:
            ctx: Strategy context

        Returns:
            True if fallback should be triggered
        """
        return ctx.days_to_month_end < self.params.fallback_days
