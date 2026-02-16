"""Tests for the portfolio wizard interactive and non-interactive flows.

Tests cover:
- _MODE_INFO / _AGG_INFO visual constants
- _create_from_flags validation
- _non_interactive resume/error paths
- _print_resume output
"""

from decimal import Decimal
from unittest.mock import MagicMock

import click.exceptions
import pytest

from beavr.cli.portfolio_wizard import (
    _AGG_INFO,
    _MODE_INFO,
    _create_from_flags,
    _non_interactive,
    _print_resume,
    select_or_create_portfolio,
)
from beavr.models.portfolio_record import (
    Aggressiveness,
    PortfolioRecord,
    PortfolioStatus,
    TradingMode,
)

# ===================================================================
# Visual constants
# ===================================================================


class TestVisualConstants:
    """Verify the mode and aggressiveness info dicts are well-formed."""

    def test_mode_info_has_paper_and_live(self) -> None:
        """Both paper and live modes should be defined."""
        modes = {v["mode"] for v in _MODE_INFO.values()}
        assert TradingMode.PAPER in modes
        assert TradingMode.LIVE in modes

    def test_mode_info_keys_are_1_and_2(self) -> None:
        """Selection keys should be '1' and '2'."""
        assert set(_MODE_INFO.keys()) == {"1", "2"}

    def test_mode_info_has_required_fields(self) -> None:
        """Each mode entry should have icon, label, desc, style."""
        for key, info in _MODE_INFO.items():
            assert "icon" in info, f"Mode {key} missing icon"
            assert "label" in info, f"Mode {key} missing label"
            assert "desc" in info, f"Mode {key} missing desc"
            assert "style" in info, f"Mode {key} missing style"

    def test_agg_info_has_all_levels(self) -> None:
        """All three aggressiveness levels should be defined."""
        aggs = {v["agg"] for v in _AGG_INFO.values()}
        assert Aggressiveness.CONSERVATIVE in aggs
        assert Aggressiveness.MODERATE in aggs
        assert Aggressiveness.AGGRESSIVE in aggs

    def test_agg_info_keys_are_1_2_3(self) -> None:
        """Selection keys should be '1', '2', '3'."""
        assert set(_AGG_INFO.keys()) == {"1", "2", "3"}

    def test_agg_info_has_required_fields(self) -> None:
        """Each aggressiveness entry should have icon, label, desc, style, bar."""
        for key, info in _AGG_INFO.items():
            assert "icon" in info, f"Agg {key} missing icon"
            assert "label" in info, f"Agg {key} missing label"
            assert "desc" in info, f"Agg {key} missing desc"
            assert "style" in info, f"Agg {key} missing style"
            assert "bar" in info, f"Agg {key} missing bar"


# ===================================================================
# Non-interactive flow
# ===================================================================


class TestNonInteractive:
    """Tests for _non_interactive portfolio resolution."""

    @pytest.fixture()
    def mock_store(self) -> MagicMock:
        """Create a mock PortfolioStore."""
        store = MagicMock()
        store.get_portfolio_by_name.return_value = None
        return store

    def test_resumes_existing_portfolio(self, mock_store: MagicMock) -> None:
        """Should return existing portfolio without creating."""
        existing = PortfolioRecord(
            id="abc",
            name="Test",
            mode=TradingMode.PAPER,
            initial_capital=Decimal("1000"),
            allocated_capital=Decimal("800"),
            current_cash=Decimal("800"),
            aggressiveness=Aggressiveness.MODERATE,
        )
        mock_store.get_portfolio_by_name.return_value = existing

        result = _non_interactive(
            mock_store, "Test", None, None, None, None, None,
        )
        assert result.name == "Test"
        mock_store.create_portfolio.assert_not_called()

    def test_missing_mode_exits(self, mock_store: MagicMock) -> None:
        """Should exit when name not found and --mode not provided."""
        with pytest.raises(click.exceptions.Exit):
            _non_interactive(
                mock_store, "NewPort", None, None, None, None, None,
            )


# ===================================================================
# Flag-based creation
# ===================================================================


