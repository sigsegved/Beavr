"""Tests for performance metrics calculation."""

from datetime import date, datetime
from decimal import Decimal

import pytest

from beavr.backtest.metrics import (
    BacktestMetrics,
    calculate_cagr,
    calculate_daily_returns,
    calculate_max_drawdown,
    calculate_metrics,
    calculate_sharpe_ratio,
    calculate_total_return,
    calculate_years_between,
)
from beavr.models.trade import Trade


class TestTotalReturn:
    """Tests for total return calculation."""

    def test_positive_return(self) -> None:
        """Test positive return calculation."""
        result = calculate_total_return(
            Decimal("10000"),
            Decimal("12000"),
        )
        assert result == pytest.approx(0.2, rel=1e-6)

    def test_negative_return(self) -> None:
        """Test negative return calculation."""
        result = calculate_total_return(
            Decimal("10000"),
            Decimal("8000"),
        )
        assert result == pytest.approx(-0.2, rel=1e-6)

    def test_zero_return(self) -> None:
        """Test zero return calculation."""
        result = calculate_total_return(
            Decimal("10000"),
            Decimal("10000"),
        )
        assert result == 0.0

    def test_zero_initial(self) -> None:
        """Test with zero initial value."""
        result = calculate_total_return(
            Decimal("0"),
            Decimal("10000"),
        )
        assert result == 0.0


class TestCAGR:
    """Tests for CAGR calculation."""

    def test_positive_cagr(self) -> None:
        """Test positive CAGR calculation."""
        # $10,000 to $17,716 in 5 years = 12% CAGR
        result = calculate_cagr(
            Decimal("10000"),
            Decimal("17716"),
            5.0,
        )
        assert result is not None
        assert result == pytest.approx(0.12, rel=0.01)

    def test_zero_years(self) -> None:
        """Test with zero years returns None."""
        result = calculate_cagr(
            Decimal("10000"),
            Decimal("12000"),
            0.0,
        )
        assert result is None

    def test_negative_years(self) -> None:
        """Test with negative years returns None."""
        result = calculate_cagr(
            Decimal("10000"),
            Decimal("12000"),
            -1.0,
        )
        assert result is None

    def test_zero_initial(self) -> None:
        """Test with zero initial returns None."""
        result = calculate_cagr(
            Decimal("0"),
            Decimal("12000"),
            5.0,
        )
        assert result is None

    def test_doubling_in_7_years(self) -> None:
        """Test doubling money in ~7 years (rule of 72 with 10%)."""
        result = calculate_cagr(
            Decimal("10000"),
            Decimal("20000"),
            7.2,
        )
        assert result is not None
        assert result == pytest.approx(0.10, rel=0.02)  # Allow 2% tolerance


class TestMaxDrawdown:
    """Tests for max drawdown calculation."""

    def test_simple_drawdown(self) -> None:
        """Test simple drawdown calculation."""
        # Peak at 100, trough at 80 = 20% drawdown
        values = [
            Decimal("100"),
            Decimal("110"),  # New peak
            Decimal("88"),   # 20% drop from 110
            Decimal("100"),
        ]
        result = calculate_max_drawdown(values)
        assert result is not None
        assert result == pytest.approx(0.2, rel=1e-6)

    def test_multiple_drawdowns(self) -> None:
        """Test with multiple drawdowns, returns maximum."""
        values = [
            Decimal("100"),
            Decimal("95"),   # 5% drawdown
            Decimal("110"),  # New peak
            Decimal("88"),   # 20% drawdown
            Decimal("120"),  # New peak
            Decimal("108"),  # 10% drawdown
        ]
        result = calculate_max_drawdown(values)
        assert result is not None
        assert result == pytest.approx(0.2, rel=1e-6)

    def test_no_drawdown(self) -> None:
        """Test with monotonically increasing values."""
        values = [
            Decimal("100"),
            Decimal("110"),
            Decimal("120"),
            Decimal("130"),
        ]
        result = calculate_max_drawdown(values)
        assert result is not None
        assert result == 0.0

    def test_empty_values(self) -> None:
        """Test with empty values returns None."""
        result = calculate_max_drawdown([])
        assert result is None

    def test_single_value(self) -> None:
        """Test with single value returns None."""
        result = calculate_max_drawdown([Decimal("100")])
        assert result is None


class TestDailyReturns:
    """Tests for daily returns calculation."""

    def test_simple_returns(self) -> None:
        """Test simple returns calculation."""
        values = [
            Decimal("100"),
            Decimal("110"),  # +10%
            Decimal("99"),   # -10%
        ]
        returns = calculate_daily_returns(values)
        assert len(returns) == 2
        assert returns[0] == pytest.approx(0.10, rel=1e-6)
        assert returns[1] == pytest.approx(-0.10, rel=1e-6)

    def test_empty_values(self) -> None:
        """Test with insufficient values."""
        assert calculate_daily_returns([]) == []
        assert calculate_daily_returns([Decimal("100")]) == []


