"""Unit tests for core Pydantic models."""

from datetime import datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from beavr.models import Bar, PortfolioState, Position, Signal, Trade


class TestBar:
    """Tests for the Bar model."""

    def test_bar_creation(self) -> None:
        """Test creating a valid bar."""
        bar = Bar(
            symbol="SPY",
            timestamp=datetime(2024, 1, 15, 9, 30),
            open=Decimal("450.00"),
            high=Decimal("455.00"),
            low=Decimal("448.00"),
            close=Decimal("453.50"),
            volume=1000000,
        )
        assert bar.symbol == "SPY"
        assert bar.close == Decimal("453.50")
        assert bar.timeframe == "1Day"  # default

    def test_bar_is_frozen(self) -> None:
        """Test that Bar is immutable."""
        bar = Bar(
            symbol="SPY",
            timestamp=datetime(2024, 1, 15),
            open=Decimal("450.00"),
            high=Decimal("455.00"),
            low=Decimal("448.00"),
            close=Decimal("453.50"),
            volume=1000000,
        )
        with pytest.raises(ValidationError):
            bar.close = Decimal("460.00")  # type: ignore

    def test_bar_with_timeframe(self) -> None:
        """Test bar with custom timeframe."""
        bar = Bar(
            symbol="AAPL",
            timestamp=datetime(2024, 1, 15, 10, 0),
            open=Decimal("185.00"),
            high=Decimal("186.00"),
            low=Decimal("184.50"),
            close=Decimal("185.75"),
            volume=50000,
            timeframe="1Hour",
        )
        assert bar.timeframe == "1Hour"

    def test_bar_str(self) -> None:
        """Test bar string representation."""
        bar = Bar(
            symbol="SPY",
            timestamp=datetime(2024, 1, 15),
            open=Decimal("450.00"),
            high=Decimal("455.00"),
            low=Decimal("448.00"),
            close=Decimal("453.50"),
            volume=1000000,
        )
        assert "SPY" in str(bar)
        assert "453.50" in str(bar)


class TestSignal:
    """Tests for the Signal model."""

    def test_buy_signal(self) -> None:
        """Test creating a buy signal."""
        signal = Signal(
            symbol="SPY",
            action="buy",
            amount=Decimal("500.00"),
            reason="Monthly DCA",
            timestamp=datetime(2024, 1, 15),
        )
        assert signal.action == "buy"
        assert signal.amount == Decimal("500.00")
        assert signal.quantity is None

    def test_sell_signal(self) -> None:
        """Test creating a sell signal."""
        signal = Signal(
            symbol="TSLA",
            action="sell",
            quantity=Decimal("10"),
            reason="Take profit",
            timestamp=datetime(2024, 1, 15),
        )
        assert signal.action == "sell"
        assert signal.quantity == Decimal("10")
        assert signal.amount is None

    def test_hold_signal(self) -> None:
        """Test creating a hold signal."""
        signal = Signal(
            symbol="SPY",
            action="hold",
            reason="No action needed",
            timestamp=datetime(2024, 1, 15),
        )
        assert signal.action == "hold"

    def test_signal_with_confidence(self) -> None:
        """Test signal with confidence score."""
        signal = Signal(
            symbol="SPY",
            action="buy",
            amount=Decimal("500.00"),
            reason="Strong dip signal",
            timestamp=datetime(2024, 1, 15),
            confidence=0.85,
        )
        assert signal.confidence == 0.85

    def test_signal_str_buy(self) -> None:
        """Test signal string representation for buy."""
        signal = Signal(
            symbol="SPY",
            action="buy",
            amount=Decimal("500.00"),
            reason="Monthly DCA",
            timestamp=datetime(2024, 1, 15),
        )
        assert "BUY" in str(signal)
        assert "500" in str(signal)


class TestTrade:
    """Tests for the Trade model."""

    def test_trade_creation(self) -> None:
        """Test creating a trade."""
        trade = Trade(
            symbol="SPY",
            side="buy",
            quantity=Decimal("10.5"),
            price=Decimal("450.00"),
            amount=Decimal("4725.00"),
            timestamp=datetime(2024, 1, 15),
            reason="scheduled",
        )
        assert trade.symbol == "SPY"
        assert trade.side == "buy"
        assert trade.id is not None  # UUID auto-generated

    def test_trade_create_buy_factory(self) -> None:
        """Test the create_buy factory method."""
        trade = Trade.create_buy(
            symbol="SPY",
            amount=Decimal("500.00"),
            price=Decimal("450.00"),
            timestamp=datetime(2024, 1, 15),
            reason="dip_buy",
        )
        assert trade.side == "buy"
        assert trade.amount == Decimal("500.00")
        # 500 / 450 = 1.111...
        assert abs(trade.quantity - Decimal("1.1111111111111111111111111111")) < Decimal("0.001")

    def test_trade_create_sell_factory(self) -> None:
        """Test the create_sell factory method."""
        trade = Trade.create_sell(
            symbol="TSLA",
            quantity=Decimal("10"),
            price=Decimal("250.00"),
            timestamp=datetime(2024, 1, 15),
            reason="take_profit",
        )
        assert trade.side == "sell"
        assert trade.quantity == Decimal("10")
        assert trade.amount == Decimal("2500.00")

    def test_trade_with_strategy_id(self) -> None:
        """Test trade with strategy identifier."""
        trade = Trade(
            symbol="SPY",
            side="buy",
            quantity=Decimal("10"),
            price=Decimal("450.00"),
            amount=Decimal("4500.00"),
            timestamp=datetime(2024, 1, 15),
            reason="scheduled",
            strategy_id="my_dca_strategy",
        )
        assert trade.strategy_id == "my_dca_strategy"