class TestCreateFromFlags:
    """Tests for _create_from_flags validation."""

    @pytest.fixture()
    def mock_store(self) -> MagicMock:
        """Create a mock PortfolioStore that returns a record."""
        store = MagicMock()
        store.create_portfolio.return_value = "new-id"
        store.get_portfolio.return_value = PortfolioRecord(
            id="new-id",
            name="Test",
            mode=TradingMode.PAPER,
            initial_capital=Decimal("10000"),
            allocated_capital=Decimal("8000"),
            current_cash=Decimal("8000"),
            aggressiveness=Aggressiveness.MODERATE,
        )
        return store

    def test_valid_creation(self, mock_store: MagicMock) -> None:
        """Should create portfolio with valid flags."""
        result = _create_from_flags(
            mock_store, "Test", "paper", "moderate", ["trade fast"], Decimal("5000"), 90.0,
        )
        assert result.id == "new-id"
        mock_store.create_portfolio.assert_called_once()

    def test_invalid_mode_exits(self, mock_store: MagicMock) -> None:
        """Invalid mode should exit."""
        with pytest.raises(click.exceptions.Exit):
            _create_from_flags(
                mock_store, "Test", "yolo", None, None, None, None,
            )

    def test_invalid_aggressiveness_exits(self, mock_store: MagicMock) -> None:
        """Invalid aggressiveness should exit."""
        with pytest.raises(click.exceptions.Exit):
            _create_from_flags(
                mock_store, "Test", "paper", "insane", None, None, None,
            )

    def test_zero_capital_exits(self, mock_store: MagicMock) -> None:
        """Zero capital should exit."""
        with pytest.raises(click.exceptions.Exit):
            _create_from_flags(
                mock_store, "Test", "paper", None, None, Decimal("0"), None,
            )

    def test_negative_capital_exits(self, mock_store: MagicMock) -> None:
        """Negative capital should exit."""
        with pytest.raises(click.exceptions.Exit):
            _create_from_flags(
                mock_store, "Test", "paper", None, None, Decimal("-100"), None,
            )

    def test_capital_pct_over_100_exits(self, mock_store: MagicMock) -> None:
        """Capital percentage > 100 should exit."""
        with pytest.raises(click.exceptions.Exit):
            _create_from_flags(
                mock_store, "Test", "paper", None, None, None, 150.0,
            )

    def test_defaults_applied(self, mock_store: MagicMock) -> None:
        """Missing optional flags should use defaults."""
        _create_from_flags(
            mock_store, "Test", "paper", None, None, None, None,
        )
        call_kwargs = mock_store.create_portfolio.call_args
        assert call_kwargs.kwargs["initial_capital"] == Decimal("10000.00")
        assert call_kwargs.kwargs["aggressiveness"] == "moderate"


# ===================================================================
# Resume display
# ===================================================================


class TestPrintResume:
    """Tests for the resume panel output."""

    def test_resume_does_not_raise(self) -> None:
        """_print_resume should print without errors."""
        record = PortfolioRecord(
            id="xyz",
            name="MyPort",
            mode=TradingMode.PAPER,
            initial_capital=Decimal("10000"),
            allocated_capital=Decimal("8000"),
            current_cash=Decimal("8000"),
            aggressiveness=Aggressiveness.AGGRESSIVE,
            realized_pnl=Decimal("-50"),
            total_trades=3,
        )
        # Should not raise
        _print_resume(record)

    def test_resume_active_vs_paused(self) -> None:
        """Should handle both active and paused portfolios."""
        for status in [PortfolioStatus.ACTIVE, PortfolioStatus.PAUSED]:
            record = PortfolioRecord(
                id="xyz",
                name="Test",
                mode=TradingMode.LIVE,
                status=status,
                initial_capital=Decimal("5000"),
                allocated_capital=Decimal("4000"),
                current_cash=Decimal("4000"),
            )
            _print_resume(record)


# ===================================================================
# Public entry point routing
# ===================================================================


class TestSelectOrCreate:
    """Tests for the select_or_create_portfolio router."""

    def test_routes_to_non_interactive_when_name_given(self) -> None:
        """Should call _non_interactive when portfolio_name is not None."""
        store = MagicMock()
        existing = PortfolioRecord(
            id="abc",
            name="X",
            mode=TradingMode.PAPER,
            initial_capital=Decimal("1000"),
            allocated_capital=Decimal("800"),
            current_cash=Decimal("800"),
        )
        store.get_portfolio_by_name.return_value = existing

        result = select_or_create_portfolio(
            store, "X", None, None, None, None, None,
        )
        assert result.name == "X"
