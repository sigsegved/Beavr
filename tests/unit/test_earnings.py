"""Tests for earnings calendar fetcher and earnings play agent."""

from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from beavr.agents.earnings_agent import (
    EarningsAnalysisBatch,
    EarningsAnalysisOutput,
    EarningsPlayAgent,
    EarningsPlayType,
)
from beavr.data.earnings import EarningsCalendarFetcher
from beavr.models.market_event import EventImportance, EventType, MarketEvent

# ===================================================================
# EarningsCalendarFetcher
# ===================================================================


class TestEarningsCalendarFetcher:
    """Tests for the earnings data fetcher."""

    @pytest.fixture()
    def mock_store(self) -> MagicMock:
        """Create a mock events store."""
        store = MagicMock()
        store.get_upcoming_earnings.return_value = []
        store.save_event.return_value = "evt-123"
        return store

    def test_convert_to_events_basic(self, mock_store: MagicMock) -> None:
        """Should convert raw earnings data to MarketEvent."""
        fetcher = EarningsCalendarFetcher(events_store=mock_store)
        raw = [
            {
                "symbol": "AAPL",
                "name": "Apple Inc",
                "earnings_date": date.today() + timedelta(days=5),
                "estimate_eps": "2.36",
                "source": "alpha_vantage",
            }
        ]
        events = fetcher._convert_to_events(raw, cutoff=date.today() + timedelta(days=14))
        assert len(events) == 1
        assert events[0].symbol == "AAPL"
        assert events[0].event_type == EventType.EARNINGS_UPCOMING
        assert events[0].estimate_eps == Decimal("2.36")
        assert events[0].importance == EventImportance.HIGH

    def test_convert_filters_past_cutoff(self, mock_store: MagicMock) -> None:
        """Should exclude events past the cutoff date."""
        fetcher = EarningsCalendarFetcher(events_store=mock_store)
        raw = [
            {
                "symbol": "MSFT",
                "name": "Microsoft",
                "earnings_date": date.today() + timedelta(days=30),
                "source": "alpha_vantage",
            }
        ]
        events = fetcher._convert_to_events(raw, cutoff=date.today() + timedelta(days=7))
        assert len(events) == 0

    def test_convert_handles_missing_eps(self, mock_store: MagicMock) -> None:
        """Should handle missing EPS estimate gracefully."""
        fetcher = EarningsCalendarFetcher(events_store=mock_store)
        raw = [
            {
                "symbol": "TSLA",
                "name": "Tesla",
                "earnings_date": date.today() + timedelta(days=3),
                "estimate_eps": "",
                "source": "alpha_vantage",
            }
        ]
        events = fetcher._convert_to_events(raw, cutoff=date.today() + timedelta(days=14))
        assert len(events) == 1
        assert events[0].estimate_eps is None

    def test_convert_skips_no_symbol(self, mock_store: MagicMock) -> None:
        """Should skip entries without a symbol."""
        fetcher = EarningsCalendarFetcher(events_store=mock_store)
        raw = [{"symbol": "", "earnings_date": date.today()}]
        events = fetcher._convert_to_events(raw, cutoff=date.today() + timedelta(days=14))
        assert len(events) == 0

    def test_deduplicate_and_store_new(self, mock_store: MagicMock) -> None:
        """Should store new events and return them."""
        fetcher = EarningsCalendarFetcher(events_store=mock_store)
        events = [
            MarketEvent(
                event_type=EventType.EARNINGS_UPCOMING,
                symbol="AAPL",
                headline="Earnings",
                summary="Test",
                source="test",
                earnings_date=date.today() + timedelta(days=5),
            )
        ]
        result = fetcher._deduplicate_and_store(events)
        assert len(result) == 1
        mock_store.save_event.assert_called_once()

    def test_deduplicate_skips_existing(self, mock_store: MagicMock) -> None:
        """Should skip events already in the database."""
        earnings_date = date.today() + timedelta(days=5)
        existing = MarketEvent(
            event_type=EventType.EARNINGS_UPCOMING,
            symbol="AAPL",
            headline="Existing",
            summary="Existing",
            source="test",
            earnings_date=earnings_date,
        )
        mock_store.get_upcoming_earnings.return_value = [existing]

        fetcher = EarningsCalendarFetcher(events_store=mock_store)
        new_events = [
            MarketEvent(
                event_type=EventType.EARNINGS_UPCOMING,
                symbol="AAPL",
                headline="Duplicate",
                summary="Duplicate",
                source="test",
                earnings_date=earnings_date,
            )
        ]
        result = fetcher._deduplicate_and_store(new_events)
        assert len(result) == 0
        mock_store.save_event.assert_not_called()

    def test_fetch_upcoming_no_api_key_no_yfinance(self, mock_store: MagicMock) -> None:
        """Should return empty list when no data source available."""
        fetcher = EarningsCalendarFetcher(events_store=mock_store, api_key=None)
        # Mock env to return None
        with patch.dict("os.environ", {}, clear=True):
            fetcher.api_key = None
            result = fetcher.fetch_upcoming_earnings()
        assert result == []


