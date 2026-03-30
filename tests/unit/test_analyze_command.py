"""Tests for analyze_opportunities return type."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest


class TestAnalyzeOpportunities:
    """Tests for AIInvestor.analyze_opportunities method."""

    def test_returns_tuple_on_empty_opportunities(self):
        """analyze_opportunities returns 3-tuple even when no opportunities."""
        from beavr.cli.ai import AIInvestor
        
        with patch.object(AIInvestor, '__init__', lambda x: None):
            investor = AIInvestor()
            investor._llm = MagicMock()
            investor._broker = MagicMock()
            investor._data_provider = MagicMock()
            investor.get_quality_opportunities = MagicMock(return_value=[])
            
            result = investor.analyze_opportunities(Decimal("1000"))
            
            assert isinstance(result, tuple)
            assert len(result) == 3
            picks, view, risk = result
            assert picks == []
            assert isinstance(view, str)
            assert isinstance(risk, str)

    def test_returns_tuple_on_no_technicals(self):
        """analyze_opportunities returns 3-tuple when technicals unavailable."""
        from beavr.cli.ai import AIInvestor
        
        with patch.object(AIInvestor, '__init__', lambda x: None):
            investor = AIInvestor()
            investor._llm = MagicMock()
            investor._broker = MagicMock()
            investor._data_provider = MagicMock()
            investor.get_quality_opportunities = MagicMock(return_value=[
                {"symbol": "XYZ", "price": 50.0, "change_pct": 5.0, "type": "gainer", "in_universe": False}
            ])
            investor.get_technical_indicators = MagicMock(return_value=None)
            
            result = investor.analyze_opportunities(Decimal("1000"))
            
            assert isinstance(result, tuple)
            assert len(result) == 3
            picks, view, risk = result
            assert picks == []

    def test_returns_tuple_on_llm_failure(self):
        """analyze_opportunities returns 3-tuple when LLM call fails."""
        from beavr.cli.ai import AIInvestor
        
        with patch.object(AIInvestor, '__init__', lambda x: None):
            investor = AIInvestor()
            mock_llm = MagicMock()
            mock_llm.reason = MagicMock(side_effect=Exception("LLM error"))
            investor._llm = mock_llm
            investor._broker = MagicMock()
            investor._data_provider = MagicMock()
            investor.get_quality_opportunities = MagicMock(return_value=[
                {"symbol": "AAPL", "price": 190.0, "change_pct": 2.0, "type": "gainer", "in_universe": True}
            ])
            investor.get_technical_indicators = MagicMock(return_value={
                "price": 190.0, "rsi": 45.0, "sma_20": 185.0,
                "bb_upper": 195.0, "bb_lower": 175.0,
                "above_sma_20": True, "oversold": False, "overbought": False,
            })
            
            result = investor.analyze_opportunities(Decimal("1000"))
            
            assert isinstance(result, tuple)
            assert len(result) == 3
            picks, view, risk = result
            assert picks == []
            assert "failed" in view.lower() or "error" in view.lower()
            assert risk == "high"