class TestPosition:
    """Tests for the Position model."""

    def test_position_creation(self) -> None:
        """Test creating a position."""
        position = Position(
            symbol="SPY",
            quantity=Decimal("100"),
            avg_cost=Decimal("420.00"),
        )
        assert position.symbol == "SPY"
        assert position.quantity == Decimal("100")
        assert position.avg_cost == Decimal("420.00")

    def test_cost_basis(self) -> None:
        """Test cost basis calculation."""
        position = Position(
            symbol="SPY",
            quantity=Decimal("100"),
            avg_cost=Decimal("420.00"),
        )
        assert position.cost_basis == Decimal("42000.00")

    def test_market_value(self) -> None:
        """Test market value calculation."""
        position = Position(
            symbol="SPY",
            quantity=Decimal("100"),
            avg_cost=Decimal("420.00"),
        )
        market_value = position.market_value(Decimal("450.00"))
        assert market_value == Decimal("45000.00")

    def test_unrealized_pnl(self) -> None:
        """Test unrealized P&L calculation."""
        position = Position(
            symbol="SPY",
            quantity=Decimal("100"),
            avg_cost=Decimal("420.00"),
        )
        pnl = position.unrealized_pnl(Decimal("450.00"))
        assert pnl == Decimal("3000.00")

    def test_unrealized_pnl_pct(self) -> None:
        """Test unrealized P&L percentage calculation."""
        position = Position(
            symbol="SPY",
            quantity=Decimal("100"),
            avg_cost=Decimal("420.00"),
        )
        pnl_pct = position.unrealized_pnl_pct(Decimal("450.00"))
        # (45000 - 42000) / 42000 = 0.0714...
        assert abs(pnl_pct - 0.0714) < 0.001


class TestPortfolioState:
    """Tests for the PortfolioState model."""

    def test_empty_portfolio(self) -> None:
        """Test creating an empty portfolio."""
        portfolio = PortfolioState(
            timestamp=datetime(2024, 1, 15),
            cash=Decimal("10000.00"),
        )
        assert portfolio.cash == Decimal("10000.00")
        assert len(portfolio.positions) == 0

    def test_portfolio_with_positions(self) -> None:
        """Test portfolio with positions."""
        spy_position = Position(
            symbol="SPY",
            quantity=Decimal("50"),
            avg_cost=Decimal("420.00"),
        )
        portfolio = PortfolioState(
            timestamp=datetime(2024, 1, 15),
            cash=Decimal("5000.00"),
            positions={"SPY": spy_position},
        )
        assert len(portfolio.positions) == 1
        assert portfolio.get_position("SPY") == spy_position
        assert portfolio.get_position("AAPL") is None

    def test_total_value(self) -> None:
        """Test total portfolio value calculation."""
        spy_position = Position(
            symbol="SPY",
            quantity=Decimal("50"),
            avg_cost=Decimal("420.00"),
        )
        portfolio = PortfolioState(
            timestamp=datetime(2024, 1, 15),
            cash=Decimal("5000.00"),
            positions={"SPY": spy_position},
        )
        prices = {"SPY": Decimal("450.00")}
        total = portfolio.total_value(prices)
        # 5000 + (50 * 450) = 5000 + 22500 = 27500
        assert total == Decimal("27500.00")

    def test_total_cost_basis(self) -> None:
        """Test total cost basis calculation."""
        spy_position = Position(
            symbol="SPY",
            quantity=Decimal("50"),
            avg_cost=Decimal("420.00"),
        )
        qqq_position = Position(
            symbol="QQQ",
            quantity=Decimal("20"),
            avg_cost=Decimal("350.00"),
        )
        portfolio = PortfolioState(
            timestamp=datetime(2024, 1, 15),
            cash=Decimal("5000.00"),
            positions={"SPY": spy_position, "QQQ": qqq_position},
        )
        # (50 * 420) + (20 * 350) = 21000 + 7000 = 28000
        assert portfolio.total_cost_basis() == Decimal("28000.00")

    def test_total_unrealized_pnl(self) -> None:
        """Test total unrealized P&L calculation."""
        spy_position = Position(
            symbol="SPY",
            quantity=Decimal("50"),
            avg_cost=Decimal("420.00"),
        )
        portfolio = PortfolioState(
            timestamp=datetime(2024, 1, 15),
            cash=Decimal("5000.00"),
            positions={"SPY": spy_position},
        )
        prices = {"SPY": Decimal("450.00")}
        pnl = portfolio.total_unrealized_pnl(prices)
        # (50 * 450) - (50 * 420) = 22500 - 21000 = 1500
        assert pnl == Decimal("1500.00")
