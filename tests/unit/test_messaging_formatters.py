"""Tests for message formatters."""

from decimal import Decimal

import pytest

from beavr.messaging.formatters import (
    format_dd_report,
    format_market_event,
    format_portfolio_status,
    format_position_closed,
    format_system_error,
    format_trade_executed,
)


class TestFormatDDReport:
    """Tests for format_dd_report."""

    def test_approved_report(self) -> None:
        result = format_dd_report(
            symbol="AAPL",
            recommendation="approve",
            confidence=0.87,
            trade_type="swing_short",
            entry=Decimal("185.00"),
            target=Decimal("195.00"),
            stop=Decimal("180.00"),
            position_size_pct=0.05,
        )
        assert "AAPL" in result
        assert "APPROVE" in result
        assert "87%" in result
        assert "Swing Short" in result
        assert "$185.00" in result
        assert "$195.00" in result
        assert "$180.00" in result

    def test_rejected_report(self) -> None:
        result = format_dd_report(
            symbol="TSLA",
            recommendation="reject",
            confidence=0.3,
        )
        assert "TSLA" in result
        assert "REJECT" in result
        assert "❌" in result

    def test_with_scenario_analysis(self) -> None:
        result = format_dd_report(
            symbol="SPY",
            recommendation="approve",
            confidence=0.75,
            bull_case="Market rally continues",
            bear_case="Recession risk",
            base_case="Sideways consolidation",
        )
        assert "Market rally continues" in result
        assert "Recession risk" in result
        assert "Sideways consolidation" in result

    def test_with_risk_factors(self) -> None:
        result = format_dd_report(
            symbol="XLE",
            recommendation="conditional",
            confidence=0.5,
            risk_factors=["Oil price volatility", "Geopolitical risk"],
        )
        assert "Oil price volatility" in result
        assert "Geopolitical risk" in result

    def test_minimal_report(self) -> None:
        result = format_dd_report(
            symbol="QQQ",
            recommendation="approve",
            confidence=0.6,
        )
        assert "QQQ" in result
        assert "APPROVE" in result


class TestFormatTradeExecuted:
    """Tests for format_trade_executed."""

    def test_buy_trade(self) -> None:
        result = format_trade_executed(
            action="buy",
            symbol="AAPL",
            quantity=Decimal("27"),
            price=Decimal("185.23"),
            total_cost=Decimal("5001.21"),
            stop_loss=Decimal("180.00"),
            target=Decimal("195.00"),
            order_id="abc123",
        )
        assert "BUY" in result
        assert "AAPL" in result
        assert "27" in result
        assert "$185.23" in result
        assert "$5,001.21" in result
        assert "abc123" in result
        assert "🟢" in result

    def test_sell_trade(self) -> None:
        result = format_trade_executed(
            action="sell",
            symbol="TSLA",
            quantity=Decimal("10"),
            price=Decimal("250.00"),
        )
        assert "SELL" in result
        assert "🔴" in result

    def test_with_thesis(self) -> None:
        result = format_trade_executed(
            action="buy",
            symbol="SPY",
            quantity=Decimal("5"),
            price=Decimal("450.00"),
            thesis_summary="Earnings momentum",
        )
        assert "Earnings momentum" in result


class TestFormatPositionClosed:
    """Tests for format_position_closed."""

    def test_target_hit(self) -> None:
        result = format_position_closed(
            symbol="AAPL",
            exit_reason="target_hit",
            entry_price=Decimal("185.00"),
            exit_price=Decimal("195.00"),
            quantity=Decimal("27"),
            pnl=Decimal("270.00"),
            pnl_pct=5.4,
        )
        assert "🎯" in result
        assert "AAPL" in result
        assert "Target Hit" in result
        assert "$270.00" in result
        assert "📈" in result

    def test_stop_hit(self) -> None:
        result = format_position_closed(
            symbol="TSLA",
            exit_reason="stop_hit",
            entry_price=Decimal("250.00"),
            exit_price=Decimal("240.00"),
            quantity=Decimal("10"),
            pnl=Decimal("-100.00"),
            pnl_pct=-4.0,
        )
        assert "⚠️" in result
        assert "📉" in result

    def test_time_exit(self) -> None:
        result = format_position_closed(
            symbol="XLE",
            exit_reason="time_exit",
            entry_price=Decimal("80.00"),
            exit_price=Decimal("82.00"),
            quantity=Decimal("50"),
            pnl=Decimal("100.00"),
            pnl_pct=2.5,
        )
        assert "⏰" in result


class TestFormatMarketEvent:
    """Tests for format_market_event."""

    def test_high_importance(self) -> None:
        result = format_market_event(
            headline="Fed raises rates 50bps",
            importance="high",
            source="Reuters",
        )
        assert "🔴" in result
        assert "Fed raises rates 50bps" in result
        assert "Reuters" in result

    def test_with_symbol(self) -> None:
        result = format_market_event(
            headline="Earnings beat",
            symbol="AAPL",
            importance="medium",
        )
        assert "AAPL" in result


class TestFormatSystemError:
    """Tests for format_system_error."""

    def test_with_component(self) -> None:
        result = format_system_error(
            error="Connection timeout",
            component="AlpacaBroker",
        )
        assert "🚨" in result
        assert "Connection timeout" in result
        assert "AlpacaBroker" in result

    def test_without_component(self) -> None:
        result = format_system_error(error="Unknown error")
        assert "Unknown error" in result


class TestFormatPortfolioStatus:
    """Tests for format_portfolio_status."""

    def test_with_positions(self) -> None:
        result = format_portfolio_status(
            cash=Decimal("10000.00"),
            equity=Decimal("50000.00"),
            positions=[
                {
                    "symbol": "AAPL",
                    "quantity": 27,
                    "unrealized_pnl": Decimal("150.00"),
                    "unrealized_pnl_pct": 3.0,
                },
                {
                    "symbol": "TSLA",
                    "quantity": 10,
                    "unrealized_pnl": Decimal("-50.00"),
                    "unrealized_pnl_pct": -2.0,
                },
            ],
            day_pnl=Decimal("100.00"),
        )
        assert "$10,000.00" in result
        assert "$50,000.00" in result
        assert "AAPL" in result
        assert "TSLA" in result
        assert "$100.00" in result

    def test_no_positions(self) -> None:
        result = format_portfolio_status(
            cash=Decimal("10000.00"),
            equity=Decimal("10000.00"),
            positions=[],
        )
        assert "No open positions" in result
