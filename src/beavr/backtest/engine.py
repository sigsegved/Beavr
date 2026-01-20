"""Backtest engine - main backtesting loop."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import uuid4

import pandas as pd

from beavr.backtest.metrics import BacktestMetrics, calculate_metrics
from beavr.backtest.portfolio import SimulatedPortfolio
from beavr.data.alpaca import AlpacaDataFetcher
from beavr.db.results import BacktestResultsRepository
from beavr.models.trade import Trade
from beavr.strategies.base import BaseStrategy
from beavr.strategies.context import StrategyContext


@dataclass
class BacktestResult:
    """Result of a backtest run.

    Attributes:
        run_id: Unique identifier for this run
        strategy_name: Name of the strategy used
        start_date: Backtest start date
        end_date: Backtest end date
        metrics: Performance metrics
        trades: List of executed trades
        daily_values: Daily portfolio values for charting
    """

    run_id: str
    strategy_name: str
    start_date: date
    end_date: date
    metrics: BacktestMetrics
    trades: list[Trade]
    daily_values: list[tuple[date, Decimal]]


class BacktestEngine:
    """Main backtesting engine.

    Orchestrates the backtest simulation by:
    1. Fetching historical data
    2. Initializing portfolio
    3. Looping through each trading day
    4. Evaluating strategy and executing signals
    5. Calculating performance metrics
    6. Storing results (if repository provided)
    """

    def __init__(
        self,
        data_fetcher: AlpacaDataFetcher,
        results_repo: Optional[BacktestResultsRepository] = None,
    ) -> None:
        """Initialize the backtest engine.

        Args:
            data_fetcher: Data fetcher for historical prices
            results_repo: Optional repository for storing results
        """
        self.data = data_fetcher
        self.results_repo = results_repo

    def run(
        self,
        strategy: BaseStrategy,
        start_date: date,
        end_date: date,
        initial_cash: Decimal,
    ) -> BacktestResult:
        """Run a backtest simulation.

        Args:
            strategy: Strategy to test
            start_date: Start date for backtest
            end_date: End date for backtest
            initial_cash: Starting cash balance

        Returns:
            BacktestResult with metrics, trades, and daily values
        """
        # Create run record
        run_id = str(uuid4())

        # Fetch data for all symbols
        bars = self.data.get_multi_bars(
            symbols=strategy.symbols,
            start=start_date,
            end=end_date,
        )

        # Get trading days (days with data)
        trading_days = self._get_trading_days(bars, start_date, end_date)
        if not trading_days:
            raise ValueError("No trading days found in date range")

        # Initialize portfolio
        portfolio = SimulatedPortfolio(initial_cash)
        daily_values: list[tuple[date, Decimal]] = []

        # Budget tracking (for DCA strategies)
        current_month: Optional[int] = None
        period_budget = initial_cash  # Default to full cash as budget
        period_spent = Decimal("0")

        # If strategy has monthly budget in params, use that
        if hasattr(strategy, "params") and hasattr(strategy.params, "monthly_budget"):
            period_budget = strategy.params.monthly_budget
        elif hasattr(strategy, "params") and hasattr(strategy.params, "amount"):
            period_budget = strategy.params.amount

        # Main simulation loop
        for i, day in enumerate(trading_days):
            # Reset period tracking on new month
            if day.month != current_month:
                current_month = day.month
                period_spent = Decimal("0")
                # Call period start hook
                ctx = self._build_context(
                    day=day,
                    bars=bars,
                    portfolio=portfolio,
                    period_budget=period_budget,
                    period_spent=period_spent,
                    trading_days=trading_days,
                    current_index=i,
                )
                strategy.on_period_start(ctx)

            # Build context for this day
            ctx = self._build_context(
                day=day,
                bars=bars,
                portfolio=portfolio,
                period_budget=period_budget,
                period_spent=period_spent,
                trading_days=trading_days,
                current_index=i,
            )

            # Get signals from strategy
            signals = strategy.evaluate(ctx)

            # Execute signals
            for signal in signals:
                if signal.action == "buy" and signal.amount:
                    price = ctx.prices.get(signal.symbol, Decimal("0"))
                    if price > Decimal("0"):
                        trade = portfolio.buy(
                            symbol=signal.symbol,
                            amount=signal.amount,
                            price=price,
                            timestamp=datetime.combine(day, datetime.min.time()),
                            reason=signal.reason,
                        )
                        if trade:
                            period_spent += trade.amount
                elif signal.action == "sell" and signal.quantity:
                    price = ctx.prices.get(signal.symbol, Decimal("0"))
                    if price > Decimal("0"):
                        portfolio.sell(
                            symbol=signal.symbol,
                            quantity=signal.quantity,
                            price=price,
                            timestamp=datetime.combine(day, datetime.min.time()),
                            reason=signal.reason,
                        )

            # Track daily value
            daily_values.append((day, portfolio.get_value(ctx.prices)))

            # Check for period end and call hook
            if self._is_last_trading_day_of_month(trading_days, i):
                strategy.on_period_end(ctx)

        # Calculate final metrics
        final_prices = self._get_prices_for_day(bars, trading_days[-1])
        final_value = portfolio.get_value(final_prices)

        metrics = calculate_metrics(
            initial_cash=initial_cash,
            final_value=final_value,
            daily_values=[v for _, v in daily_values],
            trades=portfolio.trades,
            start_date=start_date,
            end_date=end_date,
        )

        # Store results if repository provided
        if self.results_repo:
            self.results_repo.create_run(
                run_id=run_id,
                strategy_name=strategy.name,
                start_date=start_date,
                end_date=end_date,
                initial_cash=initial_cash,
            )
            self.results_repo.save_results(run_id, metrics)
            self.results_repo.save_trades(run_id, portfolio.trades)

        return BacktestResult(
            run_id=run_id,
            strategy_name=strategy.name,
            start_date=start_date,
            end_date=end_date,
            metrics=metrics,
            trades=portfolio.trades,
            daily_values=daily_values,
        )

    def _build_context(
        self,
        day: date,
        bars: dict[str, pd.DataFrame],
        portfolio: SimulatedPortfolio,
        period_budget: Decimal,
        period_spent: Decimal,
        trading_days: list[date],
        current_index: int,
    ) -> StrategyContext:
        """Build strategy context for a given day.

        Args:
            day: Current date
            bars: Historical bar data
            portfolio: Current portfolio state
            period_budget: Budget for current period
            period_spent: Amount spent this period
            trading_days: List of all trading days
            current_index: Current index in trading_days

        Returns:
            StrategyContext with all relevant information
        """
        # Get prices and historical bars up to current date
        prices: dict[str, Decimal] = {}
        historical_bars: dict[str, pd.DataFrame] = {}

        for symbol, df in bars.items():
            if df.empty:
                continue

            # Filter to dates up to and including current day
            mask = df.index.date <= day
            historical = df[mask]

            if not historical.empty:
                # Get latest close price
                last_row = historical.iloc[-1]
                prices[symbol] = Decimal(str(last_row["close"]))
                historical_bars[symbol] = historical

        # Get current positions
        positions = {
            symbol: shares
            for symbol, shares in portfolio.positions.items()
        }

        # Calculate calendar helpers
        days_to_month_end = self._days_to_month_end(trading_days, current_index)

        return StrategyContext(
            current_date=day,
            prices=prices,
            bars=historical_bars,
            cash=portfolio.cash,
            positions=positions,
            period_budget=period_budget,
            period_spent=period_spent,
            day_of_month=day.day,
            day_of_week=day.weekday(),
            days_to_month_end=days_to_month_end,
            is_first_trading_day_of_month=self._is_first_trading_day_of_month(
                trading_days, current_index
            ),
            is_last_trading_day_of_month=self._is_last_trading_day_of_month(
                trading_days, current_index
            ),
        )

    def _get_trading_days(
        self,
        bars: dict[str, pd.DataFrame],
        start: date,
        end: date,
    ) -> list[date]:
        """Extract trading days from bar data.

        Returns sorted list of unique dates that have data for at least one symbol.

        Args:
            bars: Bar data by symbol
            start: Start date
            end: End date

        Returns:
            Sorted list of trading days
        """
        all_dates: set[date] = set()

        for df in bars.values():
            if df.empty:
                continue
            # Extract dates from index
            for idx in df.index:
                d = idx.date() if hasattr(idx, "date") else idx
                if start <= d <= end:
                    all_dates.add(d)

        return sorted(all_dates)

    def _get_prices_for_day(
        self,
        bars: dict[str, pd.DataFrame],
        day: date,
    ) -> dict[str, Decimal]:
        """Get closing prices for a specific day.

        Args:
            bars: Bar data by symbol
            day: Date to get prices for

        Returns:
            Dictionary of symbol -> closing price
        """
        prices: dict[str, Decimal] = {}

        for symbol, df in bars.items():
            if df.empty:
                continue

            # Find the row for this day
            mask = df.index.date == day
            day_data = df[mask]

            if not day_data.empty:
                prices[symbol] = Decimal(str(day_data.iloc[0]["close"]))

        return prices

    def _is_first_trading_day_of_month(
        self,
        trading_days: list[date],
        current_index: int,
    ) -> bool:
        """Check if current day is first trading day of month.

        Args:
            trading_days: List of all trading days
            current_index: Current index in the list

        Returns:
            True if first trading day of month
        """
        if current_index == 0:
            return True

        current_month = trading_days[current_index].month
        prev_month = trading_days[current_index - 1].month
        return current_month != prev_month

    def _is_last_trading_day_of_month(
        self,
        trading_days: list[date],
        current_index: int,
    ) -> bool:
        """Check if current day is last trading day of month.

        Args:
            trading_days: List of all trading days
            current_index: Current index in the list

        Returns:
            True if last trading day of month
        """
        if current_index >= len(trading_days) - 1:
            return True

        current_month = trading_days[current_index].month
        next_month = trading_days[current_index + 1].month
        return current_month != next_month

    def _days_to_month_end(
        self,
        trading_days: list[date],
        current_index: int,
    ) -> int:
        """Calculate trading days remaining in month.

        Args:
            trading_days: List of all trading days
            current_index: Current index in the list

        Returns:
            Number of trading days until end of month (excluding today)
        """
        current_month = trading_days[current_index].month
        count = 0

        for i in range(current_index + 1, len(trading_days)):
            if trading_days[i].month == current_month:
                count += 1
            else:
                break

        return count
