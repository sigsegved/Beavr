"""Tests for SwingTraderAgent system prompt."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from beavr.agents.swing_trader import SwingTraderAgent


class TestSwingTraderPrompt:
    """Tests for swing trader system prompt content."""

    @pytest.fixture
    def agent(self) -> SwingTraderAgent:
        """Create a SwingTraderAgent with mock LLM."""
        mock_llm = MagicMock()
        return SwingTraderAgent(llm=mock_llm)

    def test_prompt_contains_trend_filter(self, agent: SwingTraderAgent) -> None:
        """System prompt should include trend filter rules."""
        prompt = agent.get_system_prompt()
        # Should mention SMA50 as trend indicator
        assert "SMA50" in prompt or "50-day SMA" in prompt

    def test_prompt_contains_falling_knife_filter(self, agent: SwingTraderAgent) -> None:
        """System prompt should include falling knife protection."""
        prompt = agent.get_system_prompt()
        assert "FALLING KNIFE" in prompt or "falling knife" in prompt

    def test_prompt_warns_against_oversold_in_downtrend(self, agent: SwingTraderAgent) -> None:
        """Prompt should warn against buying RSI < 40 below SMA50."""
        prompt = agent.get_system_prompt()
        # Should mention not buying when RSI low AND below moving average
        assert "RSI" in prompt
        assert "below" in prompt.lower()
        # Check for the specific rule about RSI < 40 and below SMA50
        assert "downtrend" in prompt.lower() or "below 50-day SMA" in prompt or "below SMA50" in prompt

    def test_prompt_requires_trend_for_oversold_bounce(self, agent: SwingTraderAgent) -> None:
        """Oversold bounce should only be valid if trend is intact."""
        prompt = agent.get_system_prompt()
        # Should mention that oversold needs trend confirmation
        lower_prompt = prompt.lower()
        assert "oversold" in lower_prompt
        assert "trend" in lower_prompt or "sma50" in lower_prompt.replace(" ", "")

    def test_prompt_has_do_not_buy_section(self, agent: SwingTraderAgent) -> None:
        """Prompt should have explicit DO NOT BUY section."""
        prompt = agent.get_system_prompt()
        assert "DO NOT BUY" in prompt or "NEVER" in prompt

    def test_prompt_mentions_momentum_strategy(self, agent: SwingTraderAgent) -> None:
        """Prompt should include momentum trading strategy."""
        prompt = agent.get_system_prompt()
        assert "MOMENTUM" in prompt or "momentum" in prompt

    def test_prompt_mentions_pullback_strategy(self, agent: SwingTraderAgent) -> None:
        """Prompt should include pullback in uptrend strategy."""
        prompt = agent.get_system_prompt()
        assert "PULLBACK" in prompt or "pullback" in prompt

    def test_prompt_has_position_sizing_guidance(self, agent: SwingTraderAgent) -> None:
        """Prompt should include position sizing guidelines."""
        prompt = agent.get_system_prompt()
        assert "POSITION SIZING" in prompt or "position size" in prompt.lower()

    def test_prompt_has_risk_management(self, agent: SwingTraderAgent) -> None:
        """Prompt should include risk management rules."""
        prompt = agent.get_system_prompt()
        assert "RISK MANAGEMENT" in prompt or "stop loss" in prompt.lower()
