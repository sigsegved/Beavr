"""Backtest results repository."""

from __future__ import annotations

import json
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Dict, List, Optional

from pydantic import BaseModel, Field

from beavr.models.trade import Trade

if TYPE_CHECKING:
    from beavr.db.connection import Database


class BacktestMetrics(BaseModel):
    """Performance metrics from a backtest run."""

    final_value: Decimal = Field(description="Final portfolio value")
    total_return: float = Field(description="Total return as decimal (0.15 = 15%)")
    cagr: Optional[float] = Field(default=None, description="Compound annual growth rate")
    max_drawdown: Optional[float] = Field(default=None, description="Maximum drawdown")
    sharpe_ratio: Optional[float] = Field(default=None, description="Sharpe ratio")
    total_trades: int = Field(description="Total number of trades")
    total_invested: Decimal = Field(description="Total amount invested")
    holdings: Dict[str, Decimal] = Field(
        default_factory=dict,
        description="Final holdings by symbol (symbol -> shares)",
    )

    model_config = {"frozen": True}


class BacktestResultsRepository:
    """
    Repository for storing and retrieving backtest results.

    Handles persistence of backtest runs, metrics, and trades.

    Attributes:
        db: Database connection manager
    """

    def __init__(self, db: Database):
        """
        Initialize the results repository.

        Args:
            db: Database connection manager
        """
        self.db = db

    def create_run(
        self,
        strategy_name: str,
        config: dict,
        start_date: date,
        end_date: date,
        initial_cash: Decimal,
    ) -> str:
        """
        Create a new backtest run.

        Args:
            strategy_name: Name of the strategy being tested
            config: Strategy configuration as dict
            start_date: Backtest start date
            end_date: Backtest end date
            initial_cash: Starting cash amount

        Returns:
            Run ID (UUID string)
        """
        run_id = str(uuid.uuid4())

        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO backtest_runs (id, strategy_name, config_json, start_date, end_date, initial_cash)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    strategy_name,
                    json.dumps(config),
                    start_date.isoformat(),
                    end_date.isoformat(),
                    float(initial_cash),
                ),
            )

        return run_id

    def save_results(self, run_id: str, metrics: BacktestMetrics) -> None:
        """
        Save metrics for a backtest run.

        Args:
            run_id: The run ID to save results for
            metrics: The performance metrics to save
        """
        # Convert holdings to JSON-serializable format
        holdings_json = {k: str(v) for k, v in metrics.holdings.items()}

        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO backtest_results
                (run_id, final_value, total_return, cagr, max_drawdown, sharpe_ratio,
                 total_trades, total_invested, holdings_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    final_value = excluded.final_value,
                    total_return = excluded.total_return,
                    cagr = excluded.cagr,
                    max_drawdown = excluded.max_drawdown,
                    sharpe_ratio = excluded.sharpe_ratio,
                    total_trades = excluded.total_trades,
                    total_invested = excluded.total_invested,
                    holdings_json = excluded.holdings_json
                """,
                (
                    run_id,
                    float(metrics.final_value),
                    metrics.total_return,
                    metrics.cagr,
                    metrics.max_drawdown,
                    metrics.sharpe_ratio,
                    metrics.total_trades,
                    float(metrics.total_invested),
                    json.dumps(holdings_json),
                ),
            )

    def save_trade(self, run_id: str, trade: Trade) -> None:
        """
        Save a single trade to backtest history.

        Args:
            run_id: The run ID this trade belongs to
            trade: The trade to save
        """
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO backtest_trades
                (run_id, symbol, side, quantity, price, amount, timestamp, reason)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    trade.symbol,
                    trade.side,  # Literal, not Enum
                    float(trade.quantity),
                    float(trade.price),
                    float(trade.amount),
                    trade.timestamp.isoformat(),
                    trade.reason,
                ),
            )

    def save_trades(self, run_id: str, trades: List[Trade]) -> None:
        """
        Batch save trades for a backtest run.

        Args:
            run_id: The run ID these trades belong to
            trades: List of trades to save
        """
        if not trades:
            return

        rows = [
            (
                run_id,
                trade.symbol,
                trade.side,  # Literal, not Enum
                float(trade.quantity),
                float(trade.price),
                float(trade.amount),
                trade.timestamp.isoformat(),
                trade.reason,
            )
            for trade in trades
        ]

        with self.db.connect() as conn:
            conn.executemany(
                """
                INSERT INTO backtest_trades
                (run_id, symbol, side, quantity, price, amount, timestamp, reason)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )

    def get_run(self, run_id: str) -> Optional[dict]:
        """
        Get run metadata.

        Args:
            run_id: The run ID to look up

        Returns:
            Dict with run metadata or None if not found
        """
        with self.db.connect() as conn:
            cursor = conn.execute(
                """
                SELECT id, strategy_name, config_json, start_date, end_date, initial_cash, created_at
                FROM backtest_runs
                WHERE id = ?
                """,
                (run_id,),
            )
            row = cursor.fetchone()

        if row is None:
            return None

        return {
            "id": row["id"],
            "strategy_name": row["strategy_name"],
            "config": json.loads(row["config_json"]),
            "start_date": date.fromisoformat(row["start_date"]),
            "end_date": date.fromisoformat(row["end_date"]),
            "initial_cash": Decimal(str(row["initial_cash"])),
            "created_at": datetime.fromisoformat(row["created_at"]),
        }

    def get_results(self, run_id: str) -> Optional[BacktestMetrics]:
        """
        Get results for a run.

        Args:
            run_id: The run ID to look up

        Returns:
            BacktestMetrics or None if not found
        """
        with self.db.connect() as conn:
            cursor = conn.execute(
                """
                SELECT final_value, total_return, cagr, max_drawdown, sharpe_ratio,
                       total_trades, total_invested, holdings_json
                FROM backtest_results
                WHERE run_id = ?
                """,
                (run_id,),
            )
            row = cursor.fetchone()

        if row is None:
            return None

        # Parse holdings JSON
        holdings_raw = json.loads(row["holdings_json"]) if row["holdings_json"] else {}
        holdings = {k: Decimal(v) for k, v in holdings_raw.items()}

        return BacktestMetrics(
            final_value=Decimal(str(row["final_value"])),
            total_return=row["total_return"],
            cagr=row["cagr"],
            max_drawdown=row["max_drawdown"],
            sharpe_ratio=row["sharpe_ratio"],
            total_trades=row["total_trades"],
            total_invested=Decimal(str(row["total_invested"])),
            holdings=holdings,
        )

    def get_trades(self, run_id: str) -> List[Trade]:
        """
        Get all trades for a run.

        Args:
            run_id: The run ID to look up

        Returns:
            List of Trade objects
        """
        with self.db.connect() as conn:
            cursor = conn.execute(
                """
                SELECT symbol, side, quantity, price, amount, timestamp, reason
                FROM backtest_trades
                WHERE run_id = ?
                ORDER BY timestamp
                """,
                (run_id,),
            )
            rows = cursor.fetchall()

        trades = []
        for row in rows:
            trades.append(Trade(
                symbol=row["symbol"],
                side=row["side"],
                quantity=Decimal(str(row["quantity"])),
                price=Decimal(str(row["price"])),
                amount=Decimal(str(row["amount"])),
                timestamp=datetime.fromisoformat(row["timestamp"]),
                reason=row["reason"],
            ))

        return trades

    def list_runs(
        self,
        strategy_name: Optional[str] = None,
        limit: int = 20,
    ) -> List[dict]:
        """
        List recent backtest runs.

        Args:
            strategy_name: Filter by strategy name (optional)
            limit: Maximum number of runs to return

        Returns:
            List of run metadata dicts
        """
        query = """
            SELECT r.id, r.strategy_name, r.start_date, r.end_date,
                   r.initial_cash, r.created_at,
                   res.final_value, res.total_return, res.total_trades
            FROM backtest_runs r
            LEFT JOIN backtest_results res ON r.id = res.run_id
        """
        params: list = []

        if strategy_name:
            query += " WHERE r.strategy_name = ?"
            params.append(strategy_name)

        query += " ORDER BY r.created_at DESC LIMIT ?"
        params.append(limit)

        with self.db.connect() as conn:
            cursor = conn.execute(query, tuple(params))
            rows = cursor.fetchall()

        runs = []
        for row in rows:
            run = {
                "id": row["id"],
                "strategy_name": row["strategy_name"],
                "start_date": date.fromisoformat(row["start_date"]),
                "end_date": date.fromisoformat(row["end_date"]),
                "initial_cash": Decimal(str(row["initial_cash"])),
                "created_at": datetime.fromisoformat(row["created_at"]),
            }
            # Add results if available
            if row["final_value"] is not None:
                run["final_value"] = Decimal(str(row["final_value"]))
                run["total_return"] = row["total_return"]
                run["total_trades"] = row["total_trades"]

            runs.append(run)

        return runs

    def delete_run(self, run_id: str) -> bool:
        """
        Delete a backtest run and all associated data.

        Args:
            run_id: The run ID to delete

        Returns:
            True if run was deleted, False if not found
        """
        with self.db.connect() as conn:
            # Delete trades first (foreign key)
            conn.execute("DELETE FROM backtest_trades WHERE run_id = ?", (run_id,))
            # Delete results
            conn.execute("DELETE FROM backtest_results WHERE run_id = ?", (run_id,))
            # Delete run
            cursor = conn.execute("DELETE FROM backtest_runs WHERE id = ?", (run_id,))
            return cursor.rowcount > 0
