"""Unit tests for AI Investor v2 models."""

from datetime import date
from decimal import Decimal

import pytest

from beavr.models.dd_report import (
    DDRecommendation,
    DueDiligenceReport,
    RecommendedTradeType,
)
from beavr.models.market_event import (
    EventImportance,
    EventType,
    MarketEvent,
)
from beavr.models.morning_candidate import (
    MorningCandidate,
    ScanType,
)
from beavr.models.thesis import (
    ThesisStatus,
    TradeDirection,
    TradeThesis,
    TradeType,
)


class TestTradeThesis:
    """Tests for TradeThesis model."""
    
    def test_thesis_creation(self) -> None:
        """Test creating a basic thesis."""
        thesis = TradeThesis(
            symbol="AAPL",
            trade_type=TradeType.SWING_SHORT,
            entry_rationale="Strong momentum after earnings beat",
            catalyst="Q4 earnings report",
            entry_price_target=Decimal("180.00"),
            profit_target=Decimal("195.00"),
            stop_loss=Decimal("172.00"),
            expected_exit_date=date(2026, 2, 15),
            max_hold_date=date(2026, 2, 20),
        )
        
        assert thesis.symbol == "AAPL"
        assert thesis.trade_type == TradeType.SWING_SHORT
        assert thesis.status == ThesisStatus.DRAFT
        assert thesis.direction == TradeDirection.LONG
        assert thesis.dd_approved is False
    
    def test_thesis_risk_reward_ratio(self) -> None:
        """Test risk/reward ratio calculation."""
        thesis = TradeThesis(
            symbol="NVDA",
            trade_type=TradeType.SWING_SHORT,
            entry_rationale="AI chip demand",
            catalyst="Product launch",
            entry_price_target=Decimal("100.00"),
            profit_target=Decimal("120.00"),  # +20%
            stop_loss=Decimal("90.00"),  # -10%
            expected_exit_date=date(2026, 2, 15),
            max_hold_date=date(2026, 2, 20),
        )
        
        # Risk = 10, Reward = 20, R/R = 2:1
        assert thesis.risk_reward_ratio == 2.0
    
    def test_thesis_target_and_stop_pct(self) -> None:
        """Test target and stop percentage calculations."""
        thesis = TradeThesis(
            symbol="TSLA",
            trade_type=TradeType.DAY_TRADE,
            entry_rationale="Gap up momentum",
            catalyst="News catalyst",
            entry_price_target=Decimal("200.00"),
            profit_target=Decimal("210.00"),  # +5%
            stop_loss=Decimal("196.00"),  # -2%
            expected_exit_date=date(2026, 2, 4),
            max_hold_date=date(2026, 2, 4),
        )
        
        assert thesis.target_pct == 5.0
        assert thesis.stop_pct == 2.0
    
    def test_thesis_with_invalidation_conditions(self) -> None:
        """Test thesis with invalidation conditions."""
        thesis = TradeThesis(
            symbol="MSFT",
            trade_type=TradeType.SWING_LONG,
            entry_rationale="Cloud growth accelerating",
            catalyst="Azure revenue report",
            entry_price_target=Decimal("400.00"),
            profit_target=Decimal("450.00"),
            stop_loss=Decimal("380.00"),
            expected_exit_date=date(2026, 3, 1),
            max_hold_date=date(2026, 3, 15),
            invalidation_conditions=[
                "Azure growth decelerates below 20%",
                "Market enters bear regime",
            ],
        )
        
        assert len(thesis.invalidation_conditions) == 2
        assert "Azure" in thesis.invalidation_conditions[0]
    
    def test_thesis_str_representation(self) -> None:
        """Test thesis string representation."""
        thesis = TradeThesis(
            symbol="META",
            trade_type=TradeType.SWING_SHORT,
            entry_rationale="Testing",
            catalyst="Earnings",
            entry_price_target=Decimal("500.00"),
            profit_target=Decimal("550.00"),
            stop_loss=Decimal("480.00"),
            expected_exit_date=date(2026, 2, 10),
            max_hold_date=date(2026, 2, 15),
        )
        
        thesis_str = str(thesis)
        assert "META" in thesis_str
        assert "LONG" in thesis_str
        assert "$500" in thesis_str


