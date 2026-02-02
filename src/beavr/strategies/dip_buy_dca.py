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
    """Hybrid DCA + Proportional Dip Buy strategy.

    Combines regular DCA with opportunistic dip buying:
    - Buy a base amount (50%) on the first trading day of each month
    - Reserve remaining budget (50%) for dip buying throughout the month
    - PROPORTIONAL: Buy more as dips get deeper (tiered approach)
    - Fallback at month-end to deploy any remaining budget

    Logic:
        On first trading day of month:
            Buy base_buy_pct (50%) of monthly budget

        Each subsequent day (using hourly data for intraday dips):
            Tier 1: 1% dip → buy 20% of remaining
            Tier 2: 2% dip → buy 40% of remaining
            Tier 3: 3%+ dip → buy 75% of remaining

        On last fallback_days of month:
            Deploy remaining budget evenly

    Example Configuration:
        symbols: ["VOO"]
        monthly_budget: 1000
        base_buy_pct: 0.50 (buy $500 on Day 1)
        dip_tier_1: 0.01, dip_tier_1_pct: 0.20 (1% dip → 20%)
        dip_tier_2: 0.02, dip_tier_2_pct: 0.40 (2% dip → 40%)
        dip_tier_3: 0.03, dip_tier_3_pct: 0.75 (3%+ dip → 75%)
        max_dip_buys: 8
        fallback_days: 3

        Result: $500 on Day 1, proportional buys on dips, remainder at month-end.
    """

    name: ClassVar[str] = "Dip Buy DCA"
    description: ClassVar[str] = "Hybrid DCA + proportional dip buying"
    version: ClassVar[str] = "3.0.0"
    param_model: ClassVar[Type[BaseModel]] = DipBuyDCAParams

    def __init__(self, params: DipBuyDCAParams) -> None:
        """Initialize the strategy.

        Args:
            params: Strategy configuration parameters
        """
        self.params = params
        # Track last buy price and dip count per month (reset monthly)
        self._last_buy_price: dict[str, Decimal] = {}
        self._dip_buy_count: int = 0
        self._current_month: int = 0

    @property
    def symbols(self) -> list[str]:
        """Get the symbols this strategy trades."""
        return list(self.params.symbols)

    def evaluate(self, ctx: StrategyContext) -> list[Signal]:
        """Evaluate the strategy and return trading signals.

        Args:
            ctx: Strategy context with market data and portfolio state

        Returns:
            List of buy signals based on DCA, dip detection, or fallback logic
        """
        signals = []

        # Reset tracking at start of new month
        if ctx.current_date.month != self._current_month:
            self._current_month = ctx.current_date.month
            self._dip_buy_count = 0
            self._last_buy_price = {}

        remaining_budget = ctx.period_budget - ctx.period_spent

        if remaining_budget <= Decimal("0"):
            return signals

        # Track remaining budget as we generate signals
        budget_left = remaining_budget

        for symbol in self.params.symbols:
            if symbol not in ctx.prices:
                continue

            price = ctx.prices[symbol]
            bars = ctx.bars.get(symbol, None) if ctx.bars else None

            # 1. First trading day of month: Buy base amount (DCA portion)
            if ctx.is_first_trading_day_of_month and self.params.base_buy_pct > 0:
                base_amount = ctx.period_budget * Decimal(str(self.params.base_buy_pct))
                if base_amount >= self.params.min_buy_amount and base_amount <= budget_left:
                    signals.append(
                        Signal(
                            symbol=symbol,
                            action="buy",
                            amount=base_amount,
                            reason="base_dca",
                            timestamp=datetime.combine(
                                ctx.current_date, datetime.min.time()
                            ),
                        )
                    )
                    budget_left -= base_amount
                    self._last_buy_price[symbol] = price
                continue  # Don't check for dips on first day

            # 2. Check for dip from last buy price (using hourly data if available)
            hourly = ctx.hourly_bars.get(symbol) if ctx.hourly_bars else None

            if (
                symbol in self._last_buy_price
                and self._dip_buy_count < self.params.max_dip_buys
            ):
                # Get proportional buy amount based on dip depth
                dip_pct, buy_fraction = self._get_proportional_buy(price, symbol, hourly)

                if buy_fraction > 0:
                    amount = budget_left * Decimal(str(buy_fraction))
                    if amount >= self.params.min_buy_amount:
                        # Determine reason based on tier
                        if dip_pct >= self.params.dip_tier_3:
                            reason = "dip_buy_t3"
                        elif dip_pct >= self.params.dip_tier_2:
                            reason = "dip_buy_t2"
                        else:
                            reason = "dip_buy_t1"

                        signals.append(
                            Signal(
                                symbol=symbol,
                                action="buy",
                                amount=amount,
                                reason=reason,
                                timestamp=datetime.combine(
                                    ctx.current_date, datetime.min.time()
                                ),
                            )
                        )
                        budget_left -= amount
                        self._last_buy_price[symbol] = price
                        self._dip_buy_count += 1

            # 3. Check for month-end fallback
            if self._should_fallback(ctx) and budget_left > Decimal("0"):
                # Spread remaining budget over remaining days
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

    def _get_proportional_buy(
        self,
        current_price: Decimal,
        symbol: str,
        hourly_bars: Optional[pd.DataFrame] = None,
    ) -> tuple[float, float]:
        """Get proportional buy fraction based on dip depth.

        Deeper dips trigger larger purchases:
        - Tier 3 (3%+ dip): 75% of remaining budget
        - Tier 2 (2% dip): 40% of remaining budget
        - Tier 1 (1% dip): 20% of remaining budget

        Args:
            current_price: Current price (or close price)
            symbol: The symbol to check
            hourly_bars: Optional hourly bar data for intraday dip detection

        Returns:
            Tuple of (dip_percentage, buy_fraction). Returns (0, 0) if no dip.
        """
        last_price = self._last_buy_price.get(symbol)
        if last_price is None or last_price == Decimal("0"):
            return (0.0, 0.0)

        # Calculate dip percentage from current/close price
        dip_pct = float((last_price - current_price) / last_price)

        # With hourly data, check if any intraday low hit a deeper tier
        if hourly_bars is not None and not hourly_bars.empty and "low" in hourly_bars.columns:
            recent_hours = hourly_bars.tail(self.params.lookback_hours)
            if not recent_hours.empty:
                intraday_low = Decimal(str(recent_hours["low"].min()))
                intraday_dip_pct = float((last_price - intraday_low) / last_price)
                # Use the deeper dip (intraday low vs close)
                dip_pct = max(dip_pct, intraday_dip_pct)

        # Determine buy fraction based on tier (check highest tier first)
        if dip_pct >= self.params.dip_tier_3:
            return (dip_pct, self.params.dip_tier_3_pct)
        elif dip_pct >= self.params.dip_tier_2:
            return (dip_pct, self.params.dip_tier_2_pct)
        elif dip_pct >= self.params.dip_tier_1:
            return (dip_pct, self.params.dip_tier_1_pct)
        else:
            return (dip_pct, 0.0)  # No dip threshold met

    def _is_dip_from_last_buy(
        self,
        current_price: Decimal,
        symbol: str,
        hourly_bars: Optional[pd.DataFrame] = None,
    ) -> bool:
        """Check if price dipped from the last buy price.

        With hourly data: Check if any hour today had a low that dipped
        below the threshold from last buy price.
        Without hourly data: Compare current (close) price to last buy.

        Args:
            current_price: Current price (or close price)
            symbol: The symbol to check
            hourly_bars: Optional hourly bar data for intraday dip detection

        Returns:
            True if price has dropped tier 1 threshold from last buy
        """
        last_price = self._last_buy_price.get(symbol)
        if last_price is None or last_price == Decimal("0"):
            return False

        threshold = float(last_price) * (1 - self.params.dip_tier_1)

        # With hourly data, check if any intraday low hit the threshold
        if hourly_bars is not None and not hourly_bars.empty and "low" in hourly_bars.columns:
            # Get today's hourly bars (last N hours based on lookback)
            recent_hours = hourly_bars.tail(self.params.lookback_hours)
            if not recent_hours.empty:
                intraday_low = recent_hours["low"].min()
                if intraday_low <= threshold:
                    return True

        # Fallback: check if current/close price is a dip
        drop_pct = float((last_price - current_price) / last_price)
        return drop_pct >= self.params.dip_tier_1

    def _is_dip(
        self,
        current_price: Decimal,
        bars: pd.DataFrame,
        hourly_bars: Optional[pd.DataFrame] = None,
    ) -> bool:
        """Check if current price represents a dip from recent high.

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
