"""Tests for SimulatedPortfolio."""

from datetime import datetime
from decimal import Decimal

import pytest

from beavr.backtest.portfolio import SimulatedPortfolio


class TestSimulatedPortfolio:
    """Tests for SimulatedPortfolio."""

    @pytest.fixture
    def portfolio(self) -> SimulatedPortfolio:
        """Create a portfolio with $10,000."""
        return SimulatedPortfolio(initial_cash=Decimal("10000"))

    def test_init(self, portfolio: SimulatedPortfolio) -> None:
        """Test portfolio initialization."""
        assert portfolio.cash == Decimal("10000")
        assert portfolio.initial_cash == Decimal("10000")
        assert portfolio.positions == {}
        assert portfolio.trades == []

    def test_buy_success(self, portfolio: SimulatedPortfolio) -> None:
        """Test successful buy order."""
        trade = portfolio.buy(
            symbol="SPY",
            amount=Decimal("1000"),
            price=Decimal("500"),
            timestamp=datetime(2024, 1, 1),
            reason="test",
        )

        assert trade is not None
        assert trade.symbol == "SPY"
        assert trade.side == "buy"
        assert trade.amount == Decimal("1000")
        assert trade.quantity == Decimal("2")  # $1000 / $500 = 2 shares
        assert trade.price == Decimal("500")
        assert trade.reason == "test"

        # Check portfolio state
        assert portfolio.cash == Decimal("9000")
        assert portfolio.get_position("SPY") == Decimal("2")
        assert portfolio.get_avg_cost("SPY") == Decimal("500")
        assert len(portfolio.trades) == 1

    def test_buy_insufficient_cash(self, portfolio: SimulatedPortfolio) -> None:
        """Test buy with insufficient cash returns None."""
        trade = portfolio.buy(
            symbol="SPY",
            amount=Decimal("20000"),  # More than we have
            price=Decimal("500"),
            timestamp=datetime(2024, 1, 1),
            reason="test",
        )

        assert trade is None
        assert portfolio.cash == Decimal("10000")
        assert len(portfolio.trades) == 0

    def test_buy_zero_amount(self, portfolio: SimulatedPortfolio) -> None:
        """Test buy with zero amount returns None."""
        trade = portfolio.buy(
            symbol="SPY",
            amount=Decimal("0"),
            price=Decimal("500"),
            timestamp=datetime(2024, 1, 1),
            reason="test",
        )

        assert trade is None

    def test_buy_zero_price(self, portfolio: SimulatedPortfolio) -> None:
        """Test buy with zero price returns None."""
        trade = portfolio.buy(
            symbol="SPY",
            amount=Decimal("1000"),
            price=Decimal("0"),
            timestamp=datetime(2024, 1, 1),
            reason="test",
        )

        assert trade is None

    def test_average_cost_single_buy(self, portfolio: SimulatedPortfolio) -> None:
        """Test average cost with single buy."""
        portfolio.buy(
            symbol="SPY",
            amount=Decimal("1000"),
            price=Decimal("100"),
            timestamp=datetime(2024, 1, 1),
            reason="test",
        )

        assert portfolio.get_avg_cost("SPY") == Decimal("100")

    def test_average_cost_multiple_buys(self, portfolio: SimulatedPortfolio) -> None:
        """Test average cost with multiple buys at different prices."""
        # Buy 10 shares at $100 = $1000
        portfolio.buy(
            symbol="SPY",
            amount=Decimal("1000"),
            price=Decimal("100"),
            timestamp=datetime(2024, 1, 1),
            reason="test",
        )
        # Buy 10 shares at $200 = $2000
        portfolio.buy(
            symbol="SPY",
            amount=Decimal("2000"),
            price=Decimal("200"),
            timestamp=datetime(2024, 1, 2),
            reason="test",
        )

        # 20 shares total, $3000 invested = $150 avg
        assert portfolio.get_position("SPY") == Decimal("20")
        assert portfolio.get_avg_cost("SPY") == Decimal("150")

    def test_sell_success(self, portfolio: SimulatedPortfolio) -> None:
        """Test successful sell order."""
        # First buy some shares
        portfolio.buy(
            symbol="SPY",
            amount=Decimal("1000"),
            price=Decimal("100"),
            timestamp=datetime(2024, 1, 1),
            reason="test",
        )

        # Sell half
        trade = portfolio.sell(
            symbol="SPY",
            quantity=Decimal("5"),  # Sell 5 of 10 shares
            price=Decimal("120"),  # At higher price
            timestamp=datetime(2024, 1, 2),
            reason="take_profit",
        )

        assert trade is not None
        assert trade.symbol == "SPY"
        assert trade.side == "sell"
        assert trade.quantity == Decimal("5")
        assert trade.price == Decimal("120")
        assert trade.amount == Decimal("600")

        # Check portfolio state
        assert portfolio.cash == Decimal("9600")  # 9000 + 600
        assert portfolio.get_position("SPY") == Decimal("5")
        assert portfolio.get_avg_cost("SPY") == Decimal("100")  # Unchanged
        assert len(portfolio.trades) == 2

    def test_sell_insufficient_shares(self, portfolio: SimulatedPortfolio) -> None:
        """Test sell with insufficient shares returns None."""
        portfolio.buy(
            symbol="SPY",
            amount=Decimal("1000"),
            price=Decimal("100"),
            timestamp=datetime(2024, 1, 1),
            reason="test",
        )

        trade = portfolio.sell(
            symbol="SPY",
            quantity=Decimal("20"),  # More than we have
            price=Decimal("120"),
            timestamp=datetime(2024, 1, 2),
            reason="test",
        )

        assert trade is None
        assert portfolio.get_position("SPY") == Decimal("10")

    def test_sell_closes_position(self, portfolio: SimulatedPortfolio) -> None:
        """Test selling all shares closes position."""
        portfolio.buy(
            symbol="SPY",
            amount=Decimal("1000"),
            price=Decimal("100"),
            timestamp=datetime(2024, 1, 1),
            reason="test",
        )

        portfolio.sell(
            symbol="SPY",
            quantity=Decimal("10"),  # Sell all
            price=Decimal("120"),
            timestamp=datetime(2024, 1, 2),
            reason="close",
        )

        assert portfolio.get_position("SPY") == Decimal("0")
        assert "SPY" not in portfolio.positions

    def test_get_value(self, portfolio: SimulatedPortfolio) -> None:
        """Test portfolio value calculation."""
        portfolio.buy(
            symbol="SPY",
            amount=Decimal("1000"),
            price=Decimal("100"),
            timestamp=datetime(2024, 1, 1),
            reason="test",
        )
        portfolio.buy(
            symbol="QQQ",
            amount=Decimal("2000"),
            price=Decimal("200"),
            timestamp=datetime(2024, 1, 1),
            reason="test",
        )

        # Cash: $7000
        # SPY: 10 shares at current $110 = $1100
        # QQQ: 10 shares at current $210 = $2100
        # Total: $10200
        prices = {"SPY": Decimal("110"), "QQQ": Decimal("210")}
        assert portfolio.get_value(prices) == Decimal("10200")

    def test_get_position_value(self, portfolio: SimulatedPortfolio) -> None:
        """Test position value calculation."""
        portfolio.buy(
            symbol="SPY",
            amount=Decimal("1000"),
            price=Decimal("100"),
            timestamp=datetime(2024, 1, 1),
            reason="test",
        )

        # 10 shares at $120 = $1200
        assert portfolio.get_position_value("SPY", Decimal("120")) == Decimal("1200")

    def test_get_cost_basis(self, portfolio: SimulatedPortfolio) -> None:
        """Test cost basis calculation."""
        portfolio.buy(
            symbol="SPY",
            amount=Decimal("1000"),
            price=Decimal("100"),
            timestamp=datetime(2024, 1, 1),
            reason="test",
        )

        # 10 shares at $100 avg = $1000 cost basis
        assert portfolio.get_cost_basis("SPY") == Decimal("1000")

    def test_get_total_cost_basis(self, portfolio: SimulatedPortfolio) -> None:
        """Test total cost basis calculation."""
        portfolio.buy(
            symbol="SPY",
            amount=Decimal("1000"),
            price=Decimal("100"),
            timestamp=datetime(2024, 1, 1),
            reason="test",
        )
        portfolio.buy(
            symbol="QQQ",
            amount=Decimal("2000"),
            price=Decimal("200"),
            timestamp=datetime(2024, 1, 1),
            reason="test",
        )

        assert portfolio.get_total_cost_basis() == Decimal("3000")

    def test_get_unrealized_pnl_profit(self, portfolio: SimulatedPortfolio) -> None:
        """Test unrealized P&L with profit."""
        portfolio.buy(
            symbol="SPY",
            amount=Decimal("1000"),
            price=Decimal("100"),
            timestamp=datetime(2024, 1, 1),
            reason="test",
        )

        # Cost basis: $1000, current value: $1200, P&L: +$200
        prices = {"SPY": Decimal("120")}
        assert portfolio.get_unrealized_pnl(prices) == Decimal("200")

    def test_get_unrealized_pnl_loss(self, portfolio: SimulatedPortfolio) -> None:
        """Test unrealized P&L with loss."""
        portfolio.buy(
            symbol="SPY",
            amount=Decimal("1000"),
            price=Decimal("100"),
            timestamp=datetime(2024, 1, 1),
            reason="test",
        )

        # Cost basis: $1000, current value: $800, P&L: -$200
        prices = {"SPY": Decimal("80")}
        assert portfolio.get_unrealized_pnl(prices) == Decimal("-200")

    def test_get_state(self, portfolio: SimulatedPortfolio) -> None:
        """Test getting portfolio state."""
        portfolio.buy(
            symbol="SPY",
            amount=Decimal("1000"),
            price=Decimal("100"),
            timestamp=datetime(2024, 1, 1),
            reason="test",
        )

        prices = {"SPY": Decimal("110")}
        state = portfolio.get_state(datetime(2024, 1, 2), prices)

        assert state.cash == Decimal("9000")
        assert len(state.positions) == 1
        assert state.positions["SPY"].quantity == Decimal("10")
        assert state.positions["SPY"].avg_cost == Decimal("100")

    def test_get_total_invested(self, portfolio: SimulatedPortfolio) -> None:
        """Test total invested calculation."""
        portfolio.buy(
            symbol="SPY",
            amount=Decimal("1000"),
            price=Decimal("100"),
            timestamp=datetime(2024, 1, 1),
            reason="test",
        )
        portfolio.buy(
            symbol="SPY",
            amount=Decimal("500"),
            price=Decimal("110"),
            timestamp=datetime(2024, 1, 2),
            reason="test",
        )

        assert portfolio.get_total_invested() == Decimal("1500")

    def test_get_total_withdrawn(self, portfolio: SimulatedPortfolio) -> None:
        """Test total withdrawn calculation."""
        portfolio.buy(
            symbol="SPY",
            amount=Decimal("1000"),
            price=Decimal("100"),
            timestamp=datetime(2024, 1, 1),
            reason="test",
        )
        portfolio.sell(
            symbol="SPY",
            quantity=Decimal("5"),
            price=Decimal("120"),
            timestamp=datetime(2024, 1, 2),
            reason="test",
        )

        assert portfolio.get_total_withdrawn() == Decimal("600")

    def test_repr(self, portfolio: SimulatedPortfolio) -> None:
        """Test portfolio repr."""
        repr_str = repr(portfolio)
        assert "SimulatedPortfolio" in repr_str
        assert "10000" in repr_str

    def test_multiple_symbols(self, portfolio: SimulatedPortfolio) -> None:
        """Test portfolio with multiple symbols."""
        portfolio.buy(
            symbol="SPY",
            amount=Decimal("2000"),
            price=Decimal("400"),
            timestamp=datetime(2024, 1, 1),
            reason="test",
        )
        portfolio.buy(
            symbol="QQQ",
            amount=Decimal("3000"),
            price=Decimal("300"),
            timestamp=datetime(2024, 1, 1),
            reason="test",
        )
        portfolio.buy(
            symbol="VOO",
            amount=Decimal("2500"),
            price=Decimal("500"),
            timestamp=datetime(2024, 1, 1),
            reason="test",
        )

        assert len(portfolio.positions) == 3
        assert portfolio.get_position("SPY") == Decimal("5")
        assert portfolio.get_position("QQQ") == Decimal("10")
        assert portfolio.get_position("VOO") == Decimal("5")
        assert portfolio.cash == Decimal("2500")

    def test_strategy_id_tracked(self, portfolio: SimulatedPortfolio) -> None:
        """Test that strategy_id is tracked on trades."""
        trade = portfolio.buy(
            symbol="SPY",
            amount=Decimal("1000"),
            price=Decimal("100"),
            timestamp=datetime(2024, 1, 1),
            reason="test",
            strategy_id="simple_dca_001",
        )

        assert trade is not None
        assert trade.strategy_id == "simple_dca_001"
