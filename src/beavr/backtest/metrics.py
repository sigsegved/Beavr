"""Performance metrics calculation for backtests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Optional

from beavr.models.trade import Trade


@dataclass
class BacktestMetrics:
    """Performance metrics from a backtest run.

    Attributes:
        initial_cash: Starting cash balance
        final_value: Final portfolio value
        total_return: Total return as decimal (0.1 = 10%)
        cagr: Compound annual growth rate
        max_drawdown: Maximum drawdown from peak
        sharpe_ratio: Risk-adjusted return metric
        total_trades: Number of trades executed
        buy_trades: Number of buy trades
        sell_trades: Number of sell trades
        total_invested: Total dollar amount invested
        holdings: Final position quantities by symbol
        win_rate: Percentage of profitable trades (for sell trades)
        avg_trade_return: Average return per trade
    """

    initial_cash: Decimal
    final_value: Decimal
    total_return: float
    cagr: Optional[float]
    max_drawdown: Optional[float]
    sharpe_ratio: Optional[float]
    total_trades: int
    buy_trades: int
    sell_trades: int
    total_invested: Decimal
    holdings: dict[str, Decimal]
    win_rate: Optional[float] = None
    avg_trade_return: Optional[float] = None


def calculate_total_return(initial: Decimal, final: Decimal) -> float:
    """Calculate simple total return as percentage.

    Args:
        initial: Initial value
        final: Final value

    Returns:
        Total return as decimal (0.1 = 10%)
    """
    if initial == Decimal("0"):
        return 0.0
    return float((final - initial) / initial)


def calculate_cagr(
    initial: Decimal,
    final: Decimal,
    years: float,
) -> Optional[float]:
    """Calculate compound annual growth rate.

    Args:
        initial: Initial value
        final: Final value
        years: Number of years

    Returns:
        CAGR as decimal, or None if cannot be calculated
    """
    if years <= 0:
        return None
    if initial <= Decimal("0"):
        return None
    if final < Decimal("0"):
        return None

    # CAGR = (final / initial)^(1/years) - 1
    try:
        return (float(final / initial) ** (1 / years)) - 1
    except (OverflowError, ZeroDivisionError):
        return None


def calculate_max_drawdown(daily_values: list[Decimal]) -> Optional[float]:
    """Calculate maximum drawdown from peak.

    Maximum drawdown is the largest percentage drop from a peak to a trough.

    Args:
        daily_values: List of daily portfolio values

    Returns:
        Maximum drawdown as decimal (0.1 = 10% drawdown), or None
    """
    if not daily_values or len(daily_values) < 2:
        return None

    max_drawdown = Decimal("0")
    peak = daily_values[0]

    for value in daily_values[1:]:
        if value > peak:
            peak = value
        elif peak > Decimal("0"):
            drawdown = (peak - value) / peak
            if drawdown > max_drawdown:
                max_drawdown = drawdown

    return float(max_drawdown)


def calculate_daily_returns(daily_values: list[Decimal]) -> list[float]:
    """Calculate daily returns from portfolio values.

    Args:
        daily_values: List of daily portfolio values

    Returns:
        List of daily returns
    """
    if len(daily_values) < 2:
        return []

    returns = []
    for i in range(1, len(daily_values)):
        if daily_values[i - 1] > Decimal("0"):
            ret = float((daily_values[i] - daily_values[i - 1]) / daily_values[i - 1])
            returns.append(ret)

    return returns


def calculate_sharpe_ratio(
    daily_values: list[Decimal],
    risk_free_rate: float = 0.0,
) -> Optional[float]:
    """Calculate annualized Sharpe ratio.

    Sharpe Ratio = (mean return - risk-free rate) / std dev * sqrt(252)

    Args:
        daily_values: List of daily portfolio values
        risk_free_rate: Annual risk-free rate (e.g., 0.05 for 5%)

    Returns:
        Annualized Sharpe ratio, or None if cannot be calculated
    """
    if len(daily_values) < 2:
        return None

    returns = calculate_daily_returns(daily_values)
    if len(returns) < 2:
        return None

    # Calculate mean and standard deviation
    mean_return = sum(returns) / len(returns)

    # Convert annual risk-free rate to daily
    daily_rf = (1 + risk_free_rate) ** (1 / 252) - 1

    # Calculate standard deviation
    variance = sum((r - mean_return) ** 2 for r in returns) / (len(returns) - 1)
    if variance <= 0:
        return None
    std_dev = variance ** 0.5

    if std_dev == 0:
        return None

    # Annualize: multiply by sqrt(252)
    sharpe = ((mean_return - daily_rf) / std_dev) * (252 ** 0.5)
    return sharpe


def calculate_years_between(start: date, end: date) -> float:
    """Calculate number of years between two dates.

    Args:
        start: Start date
        end: End date

    Returns:
        Number of years as float
    """
    days = (end - start).days
    return days / 365.25


def calculate_metrics(
    initial_cash: Decimal,
    final_value: Decimal,
    daily_values: list[Decimal],
    trades: list[Trade],
    start_date: date,
    end_date: date,
    risk_free_rate: float = 0.0,
) -> BacktestMetrics:
    """Calculate all performance metrics from backtest results.

    Args:
        initial_cash: Starting cash balance
        final_value: Final portfolio value
        daily_values: List of daily portfolio values
        trades: List of executed trades
        start_date: Backtest start date
        end_date: Backtest end date
        risk_free_rate: Annual risk-free rate for Sharpe calculation

    Returns:
        BacktestMetrics with all calculated metrics
    """
    years = calculate_years_between(start_date, end_date)

    # Calculate total invested (sum of buy amounts)
    total_invested = sum(
        (t.amount for t in trades if t.side == "buy"),
        Decimal("0"),
    )

    # Calculate holdings (final positions)
    holdings: dict[str, Decimal] = {}
    for trade in trades:
        if trade.side == "buy":
            holdings[trade.symbol] = holdings.get(trade.symbol, Decimal("0")) + trade.quantity
        else:  # sell
            holdings[trade.symbol] = holdings.get(trade.symbol, Decimal("0")) - trade.quantity

    # Remove zero positions
    holdings = {k: v for k, v in holdings.items() if v > Decimal("0")}

    # Count buy and sell trades
    buy_trades = sum(1 for t in trades if t.side == "buy")
    sell_trades = sum(1 for t in trades if t.side == "sell")

    return BacktestMetrics(
        initial_cash=initial_cash,
        final_value=final_value,
        total_return=calculate_total_return(initial_cash, final_value),
        cagr=calculate_cagr(initial_cash, final_value, years),
        max_drawdown=calculate_max_drawdown(daily_values),
        sharpe_ratio=calculate_sharpe_ratio(daily_values, risk_free_rate),
        total_trades=len(trades),
        buy_trades=buy_trades,
        sell_trades=sell_trades,
        total_invested=total_invested,
        holdings=holdings,
    )
