"""Tests for stock quality screening."""
from __future__ import annotations

import pytest

from beavr.core.screener import (
    MIN_RESEARCH_PRICE,
    QUALITY_UNIVERSE,
    passes_quality_gate,
)


class TestQualityGate:
    """Tests for passes_quality_gate function."""

    @pytest.mark.parametrize("symbol,price,expected", [
        ("AAPL", 190.0, True),    # In quality universe
        ("SPY", 560.0, True),     # ETF in universe
        ("DVLT", 0.72, False),    # Penny stock
        ("BMEA", 0.95, False),    # Sub-$1
        ("SNAP", 5.14, False),    # Below MIN_RESEARCH_PRICE ($15)
        ("AMZN", 200.0, True),    # Quality universe
        ("XYZ", 50.0, True),      # Unknown but valid price
        ("ABCDEF", 50.0, False),  # Symbol too long (>5 chars)
        ("BRK.B", 50.0, False),   # Has dot
        ("MSFT", 420.0, True),    # Quality universe, high price ok
        ("NVDA", 900.0, True),    # Quality universe bypasses max price
        ("RAND", 850.0, False),   # Not in universe, above max price ($800)
    ])
    def test_passes_quality_gate(self, symbol: str, price: float, expected: bool) -> None:
        """Test quality gate with various inputs."""
        assert passes_quality_gate(symbol, price=price) == expected

    def test_quality_universe_always_passes(self) -> None:
        """Stocks in QUALITY_UNIVERSE always pass regardless of price."""
        for symbol in list(QUALITY_UNIVERSE)[:5]:
            assert passes_quality_gate(symbol, price=1.0) is True
            assert passes_quality_gate(symbol, price=1000.0) is True

    def test_unknown_price_passes(self) -> None:
        """Unknown price (0) should not reject valid symbols."""
        assert passes_quality_gate("NEWCO", price=0.0) is True

    def test_rejects_low_volume_if_known(self) -> None:
        """Should reject stocks with known low volume."""
        assert passes_quality_gate("LVOL", price=50.0, avg_volume=100_000) is False
        assert passes_quality_gate("LVOL", price=50.0, avg_volume=600_000) is True

    def test_unknown_volume_passes(self) -> None:
        """Unknown volume (0) should not reject valid symbols."""
        assert passes_quality_gate("NEWCO", price=50.0, avg_volume=0) is True