# ===================================================================
# EarningsPlayAgent
# ===================================================================


class TestEarningsPlayAgent:
    """Tests for the earnings play agent."""

    @pytest.fixture()
    def mock_llm(self) -> MagicMock:
        """Create a mock LLM client."""
        return MagicMock()

    @pytest.fixture()
    def agent(self, mock_llm: MagicMock) -> EarningsPlayAgent:
        """Create an agent with mock LLM."""
        return EarningsPlayAgent(llm=mock_llm)

    def test_classify_pre_earnings_drift(self, agent: EarningsPlayAgent) -> None:
        """Events 3–5 days out should be classified as pre-drift."""
        event = MagicMock()
        assert agent.classify_earnings_play(event, days_until_earnings=3) == EarningsPlayType.PRE_EARNINGS_DRIFT
        assert agent.classify_earnings_play(event, days_until_earnings=5) == EarningsPlayType.PRE_EARNINGS_DRIFT

    def test_classify_post_earnings_momentum(self, agent: EarningsPlayAgent) -> None:
        """Events just after earnings should be post-momentum."""
        event = MagicMock()
        assert agent.classify_earnings_play(event, days_until_earnings=-1) == EarningsPlayType.POST_EARNINGS_MOMENTUM
        assert agent.classify_earnings_play(event, days_until_earnings=-3) == EarningsPlayType.POST_EARNINGS_MOMENTUM

    def test_classify_skip_too_far(self, agent: EarningsPlayAgent) -> None:
        """Events too far out should be skipped."""
        event = MagicMock()
        assert agent.classify_earnings_play(event, days_until_earnings=10) == EarningsPlayType.SKIP
        assert agent.classify_earnings_play(event, days_until_earnings=-5) == EarningsPlayType.SKIP

    def test_extract_earnings_events_from_dicts(self, agent: EarningsPlayAgent) -> None:
        """Should extract earnings events from context event dicts."""
        from beavr.agents.base import AgentContext

        ctx = AgentContext(
            current_date=str(date.today()),
            timestamp=str(datetime.now()),
            prices={"AAPL": Decimal("180")},
            bars={},
            indicators={},
            cash=Decimal("10000"),
            positions={},
            portfolio_value=Decimal("10000"),
            current_drawdown=0.0,
            peak_value=Decimal("10000"),
            risk_budget=1.0,
            events=[
                {
                    "event_type": "earnings_upcoming",
                    "symbol": "AAPL",
                    "headline": "AAPL Earnings",
                    "summary": "Reporting soon",
                    "source": "test",
                    "earnings_date": (date.today() + timedelta(days=3)).isoformat(),
                },
                {
                    "event_type": "news_catalyst",
                    "symbol": "MSFT",
                    "headline": "MSFT News",
                    "summary": "Some news",
                    "source": "test",
                },
            ],
        )
        events = agent._extract_earnings_events(ctx)
        assert len(events) == 1
        assert events[0].symbol == "AAPL"

    def test_analyze_no_events(self, agent: EarningsPlayAgent) -> None:
        """Should return empty proposal when no earnings events."""
        from beavr.agents.base import AgentContext

        ctx = AgentContext(
            current_date=str(date.today()),
            timestamp=str(datetime.now()),
            prices={},
            bars={},
            indicators={},
            cash=Decimal("10000"),
            positions={},
            portfolio_value=Decimal("10000"),
            current_drawdown=0.0,
            peak_value=Decimal("10000"),
            risk_budget=1.0,
            events=[],
        )
        result = agent.analyze(ctx)
        assert result.conviction == 0.0
        assert len(result.signals) == 0

    def test_analyze_with_llm_response(self, agent: EarningsPlayAgent, mock_llm: MagicMock) -> None:
        """Should produce thesis from LLM earnings analysis."""
        from beavr.agents.base import AgentContext

        mock_llm.reason.return_value = EarningsAnalysisBatch(
            analyses=[
                EarningsAnalysisOutput(
                    symbol="AAPL",
                    play_type="pre_earnings_drift",
                    direction="long",
                    conviction=0.75,
                    entry_rationale="Strong beat streak, institutional accumulation",
                    catalyst="Q1 earnings report",
                    target_pct=5.0,
                    stop_pct=3.0,
                    risk_factors=["Macro headwinds"],
                ),
            ],
            market_outlook="Favorable earnings season",
            overall_conviction=0.7,
        )

        ctx = AgentContext(
            current_date=str(date.today()),
            timestamp=str(datetime.now()),
            prices={"AAPL": Decimal("180")},
            bars={},
            indicators={},
            cash=Decimal("10000"),
            positions={},
            portfolio_value=Decimal("10000"),
            current_drawdown=0.0,
            peak_value=Decimal("10000"),
            risk_budget=1.0,
            events=[
                {
                    "event_type": "earnings_upcoming",
                    "symbol": "AAPL",
                    "headline": "AAPL Earnings",
                    "summary": "Q1 report",
                    "source": "test",
                    "earnings_date": (date.today() + timedelta(days=3)).isoformat(),
                },
            ],
        )

        result = agent.analyze(ctx)
        assert len(result.signals) == 1
        assert result.signals[0]["symbol"] == "AAPL"
        assert result.extra["theses_created"] == 1

    def test_create_thesis_from_analysis(self, agent: EarningsPlayAgent) -> None:
        """Should create a proper TradeThesis from analysis output."""
        from beavr.agents.base import AgentContext

        analysis = EarningsAnalysisOutput(
            symbol="TSLA",
            play_type="pre_earnings_drift",
            direction="long",
            conviction=0.8,
            entry_rationale="Consistent beat streak",
            catalyst="Q4 deliveries report",
            target_pct=6.0,
            stop_pct=3.5,
            risk_factors=["EV competition"],
        )

        ctx = AgentContext(
            current_date=str(date.today()),
            timestamp=str(datetime.now()),
            prices={"TSLA": Decimal("250")},
            bars={},
            indicators={},
            cash=Decimal("10000"),
            positions={},
            portfolio_value=Decimal("10000"),
            current_drawdown=0.0,
            peak_value=Decimal("10000"),
            risk_budget=1.0,
        )

        thesis = agent._create_thesis_from_analysis(analysis, ctx)
        assert thesis is not None
        assert thesis.symbol == "TSLA"
        assert thesis.source == "earnings_agent"
        assert thesis.confidence == 0.8
        assert thesis.profit_target > Decimal("250")
        assert thesis.stop_loss < Decimal("250")

    def test_create_thesis_no_price(self, agent: EarningsPlayAgent) -> None:
        """Should return None when price data is missing."""
        from beavr.agents.base import AgentContext

        analysis = EarningsAnalysisOutput(
            symbol="XXX",
            play_type="pre_earnings_drift",
            direction="long",
            conviction=0.8,
            entry_rationale="Test",
            catalyst="Test",
            target_pct=5.0,
            stop_pct=3.0,
        )

        ctx = AgentContext(
            current_date=str(date.today()),
            timestamp=str(datetime.now()),
            prices={},
            bars={},
            indicators={},
            cash=Decimal("10000"),
            positions={},
            portfolio_value=Decimal("10000"),
            current_drawdown=0.0,
            peak_value=Decimal("10000"),
            risk_budget=1.0,
        )

        thesis = agent._create_thesis_from_analysis(analysis, ctx)
        assert thesis is None

    def test_low_conviction_skipped(self, agent: EarningsPlayAgent, mock_llm: MagicMock) -> None:
        """Low conviction analyses should not produce theses."""
        from beavr.agents.base import AgentContext

        mock_llm.reason.return_value = EarningsAnalysisBatch(
            analyses=[
                EarningsAnalysisOutput(
                    symbol="AAPL",
                    play_type="pre_earnings_drift",
                    conviction=0.2,  # Very low
                    entry_rationale="Weak signal",
                    catalyst="Earnings",
                    target_pct=5.0,
                    stop_pct=3.0,
                ),
            ],
            overall_conviction=0.2,
        )

        ctx = AgentContext(
            current_date=str(date.today()),
            timestamp=str(datetime.now()),
            prices={"AAPL": Decimal("180")},
            bars={},
            indicators={},
            cash=Decimal("10000"),
            positions={},
            portfolio_value=Decimal("10000"),
            current_drawdown=0.0,
            peak_value=Decimal("10000"),
            risk_budget=1.0,
            events=[
                {
                    "event_type": "earnings_upcoming",
                    "symbol": "AAPL",
                    "headline": "AAPL earnings",
                    "summary": "test",
                    "source": "test",
                    "earnings_date": (date.today() + timedelta(days=3)).isoformat(),
                },
            ],
        )

        result = agent.analyze(ctx)
        assert result.extra["theses_created"] == 0

    def test_system_prompt_defined(self, agent: EarningsPlayAgent) -> None:
        """System prompt should be non-empty and define earnings expertise."""
        prompt = agent.get_system_prompt()
        assert "earnings" in prompt.lower()
        assert len(prompt) > 100


