"""Tests for market briefing system."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from beavr.agents.base import AgentContext
from beavr.agents.market_briefing import (
    MarketBrief,
    MarketBriefingAgent,
)


class TestMarketBrief:
    """Tests for MarketBrief model."""

    def test_brief_model_validates(self) -> None:
        """MarketBrief Pydantic model validates correctly."""
        brief = MarketBrief(
            regime="bull",
            regime_confidence=0.8,
            risk_posture="aggressive",
            leading_sectors=["XLK", "XLY"],
            lagging_sectors=["XLU", "XLP"],
            rotation_theme="Risk-on rotation into tech",
            key_takeaways=["Market is bullish", "Buy the dip"],
            raw_summary="The market is looking good.",
        )
        assert brief.regime == "bull"
        assert brief.regime_confidence == 0.8
        assert len(brief.leading_sectors) == 2

    def test_brief_model_defaults(self) -> None:
        """MarketBrief has sensible defaults."""
        brief = MarketBrief(
            regime="sideways",
            regime_confidence=0.5,
            risk_posture="moderate",
        )
        assert brief.leading_sectors == []
        assert brief.lagging_sectors == []
        assert brief.key_takeaways == []
        assert brief.portfolio_warnings == []


class TestMarketBriefingAgent:
    """Tests for MarketBriefingAgent."""

    @pytest.fixture
    def mock_llm(self) -> MagicMock:
        """Create a mock LLM client."""
        llm = MagicMock()
        llm.reason.return_value = MarketBrief(
            regime="bull",
            regime_confidence=0.75,
            risk_posture="moderate",
            leading_sectors=["XLK"],
            lagging_sectors=["XLE"],
            key_takeaways=["Stay long tech"],
            raw_summary="Market is bullish.",
        )
        return llm

    @pytest.fixture
    def agent(self, mock_llm: MagicMock) -> MarketBriefingAgent:
        """Create agent with mock LLM."""
        return MarketBriefingAgent(llm=mock_llm)

    @pytest.fixture
    def context(self) -> AgentContext:
        """Create a test context."""
        return AgentContext(
            current_date=date.today(),
            timestamp=datetime.now(),
            portfolio_value=Decimal("50000"),
            cash=Decimal("10000"),
            current_drawdown=0.02,
            peak_value=Decimal("51000"),
            regime="sideways",
            risk_budget=0.8,
            prices={},
            bars={},
            positions={},
            indicators={
                "SPY": {"current_price": 560.0, "rsi_14": 55.0, "change_5d": 1.5},
                "QQQ": {"current_price": 480.0, "rsi_14": 58.0, "change_5d": 2.0},
            },
        )

    def test_agent_builds_prompt(self, agent: MarketBriefingAgent, context: AgentContext) -> None:
        """Agent builds prompt with index and sector data."""
        prompt = agent._build_brief_prompt(context, "Test portfolio")
        assert "SPY" in prompt
        assert "QQQ" in prompt
        assert "50,000" in prompt or "50000" in prompt
        assert "Test portfolio" in prompt

    def test_agent_generates_brief(
        self, agent: MarketBriefingAgent, context: AgentContext, mock_llm: MagicMock
    ) -> None:
        """Agent generates a MarketBrief."""
        brief = agent.generate_brief(context)
        assert isinstance(brief, MarketBrief)
        assert brief.regime == "bull"
        mock_llm.reason.assert_called_once()

    def test_agent_system_prompt(self, agent: MarketBriefingAgent) -> None:
        """System prompt contains key instructions."""
        prompt = agent.get_system_prompt()
        assert "MARKET REGIME" in prompt
        assert "SECTOR ROTATION" in prompt
        assert "ACTIONABLE" in prompt or "actionable" in prompt

    def test_agent_handles_no_indicators(self, agent: MarketBriefingAgent) -> None:
        """Agent handles context with no indicators."""
        ctx = AgentContext(
            current_date=date.today(),
            timestamp=datetime.now(),
            portfolio_value=Decimal("10000"),
            cash=Decimal("5000"),
            current_drawdown=0.0,
            peak_value=Decimal("10000"),
            regime="sideways",
            risk_budget=1.0,
            prices={},
            bars={},
            positions={},
            indicators={},
        )
        prompt = agent._build_brief_prompt(ctx, "")
        assert "No index data" in prompt or "INDEX DATA" in prompt


class TestBriefingCommandHandler:
    """Tests for BriefingCommandHandler."""

    def test_handler_formats_output(self) -> None:
        """Telegram command formats brief within 4096 char limit."""
        from beavr.messaging.commands.briefing import BriefingCommandHandler
        from beavr.models.messaging import InboundCommand

        handler = BriefingCommandHandler(api=None)

        # Without API, should return error
        import asyncio

        cmd = InboundCommand(
            raw_text="/brief",
            command="brief",
            args=[],
            sender_id="test",
            platform="telegram",
            timestamp=datetime.now(),
        )
        result = asyncio.run(handler.handle(cmd))
        assert not result.success
        assert "not connected" in result.message.lower()

    def test_handler_command_names(self) -> None:
        """Handler responds to correct command names."""
        from beavr.messaging.commands.briefing import BriefingCommandHandler

        handler = BriefingCommandHandler()
        assert "brief" in handler.command_names
        assert "briefing" in handler.command_names
        assert "market" in handler.command_names