class TestDueDiligenceReport:
    """Tests for DueDiligenceReport model."""
    
    def test_dd_report_approval(self) -> None:
        """Test creating an approved DD report."""
        report = DueDiligenceReport(
            symbol="AAPL",
            recommended_trade_type=RecommendedTradeType.SWING_SHORT,
            trade_type_rationale="Near-term earnings catalyst with 2-week expected move",
            recommendation=DDRecommendation.APPROVE,
            confidence=0.85,
            executive_summary="AAPL shows strong fundamentals with clear catalyst.",
            fundamental_summary="Strong financials, growing revenue",
            technical_summary="Above 50 SMA, bullish momentum",
            catalyst_assessment="Earnings catalyst is clear and timely",
            risk_factors=["Market volatility", "Macro uncertainty"],
            recommended_entry=Decimal("180.00"),
            recommended_target=Decimal("195.00"),
            recommended_stop=Decimal("172.00"),
            recommended_position_size_pct=0.15,
            approval_rationale="Solid setup with favorable R/R",
        )
        
        assert report.recommendation == DDRecommendation.APPROVE
        assert report.is_approved is True
        assert report.confidence == 0.85
        assert report.recommended_trade_type == RecommendedTradeType.SWING_SHORT
    
    def test_dd_report_rejection(self) -> None:
        """Test creating a rejected DD report."""
        report = DueDiligenceReport(
            symbol="PUMP",
            recommended_trade_type=RecommendedTradeType.DAY_TRADE,
            trade_type_rationale="If traded, only for day trade due to high risk",
            recommendation=DDRecommendation.REJECT,
            confidence=0.90,
            executive_summary="PUMP is a speculative penny stock - avoid.",
            fundamental_summary="No revenue, speculative company",
            technical_summary="Extended, overbought",
            catalyst_assessment="No clear catalyst",
            risk_factors=["Penny stock", "No fundamentals", "Pump and dump risk"],
            recommended_entry=Decimal("5.00"),
            recommended_target=Decimal("6.00"),
            recommended_stop=Decimal("4.50"),
            recommended_position_size_pct=0.05,
            rejection_rationale="Does not meet quality standards",
        )
        
        assert report.recommendation == DDRecommendation.REJECT
        assert report.is_approved is False
    
    def test_dd_report_conditional(self) -> None:
        """Test creating a conditional DD report."""
        report = DueDiligenceReport(
            symbol="NVDA",
            recommended_trade_type=RecommendedTradeType.SWING_MEDIUM,
            trade_type_rationale="Product launch catalyst suggests 1-3 month timeframe",
            recommendation=DDRecommendation.CONDITIONAL,
            confidence=0.70,
            executive_summary="NVDA attractive but wait for pullback.",
            fundamental_summary="Strong but expensive",
            technical_summary="Extended but momentum intact",
            catalyst_assessment="Product launch next week",
            risk_factors=["High valuation", "Extended technicals"],
            recommended_entry=Decimal("800.00"),
            recommended_target=Decimal("880.00"),
            recommended_stop=Decimal("760.00"),
            recommended_position_size_pct=0.10,
            conditions=[
                "Wait for pullback to $820 support",
                "Confirm volume on bounce",
            ],
        )
        
        assert report.recommendation == DDRecommendation.CONDITIONAL
        assert report.is_approved is True  # Conditional counts as approved
        assert len(report.conditions) == 2
    
    def test_dd_report_risk_reward(self) -> None:
        """Test risk/reward calculation on DD report."""
        report = DueDiligenceReport(
            symbol="TEST",
            recommended_trade_type=RecommendedTradeType.SWING_SHORT,
            trade_type_rationale="Test trade type",
            recommendation=DDRecommendation.APPROVE,
            confidence=0.80,
            executive_summary="Test summary.",
            fundamental_summary="Test",
            technical_summary="Test",
            catalyst_assessment="Test",
            recommended_entry=Decimal("100.00"),
            recommended_target=Decimal("115.00"),  # +15
            recommended_stop=Decimal("95.00"),  # -5
            recommended_position_size_pct=0.10,
        )
        
        # R/R = 15/5 = 3:1
        assert report.risk_reward_ratio == 3.0


class TestMarketEvent:
    """Tests for MarketEvent model."""
    
    def test_earnings_event(self) -> None:
        """Test creating an earnings event."""
        event = MarketEvent(
            event_type=EventType.EARNINGS_UPCOMING,
            symbol="AAPL",
            headline="Apple to report Q1 earnings Feb 6",
            summary="Apple Inc. scheduled to report earnings after close",
            source="alpaca",
            importance=EventImportance.HIGH,
            earnings_date=date(2026, 2, 6),
            estimate_eps=Decimal("2.10"),
        )
        
        assert event.event_type == EventType.EARNINGS_UPCOMING
        assert event.is_earnings_related is True
        assert event.is_actionable is True
    
    def test_analyst_upgrade_event(self) -> None:
        """Test creating an analyst upgrade event."""
        event = MarketEvent(
            event_type=EventType.ANALYST_UPGRADE,
            symbol="NVDA",
            headline="Goldman upgrades NVDA to Buy",
            summary="Goldman Sachs upgrades NVIDIA citing AI demand",
            source="alpaca",
            importance=EventImportance.MEDIUM,
            analyst_firm="Goldman Sachs",
            old_rating="Hold",
            new_rating="Buy",
            old_price_target=Decimal("800"),
            new_price_target=Decimal("1000"),
        )
        
        assert event.analyst_firm == "Goldman Sachs"
        assert event.new_rating == "Buy"
        assert event.is_earnings_related is False
    
    def test_macro_event(self) -> None:
        """Test creating a macro economic event."""
        event = MarketEvent(
            event_type=EventType.MACRO_RELEASE,
            symbol=None,  # Macro events don't have a symbol
            headline="Fed announces rate decision",
            summary="Federal Reserve holds rates steady at 4.5%",
            source="alpaca",
            importance=EventImportance.HIGH,
        )
        
        assert event.symbol is None
        assert event.event_type == EventType.MACRO_RELEASE
    
    def test_event_str_representation(self) -> None:
        """Test event string representation."""
        event = MarketEvent(
            event_type=EventType.NEWS_CATALYST,
            symbol="TSLA",
            headline="Tesla announces new product",
            summary="Tesla unveils new vehicle",
            source="alpaca",
            importance=EventImportance.MEDIUM,
        )
        
        event_str = str(event)
        assert "TSLA" in event_str
        assert "Tesla" in event_str