# ===================================================================
# Orchestrator earnings scan integration
# ===================================================================


class TestOrchestratorEarningsScan:
    """Tests for _scan_earnings_calendar in orchestrator."""

    def test_noop_without_fetcher(self) -> None:
        """Should not raise when earnings fetcher is not configured."""
        from beavr.orchestrator.v2_engine import V2AutonomousOrchestrator

        orch = V2AutonomousOrchestrator()
        orch._scan_earnings_calendar()  # Should be a no-op

    def test_noop_without_agent(self) -> None:
        """Should not raise when earnings agent is not configured."""
        from beavr.orchestrator.v2_engine import V2AutonomousOrchestrator

        orch = V2AutonomousOrchestrator()
        orch._earnings_fetcher = MagicMock()
        orch._scan_earnings_calendar()  # Should be a no-op

    def test_scan_with_no_events(self) -> None:
        """Should handle empty earnings calendar gracefully."""
        from beavr.orchestrator.v2_engine import V2AutonomousOrchestrator

        orch = V2AutonomousOrchestrator()
        mock_fetcher = MagicMock()
        mock_fetcher.fetch_upcoming_earnings.return_value = []
        orch._earnings_fetcher = mock_fetcher
        orch._earnings_agent = MagicMock()

        orch._scan_earnings_calendar()
        mock_fetcher.fetch_upcoming_earnings.assert_called_once()


# ===================================================================
# EarningsPlayType enum
# ===================================================================


class TestEarningsPlayType:
    """Tests for the EarningsPlayType enum."""

    def test_all_values(self) -> None:
        """Enum should have exactly 3 values."""
        assert len(EarningsPlayType) == 3
        assert EarningsPlayType.PRE_EARNINGS_DRIFT.value == "pre_earnings_drift"
        assert EarningsPlayType.POST_EARNINGS_MOMENTUM.value == "post_earnings_momentum"
        assert EarningsPlayType.SKIP.value == "skip"
