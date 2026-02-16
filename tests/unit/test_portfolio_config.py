"""Tests for portfolio configuration helpers and directive injection."""

from decimal import Decimal

import pytest

from beavr.models.portfolio_record import Aggressiveness
from beavr.orchestrator.portfolio_config import (
    CONFIDENCE_THRESHOLDS,
    apply_aggressiveness,
    build_portfolio_state_path,
    format_directives_for_prompt,
)
from beavr.orchestrator.v2_engine import V2Config

# ===================================================================
# apply_aggressiveness
# ===================================================================


class TestApplyAggressiveness:
    """Tests for aggressiveness → V2Config override mapping."""

    def test_conservative_reduces_risk(self) -> None:
        """Conservative profile should lower risk limits."""
        config = apply_aggressiveness(V2Config(), "conservative")
        assert config.max_daily_loss_pct == 2.0
        assert config.max_drawdown_pct == 7.0
        assert config.daily_trade_limit == 3

    def test_moderate_is_default(self) -> None:
        """Moderate profile should match default-ish config."""
        config = apply_aggressiveness(V2Config(), "moderate")
        assert config.max_daily_loss_pct == 3.0
        assert config.daily_trade_limit == 5

    def test_aggressive_increases_risk(self) -> None:
        """Aggressive profile should raise limits."""
        config = apply_aggressiveness(V2Config(), "aggressive")
        assert config.max_daily_loss_pct == 5.0
        assert config.max_drawdown_pct == 15.0
        assert config.daily_trade_limit == 8
        assert config.max_position_pct == 0.15
        assert config.day_trade_target_pct == 8.0

    def test_preserves_non_overridden_fields(self) -> None:
        """Fields not in override map should stay unchanged."""
        base = V2Config(news_poll_interval=999)
        config = apply_aggressiveness(base, "aggressive")
        assert config.news_poll_interval == 999

    def test_returns_new_instance(self) -> None:
        """Should return a new V2Config, not mutate the original."""
        original = V2Config()
        modified = apply_aggressiveness(original, "aggressive")
        assert original.max_daily_loss_pct != modified.max_daily_loss_pct
        assert original.max_daily_loss_pct == 3.0

    def test_invalid_aggressiveness_raises(self) -> None:
        """Should raise ValueError for invalid aggressiveness."""
        with pytest.raises(ValueError):
            apply_aggressiveness(V2Config(), "yolo")

    @pytest.mark.parametrize(
        "level",
        ["conservative", "moderate", "aggressive"],
    )
    def test_all_levels_valid(self, level: str) -> None:
        """All aggressiveness levels should produce a valid config."""
        config = apply_aggressiveness(V2Config(), level)
        assert isinstance(config, V2Config)


class TestConfidenceThresholds:
    """Tests for confidence threshold lookup."""

    def test_all_levels_have_thresholds(self) -> None:
        """Every aggressiveness level should have confidence thresholds."""
        for level in Aggressiveness:
            assert level in CONFIDENCE_THRESHOLDS
            t = CONFIDENCE_THRESHOLDS[level]
            assert "min_thesis_confidence" in t
            assert "dd_min_approval_confidence" in t

    def test_conservative_highest_thresholds(self) -> None:
        """Conservative should have highest confidence requirements."""
        c = CONFIDENCE_THRESHOLDS[Aggressiveness.CONSERVATIVE]
        assert c["min_thesis_confidence"] == 0.75
        assert c["dd_min_approval_confidence"] == 0.80

    def test_aggressive_lowest_thresholds(self) -> None:
        """Aggressive should have lowest requirements."""
        a = CONFIDENCE_THRESHOLDS[Aggressiveness.AGGRESSIVE]
        assert a["min_thesis_confidence"] == 0.45


# ===================================================================
# format_directives_for_prompt
# ===================================================================


class TestFormatDirectives:
    """Tests for formatting directives into LLM prompt text."""

    def test_empty_returns_empty(self) -> None:
        """No directives should produce empty string."""
        assert format_directives_for_prompt([]) == ""

    def test_single_directive(self) -> None:
        """Single directive should be formatted."""
        result = format_directives_for_prompt(["Focus on tech"])
        assert "Focus on tech" in result
        assert "USER TRADING DIRECTIVES" in result

    def test_multiple_directives(self) -> None:
        """Multiple directives should all appear."""
        result = format_directives_for_prompt(["A", "B", "C"])
        assert "- A" in result
        assert "- B" in result
        assert "- C" in result

    def test_includes_instruction_footer(self) -> None:
        """Should include instruction to factor preferences."""
        result = format_directives_for_prompt(["test"])
        assert "Factor these preferences" in result


# ===================================================================
# build_portfolio_state_path
# ===================================================================


class TestBuildPortfolioStatePath:
    """Tests for per-portfolio state file path generation."""

    def test_default_log_dir(self) -> None:
        """Should use default log dir."""
        path = build_portfolio_state_path("abc123")
        assert path == "logs/ai_investor/state_abc123.json"

    def test_custom_log_dir(self) -> None:
        """Should use custom log dir."""
        path = build_portfolio_state_path("xyz", "/tmp/logs")
        assert path == "/tmp/logs/state_xyz.json"


# ===================================================================
# AgentContext directives field
# ===================================================================


class TestAgentContextDirectives:
    """Tests for the directives field on AgentContext."""

    def test_default_empty(self) -> None:
        """Directives should default to empty list."""
        from beavr.agents.base import AgentContext

        ctx = AgentContext(
            current_date="2026-01-01",
            timestamp="2026-01-01T00:00:00",
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
        assert ctx.directives == []

    def test_accepts_directives(self) -> None:
        """Should accept directive strings."""
        from beavr.agents.base import AgentContext

        ctx = AgentContext(
            current_date="2026-01-01",
            timestamp="2026-01-01T00:00:00",
            prices={},
            bars={},
            indicators={},
            cash=Decimal("10000"),
            positions={},
            portfolio_value=Decimal("10000"),
            current_drawdown=0.0,
            peak_value=Decimal("10000"),
            risk_budget=1.0,
            directives=["Focus on tech", "Avoid biotech"],
        )
        assert len(ctx.directives) == 2


# ===================================================================
# V2AutonomousOrchestrator._log_decision
# ===================================================================


class TestOrchestratorLogDecision:
    """Tests for the orchestrator decision logging helper."""

    def test_log_decision_noop_without_stores(self) -> None:
        """Should not raise when stores are not wired."""
        from beavr.orchestrator.v2_engine import V2AutonomousOrchestrator

        orch = V2AutonomousOrchestrator()
        # Should be a no-op, not raise
        orch._log_decision(
            decision_type="thesis_created",
            action="create",
            symbol="AAPL",
        )

    def test_log_decision_writes_to_store(self) -> None:
        """Should log decision when stores and portfolio_id are set."""
        from beavr.db.factory import create_sqlite_stores
        from beavr.orchestrator.v2_engine import V2AutonomousOrchestrator

        stores = create_sqlite_stores(":memory:")
        pid = stores.portfolios.create_portfolio(
            name="Test",
            mode="paper",
            initial_capital=Decimal("10000"),
            config_snapshot={},
            aggressiveness="moderate",
            directives=[],
        )

        orch = V2AutonomousOrchestrator(
            portfolio_id=pid,
            decision_store=stores.decisions,
        )
        orch._log_decision(
            decision_type="thesis_created",
            action="create",
            symbol="AAPL",
            reasoning="Test thesis",
        )

        decisions = stores.decisions.get_decisions(pid)
        assert len(decisions) == 1
        assert decisions[0].symbol == "AAPL"
        assert decisions[0].action == "create"