class TestMorningCandidate:
    """Tests for MorningCandidate model."""
    
    def test_gap_up_candidate(self) -> None:
        """Test creating a gap up candidate."""
        candidate = MorningCandidate(
            symbol="AAPL",
            scan_type=ScanType.GAP_UP,
            pre_market_price=Decimal("185.00"),
            previous_close=Decimal("175.00"),
            pre_market_change_pct=5.7,
            pre_market_volume=5_000_000,
            avg_daily_volume=50_000_000,
            volume_ratio=2.5,
            catalyst_summary="Gapping up 5.7% on strong earnings beat",
            preliminary_direction="long",
            preliminary_target_pct=8.0,
            preliminary_stop_pct=3.0,
            conviction_score=0.75,
            priority_rank=1,
        )
        
        assert candidate.scan_type == ScanType.GAP_UP
        assert candidate.gap_pct == pytest.approx(5.7, rel=0.1)
        assert candidate.risk_reward_ratio == pytest.approx(8.0 / 3.0, rel=0.01)
    
    def test_volume_surge_candidate(self) -> None:
        """Test creating a volume surge candidate."""
        candidate = MorningCandidate(
            symbol="NVDA",
            scan_type=ScanType.VOLUME_SURGE,
            pre_market_price=Decimal("850.00"),
            previous_close=Decimal("845.00"),
            pre_market_change_pct=0.6,
            pre_market_volume=10_000_000,
            avg_daily_volume=30_000_000,
            volume_ratio=3.3,
            catalyst_summary="Volume surge 3.3x average",
            preliminary_direction="long",
            preliminary_target_pct=5.0,
            preliminary_stop_pct=2.0,
            conviction_score=0.65,
            priority_rank=2,
        )
        
        assert candidate.scan_type == ScanType.VOLUME_SURGE
        assert candidate.volume_ratio == 3.3
    
    def test_candidate_with_thesis_alignment(self) -> None:
        """Test candidate aligned with active thesis."""
        candidate = MorningCandidate(
            symbol="MSFT",
            scan_type=ScanType.THESIS_SETUP,
            pre_market_price=Decimal("410.00"),
            previous_close=Decimal("405.00"),
            pre_market_change_pct=1.2,
            pre_market_volume=2_000_000,
            avg_daily_volume=20_000_000,
            volume_ratio=1.5,
            catalyst_summary="Thesis setup: Azure earnings tomorrow",
            has_active_thesis=True,
            thesis_id="abc123",
            preliminary_direction="long",
            preliminary_target_pct=10.0,
            preliminary_stop_pct=4.0,
            conviction_score=0.80,
            priority_rank=1,
        )
        
        assert candidate.has_active_thesis is True
        assert candidate.thesis_id == "abc123"
        assert candidate.scan_type == ScanType.THESIS_SETUP
    
    def test_candidate_quality_flags(self) -> None:
        """Test quality flags on candidate."""
        candidate = MorningCandidate(
            symbol="PUMP",
            scan_type=ScanType.GAP_UP,
            pre_market_price=Decimal("3.50"),  # Low price
            previous_close=Decimal("2.00"),
            pre_market_change_pct=75.0,  # Extreme move
            pre_market_volume=50_000_000,
            avg_daily_volume=10_000_000,
            volume_ratio=5.0,
            catalyst_summary="Unknown catalyst",
            preliminary_direction="long",
            preliminary_target_pct=20.0,
            preliminary_stop_pct=10.0,
            conviction_score=0.40,
            priority_rank=10,
            is_quality_stock=False,
            quality_notes="Price below $10",
            extreme_move=True,
        )
        
        assert candidate.is_quality_stock is False
        assert candidate.extreme_move is True
        assert "Price below" in candidate.quality_notes
