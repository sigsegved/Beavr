"""SQLite implementation of DD report store."""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from beavr.models.dd_report import (
    DDRecommendation,
    DDSummary,
    DueDiligenceReport,
)

if TYPE_CHECKING:
    from beavr.db.sqlite.connection import Database


class SQLiteDDReportStore:
    """
    SQLite implementation of the DDReportStore protocol.

    Stores DD analysis results for audit trail and learning.
    """

    def __init__(self, db: Database) -> None:
        """Initialize the store."""
        self.db = db

    def save_report(self, report: DueDiligenceReport) -> str:
        """
        Store a new DD report.

        Args:
            report: DueDiligenceReport to persist

        Returns:
            Report ID
        """
        risk_factors_json = json.dumps(report.risk_factors)
        data_sources_json = json.dumps(report.data_sources_used)
        conditions_json = json.dumps(report.conditions) if report.conditions else None

        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO dd_reports
                (id, thesis_id, symbol, timestamp, recommendation, confidence,
                 fundamental_summary, technical_summary, catalyst_assessment,
                 risk_factors, market_cap, pe_ratio, revenue_growth,
                 institutional_ownership, recommended_entry, recommended_target,
                 recommended_stop, recommended_position_size_pct, approval_rationale,
                 rejection_rationale, conditions, data_sources_used, processing_time_ms,
                 llm_model)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    report.id,
                    report.thesis_id,
                    report.symbol,
                    report.timestamp.isoformat(),
                    report.recommendation.value,
                    report.confidence,
                    report.fundamental_summary,
                    report.technical_summary,
                    report.catalyst_assessment,
                    risk_factors_json,
                    float(report.market_cap) if report.market_cap else None,
                    report.pe_ratio,
                    report.revenue_growth,
                    report.institutional_ownership,
                    float(report.recommended_entry),
                    float(report.recommended_target),
                    float(report.recommended_stop),
                    report.recommended_position_size_pct,
                    report.approval_rationale,
                    report.rejection_rationale,
                    conditions_json,
                    data_sources_json,
                    report.processing_time_ms,
                    report.llm_model,
                ),
            )

        return report.id

    def get_report(self, report_id: str) -> Optional[DueDiligenceReport]:
        """
        Get a DD report by ID.

        Args:
            report_id: Report ID

        Returns:
            DueDiligenceReport or None
        """
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM dd_reports WHERE id = ?",
                (report_id,),
            ).fetchone()

        if row is None:
            return None

        return self._row_to_report(row)

    def get_report_by_thesis(self, thesis_id: str) -> Optional[DueDiligenceReport]:
        """
        Get DD report for a thesis.

        Args:
            thesis_id: Thesis ID

        Returns:
            DueDiligenceReport or None
        """
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM dd_reports WHERE thesis_id = ? ORDER BY timestamp DESC LIMIT 1",
                (thesis_id,),
            ).fetchone()

        if row is None:
            return None

        return self._row_to_report(row)

    def get_reports_by_symbol(self, symbol: str, limit: int = 10) -> list[DueDiligenceReport]:
        """
        Get DD reports for a symbol.

        Args:
            symbol: Trading symbol
            limit: Maximum reports to return

        Returns:
            List of DD reports
        """
        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM dd_reports 
                WHERE symbol = ? 
                ORDER BY timestamp DESC 
                LIMIT ?
                """,
                (symbol, limit),
            ).fetchall()

        return [self._row_to_report(row) for row in rows]

    def get_recent_approvals(self, limit: int = 20) -> list[DueDiligenceReport]:
        """
        Get recent approved DD reports.

        Args:
            limit: Maximum reports to return

        Returns:
            List of approved reports
        """
        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM dd_reports 
                WHERE recommendation IN ('approve', 'conditional')
                ORDER BY timestamp DESC 
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        return [self._row_to_report(row) for row in rows]

    def get_recent_rejections(self, limit: int = 20) -> list[DueDiligenceReport]:
        """
        Get recent rejected DD reports.

        Useful for understanding what kinds of opportunities are being filtered out.

        Args:
            limit: Maximum reports to return

        Returns:
            List of rejected reports
        """
        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM dd_reports 
                WHERE recommendation = 'reject'
                ORDER BY timestamp DESC 
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        return [self._row_to_report(row) for row in rows]

    def get_approval_stats(self) -> dict:
        """
        Get DD approval statistics.

        Returns:
            Dictionary with approval stats
        """
        with self.db.connect() as conn:
            row = conn.execute(
                """
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN recommendation = 'approve' THEN 1 ELSE 0 END) as approved,
                    SUM(CASE WHEN recommendation = 'reject' THEN 1 ELSE 0 END) as rejected,
                    SUM(CASE WHEN recommendation = 'conditional' THEN 1 ELSE 0 END) as conditional,
                    AVG(confidence) as avg_confidence,
                    AVG(CASE WHEN recommendation = 'approve' THEN confidence END) as avg_approval_confidence
                FROM dd_reports
                """,
            ).fetchone()

        total = row[0] or 0
        approved = row[1] or 0
        rejected = row[2] or 0
        conditional = row[3] or 0

        return {
            "total_reports": total,
            "approved": approved,
            "rejected": rejected,
            "conditional": conditional,
            "approval_rate": (approved + conditional) / total if total > 0 else 0,
            "rejection_rate": rejected / total if total > 0 else 0,
            "avg_confidence": row[4] or 0,
            "avg_approval_confidence": row[5] or 0,
        }

    def get_report_summaries(self, limit: int = 50) -> list[DDSummary]:
        """
        Get DD report summaries for display.

        Args:
            limit: Maximum summaries to return

        Returns:
            List of DDSummary
        """
        from beavr.models.dd_report import RecommendedTradeType

        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT id, symbol, recommendation, confidence, timestamp,
                       thesis_id, recommended_entry, recommended_target,
                       recommended_stop
                FROM dd_reports
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        summaries: list[DDSummary] = []
        for row in rows:
            entry = float(row[6]) if row[6] else 0.0
            target = float(row[7]) if row[7] else 0.0
            stop = float(row[8]) if row[8] else 0.0
            risk = entry - stop if entry and stop else 0.0
            rr = ((target - entry) / risk) if risk > 0 else 0.0

            summaries.append(
                DDSummary(
                    id=row[0],
                    symbol=row[1],
                    recommendation=DDRecommendation(row[2]),
                    confidence=row[3],
                    timestamp=datetime.fromisoformat(row[4]),
                    thesis_id=row[5],
                    recommended_trade_type=RecommendedTradeType.SWING_SHORT,
                    risk_reward_ratio=round(rr, 2),
                )
            )
        return summaries

    def _row_to_report(self, row: tuple) -> DueDiligenceReport:
        """Convert database row to DueDiligenceReport."""
        risk_factors = json.loads(row[9]) if row[9] else []
        data_sources = json.loads(row[21]) if row[21] else []
        conditions = json.loads(row[20]) if row[20] else None

        return DueDiligenceReport(
            id=row[0],
            thesis_id=row[1],
            symbol=row[2],
            timestamp=datetime.fromisoformat(row[3]),
            recommendation=DDRecommendation(row[4]),
            confidence=row[5],
            fundamental_summary=row[6],
            technical_summary=row[7],
            catalyst_assessment=row[8],
            risk_factors=risk_factors,
            market_cap=Decimal(str(row[10])) if row[10] else None,
            pe_ratio=row[11],
            revenue_growth=row[12],
            institutional_ownership=row[13],
            recommended_entry=Decimal(str(row[14])),
            recommended_target=Decimal(str(row[15])),
            recommended_stop=Decimal(str(row[16])),
            recommended_position_size_pct=row[17],
            approval_rationale=row[18],
            rejection_rationale=row[19],
            conditions=conditions,
            data_sources_used=data_sources,
            processing_time_ms=row[22] or 0,
            llm_model=row[23],
        )
