"""Regression tests for AI Investor v2 CLI wiring.

These tests ensure the v2 commands are correctly wired to the v2 models/agents
and don't crash due to import mismatches.

We mock external dependencies (Alpaca, LLM providers) so the tests are
fast, deterministic, and offline.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pandas as pd
from typer.testing import CliRunner

import beavr.agents as agents_mod
import beavr.cli.ai as ai_cli
import beavr.llm as llm_mod
from beavr.models.dd_report import DDRecommendation, DueDiligenceReport, RecommendedTradeType
from beavr.models.thesis import TradeDirection, TradeThesis, TradeType


class _FakeFetcher:
    def __init__(self, df: pd.DataFrame) -> None:
        self._df = df

    def get_bars(self, symbol: str, start, end, timeframe: str = "1Day") -> pd.DataFrame:  # noqa: ANN001
        return self._df


class _FakeInvestor:
    def __init__(self, df: pd.DataFrame) -> None:
        self._data_provider = _FakeFetcher(df)
        self._db = SimpleNamespace()

    @property
    def data_provider(self) -> _FakeFetcher:
        return self._data_provider

    @property
    def db(self):  # noqa: ANN001
        return self._db

    def get_account(self) -> dict:
        return {
            "equity": Decimal("10000"),
            "cash": Decimal("5000"),
            "buying_power": Decimal("15000"),
            "positions": {},
        }


class _FakeLLMClient:
    def __init__(self, config, agent_name: str = "") -> None:  # noqa: ANN001
        self.config = config


class _FakeThesisGeneratorAgent:
    def __init__(self, llm) -> None:  # noqa: ANN001
        self._llm = llm

    def generate_thesis_from_event(self, event, ctx):  # noqa: ANN001
        _ = (event, ctx)
        today = datetime(2026, 2, 4).date()
        return TradeThesis(
            symbol="AAPL",
            trade_type=TradeType.SWING_SHORT,
            direction=TradeDirection.LONG,
            entry_rationale="Test rationale",
            catalyst="Test catalyst",
            entry_price_target=Decimal("100.00"),
            profit_target=Decimal("108.00"),
            stop_loss=Decimal("96.00"),
            expected_exit_date=today + timedelta(days=10),
            max_hold_date=today + timedelta(days=14),
            invalidation_conditions=["Test invalidation"],
            confidence=0.7,
            source="test",
        )


class _FakeDueDiligenceAgent:
    def __init__(self, llm, save_reports: bool = False) -> None:  # noqa: ANN001
        _ = (llm, save_reports)

    def analyze_thesis(self, thesis, ctx):  # noqa: ANN001
        _ = (thesis, ctx)
        return DueDiligenceReport(
            thesis_id=getattr(thesis, "id", None),
            symbol="AAPL",
            recommended_trade_type=RecommendedTradeType.SWING_SHORT,
            trade_type_rationale="Test",
            recommendation=DDRecommendation.CONDITIONAL,
            confidence=0.55,
            executive_summary="Test summary",
            fundamental_summary="Test fundamentals",
            technical_summary="Test technicals",
            catalyst_assessment="Test catalyst",
            risk_factors=["Risk 1"],
            recommended_entry=Decimal("100.00"),
            recommended_target=Decimal("108.00"),
            recommended_stop=Decimal("96.00"),
            recommended_position_size_pct=0.10,
            swing_trade_plan=None,
            day_trade_plan=None,
        )


def _sample_bars_df() -> pd.DataFrame:
    # Build a minimal OHLCV dataframe resembling AlpacaDataFetcher output
    base = datetime(2026, 1, 1)
    rows = []
    for i in range(30):
        ts = base + timedelta(days=i)
        rows.append(
            {
                "timestamp": ts,
                "open": Decimal("99.00"),
                "high": Decimal("101.00"),
                "low": Decimal("98.00"),
                "close": Decimal("100.00"),
                "volume": 1_000_000,
            }
        )
    return pd.DataFrame(rows)


class TestAIV2CliCommands:
    """Smoke tests for the v2 CLI commands."""

    def test_thesis_command_runs_with_mocks(self, monkeypatch) -> None:
        runner = CliRunner()
        df = _sample_bars_df()

        monkeypatch.setattr(ai_cli, "get_investor", lambda: _FakeInvestor(df))
        monkeypatch.setattr(llm_mod, "LLMClient", _FakeLLMClient)
        monkeypatch.setattr(llm_mod, "get_agent_config", lambda _name: SimpleNamespace(model="test", temperature=0.0))
        monkeypatch.setattr(agents_mod, "ThesisGeneratorAgent", _FakeThesisGeneratorAgent)

        result = runner.invoke(ai_cli.ai_app, ["thesis", "test event", "--symbol", "AAPL"])
        assert result.exit_code == 0
        assert "Generated Thesis" in result.output
        assert "AAPL" in result.output

    def test_dd_command_runs_with_mocks(self, monkeypatch) -> None:
        runner = CliRunner()
        df = _sample_bars_df()

        monkeypatch.setattr(ai_cli, "get_investor", lambda: _FakeInvestor(df))
        monkeypatch.setattr(llm_mod, "LLMClient", _FakeLLMClient)
        monkeypatch.setattr(llm_mod, "get_agent_config", lambda _name: SimpleNamespace(model="test", temperature=0.0))
        monkeypatch.setattr(agents_mod, "DueDiligenceAgent", _FakeDueDiligenceAgent)

        result = runner.invoke(
            ai_cli.ai_app,
            ["dd", "--symbol", "AAPL", "--rationale", "Test", "--no-save"],
        )
        assert result.exit_code == 0
        assert "Due Diligence" in result.output
        assert "AAPL" in result.output