class TestSharpeRatio:
    """Tests for Sharpe ratio calculation."""

    def test_positive_sharpe(self) -> None:
        """Test positive Sharpe ratio."""
        # Steady upward trend should have positive Sharpe
        values = [Decimal(str(100 + i * 0.1)) for i in range(252)]
        result = calculate_sharpe_ratio(values)
        assert result is not None
        assert result > 0

    def test_insufficient_data(self) -> None:
        """Test with insufficient data returns None."""
        assert calculate_sharpe_ratio([]) is None
        assert calculate_sharpe_ratio([Decimal("100")]) is None

    def test_with_risk_free_rate(self) -> None:
        """Test Sharpe ratio with non-zero risk-free rate."""
        values = [Decimal(str(100 + i * 0.1)) for i in range(252)]
        result_no_rf = calculate_sharpe_ratio(values, risk_free_rate=0.0)
        result_with_rf = calculate_sharpe_ratio(values, risk_free_rate=0.05)
        
        # Higher risk-free rate should reduce Sharpe
        assert result_no_rf is not None
        assert result_with_rf is not None
        assert result_with_rf < result_no_rf


class TestYearsBetween:
    """Tests for years between calculation."""

    def test_one_year(self) -> None:
        """Test calculating one year."""
        result = calculate_years_between(
            date(2024, 1, 1),
            date(2025, 1, 1),
        )
        assert result == pytest.approx(1.0, rel=0.01)

    def test_five_years(self) -> None:
        """Test calculating five years."""
        result = calculate_years_between(
            date(2020, 1, 1),
            date(2025, 1, 1),
        )
        assert result == pytest.approx(5.0, rel=0.01)

    def test_partial_year(self) -> None:
        """Test calculating partial year."""
        result = calculate_years_between(
            date(2024, 1, 1),
            date(2024, 7, 1),
        )
        assert result == pytest.approx(0.5, rel=0.02)


class TestCalculateMetrics:
    """Tests for full metrics calculation."""

    def test_basic_metrics(self) -> None:
        """Test basic metrics calculation."""
        trades = [
            Trade(
                symbol="SPY",
                side="buy",
                quantity=Decimal("10"),
                price=Decimal("100"),
                amount=Decimal("1000"),
                timestamp=datetime(2024, 1, 1),
                reason="scheduled",
            ),
            Trade(
                symbol="SPY",
                side="buy",
                quantity=Decimal("5"),
                price=Decimal("110"),
                amount=Decimal("550"),
                timestamp=datetime(2024, 2, 1),
                reason="scheduled",
            ),
        ]
        
        daily_values = [Decimal("10000")] * 365 + [Decimal("12000")]

        metrics = calculate_metrics(
            initial_cash=Decimal("10000"),
            final_value=Decimal("12000"),
            daily_values=daily_values,
            trades=trades,
            start_date=date(2024, 1, 1),
            end_date=date(2025, 1, 1),
        )

        assert metrics.initial_cash == Decimal("10000")
        assert metrics.final_value == Decimal("12000")
        assert metrics.total_return == pytest.approx(0.2, rel=1e-6)
        assert metrics.total_trades == 2
        assert metrics.total_invested == Decimal("1550")
        assert "SPY" in metrics.holdings
        assert metrics.holdings["SPY"] == Decimal("15")

    def test_metrics_with_sells(self) -> None:
        """Test metrics with buy and sell trades."""
        trades = [
            Trade(
                symbol="SPY",
                side="buy",
                quantity=Decimal("10"),
                price=Decimal("100"),
                amount=Decimal("1000"),
                timestamp=datetime(2024, 1, 1),
                reason="scheduled",
            ),
            Trade(
                symbol="SPY",
                side="sell",
                quantity=Decimal("5"),
                price=Decimal("120"),
                amount=Decimal("600"),
                timestamp=datetime(2024, 6, 1),
                reason="take_profit",
            ),
        ]

        metrics = calculate_metrics(
            initial_cash=Decimal("10000"),
            final_value=Decimal("10600"),
            daily_values=[Decimal("10000")] * 183 + [Decimal("10600")] * 183,
            trades=trades,
            start_date=date(2024, 1, 1),
            end_date=date(2025, 1, 1),
        )

        assert metrics.total_trades == 2
        assert metrics.total_invested == Decimal("1000")  # Only buy amounts
        assert metrics.holdings["SPY"] == Decimal("5")  # 10 bought - 5 sold

    def test_empty_trades(self) -> None:
        """Test metrics with no trades."""
        metrics = calculate_metrics(
            initial_cash=Decimal("10000"),
            final_value=Decimal("10000"),
            daily_values=[Decimal("10000")] * 366,
            trades=[],
            start_date=date(2024, 1, 1),
            end_date=date(2025, 1, 1),
        )

        assert metrics.total_trades == 0
        assert metrics.total_invested == Decimal("0")
        assert metrics.holdings == {}
        assert metrics.total_return == 0.0

    def test_metrics_dataclass(self) -> None:
        """Test BacktestMetrics dataclass."""
        metrics = BacktestMetrics(
            initial_cash=Decimal("10000"),
            final_value=Decimal("12000"),
            total_return=0.2,
            cagr=0.10,
            max_drawdown=0.15,
            sharpe_ratio=1.5,
            total_trades=10,
            total_invested=Decimal("5000"),
            holdings={"SPY": Decimal("20")},
        )

        assert metrics.initial_cash == Decimal("10000")
        assert metrics.total_return == 0.2
        assert metrics.cagr == 0.10
        assert metrics.max_drawdown == 0.15
        assert metrics.sharpe_ratio == 1.5
