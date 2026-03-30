"""Tests for volatility-adjusted position sizing."""
from __future__ import annotations

from decimal import Decimal

import pytest

from beavr.core.sizing import calculate_position_size


class TestPositionSizing:
    """Tests for calculate_position_size function."""

    def test_wider_stop_gets_smaller_position(self) -> None:
        """Wider stop distance should result in smaller position."""
        pv = Decimal("10000")
        wide = calculate_position_size(pv, stop_distance_pct=12.0)
        narrow = calculate_position_size(pv, stop_distance_pct=4.0)
        assert wide < narrow

    def test_respects_max_position(self) -> None:
        """Position should not exceed max_position_pct."""
        result = calculate_position_size(
            Decimal("10000"),
            stop_distance_pct=1.0,  # Very tight stop would want huge position
            max_position_pct=0.20,
        )
        assert result <= Decimal("2000")  # 20% of 10K

    def test_respects_min_position(self) -> None:
        """Position should not go below min_position_pct."""
        result = calculate_position_size(
            Decimal("10000"),
            stop_distance_pct=50.0,  # Very wide stop
            min_position_pct=0.05,
        )
        assert result >= Decimal("500")  # 5% of 10K

    def test_handles_zero_stop(self) -> None:
        """Zero stop distance should use default (5%)."""
        result = calculate_position_size(Decimal("10000"), stop_distance_pct=0)
        assert result > 0
        # With default 5% stop and 2% risk: 2% / 5% = 40% raw, capped at 20%
        assert result == Decimal("2000")

    def test_handles_negative_stop(self) -> None:
        """Negative stop distance should use default."""
        result = calculate_position_size(Decimal("10000"), stop_distance_pct=-5.0)
        assert result > 0

    def test_standard_5pct_stop(self) -> None:
        """Standard 5% stop with 2% risk should give 40% raw, capped at 20%."""
        result = calculate_position_size(
            Decimal("10000"),
            stop_distance_pct=5.0,
            max_risk_per_trade=0.02,
            max_position_pct=0.20,
        )
        # 2% risk / 5% stop = 40% raw position, capped at 20% = $2000
        assert result == Decimal("2000")

    def test_10pct_stop_gives_20pct_position(self) -> None:
        """10% stop with 2% risk should give 20% position."""
        result = calculate_position_size(
            Decimal("10000"),
            stop_distance_pct=10.0,
            max_risk_per_trade=0.02,
            min_position_pct=0.05,
            max_position_pct=0.30,  # Raise cap to test raw calculation
        )
        # 2% risk / 10% stop = 20% position = $2000
        assert result == Decimal("2000")

    def test_20pct_stop_gives_10pct_position(self) -> None:
        """20% stop with 2% risk should give 10% position."""
        result = calculate_position_size(
            Decimal("10000"),
            stop_distance_pct=20.0,
            max_risk_per_trade=0.02,
            min_position_pct=0.05,
            max_position_pct=0.30,
        )
        # 2% risk / 20% stop = 10% position = $1000
        assert result == Decimal("1000")

    def test_custom_risk_per_trade(self) -> None:
        """Custom risk per trade should be respected."""
        result = calculate_position_size(
            Decimal("10000"),
            stop_distance_pct=5.0,
            max_risk_per_trade=0.01,  # 1% risk instead of 2%
            max_position_pct=0.30,
        )
        # 1% risk / 5% stop = 20% position = $2000
        assert result == Decimal("2000")

    def test_large_portfolio(self) -> None:
        """Should scale correctly with large portfolio."""
        result = calculate_position_size(
            Decimal("1000000"),
            stop_distance_pct=5.0,
            max_risk_per_trade=0.02,
            max_position_pct=0.20,
        )
        # 20% of $1M = $200K
        assert result == Decimal("200000")

    def test_small_portfolio(self) -> None:
        """Should work with small portfolios."""
        result = calculate_position_size(
            Decimal("1000"),
            stop_distance_pct=5.0,
            max_risk_per_trade=0.02,
            min_position_pct=0.05,
            max_position_pct=0.20,
        )
        # 20% of $1000 = $200
        assert result == Decimal("200")
