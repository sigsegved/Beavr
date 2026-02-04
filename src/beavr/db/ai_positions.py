"""AI Investor positions repository."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, List, Optional

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from beavr.db.connection import Database


class AIPosition(BaseModel):
    """An AI investor position with stop/target tracking."""

    id: Optional[int] = None
    symbol: str
    quantity: Decimal
    entry_price: Decimal
    entry_amount: Decimal
    stop_loss_pct: float
    target_pct: float
    strategy: Optional[str] = None
    rationale: Optional[str] = None
    status: str = "open"  # open, closed_target, closed_stop, closed_manual
    entry_timestamp: datetime
    exit_timestamp: Optional[datetime] = None
    exit_price: Optional[Decimal] = None
    exit_reason: Optional[str] = None
    pnl: Optional[Decimal] = None
    pnl_pct: Optional[float] = None

    model_config = {"frozen": False}

    @property
    def stop_price(self) -> Decimal:
        """Calculate stop loss price."""
        return self.entry_price * (1 - Decimal(str(self.stop_loss_pct)) / 100)

    @property
    def target_price(self) -> Decimal:
        """Calculate profit target price."""
        return self.entry_price * (1 + Decimal(str(self.target_pct)) / 100)


class AITrade(BaseModel):
    """An AI investor trade execution."""

    id: Optional[int] = None
    position_id: Optional[int] = None
    symbol: str
    side: str  # BUY or SELL
    quantity: Decimal
    price: Decimal
    amount: Decimal
    timestamp: datetime
    reason: Optional[str] = None

    model_config = {"frozen": True}


class AIPositionsRepository:
    """
    Repository for AI investor positions and trades.

    Tracks positions with stop/target levels and integrates
    with the main portfolio tracking system.
    """

    def __init__(self, db: "Database") -> None:
        """Initialize the repository."""
        self.db = db

    def open_position(
        self,
        symbol: str,
        quantity: Decimal,
        entry_price: Decimal,
        stop_loss_pct: float,
        target_pct: float,
        strategy: Optional[str] = None,
        rationale: Optional[str] = None,
    ) -> int:
        """
        Open a new AI position.

        Args:
            symbol: Stock symbol
            quantity: Number of shares
            entry_price: Entry price per share
            stop_loss_pct: Stop loss percentage (e.g., 5.0 for 5%)
            target_pct: Profit target percentage
            strategy: Trading strategy name
            rationale: AI reasoning for the trade

        Returns:
            Position ID
        """
        entry_amount = quantity * entry_price
        now = datetime.now()

        with self.db.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO ai_positions
                (symbol, quantity, entry_price, entry_amount, stop_loss_pct, target_pct,
                 strategy, rationale, status, entry_timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'open', ?)
                """,
                (
                    symbol,
                    float(quantity),
                    float(entry_price),
                    float(entry_amount),
                    stop_loss_pct,
                    target_pct,
                    strategy,
                    rationale,
                    now.isoformat(),
                ),
            )
            position_id = cursor.lastrowid

            # Record the entry trade
            conn.execute(
                """
                INSERT INTO ai_trades
                (position_id, symbol, side, quantity, price, amount, timestamp, reason)
                VALUES (?, ?, 'BUY', ?, ?, ?, ?, ?)
                """,
                (
                    position_id,
                    symbol,
                    float(quantity),
                    float(entry_price),
                    float(entry_amount),
                    now.isoformat(),
                    rationale,
                ),
            )

        return position_id

    def close_position(
        self,
        position_id: int,
        exit_price: Decimal,
        reason: str,
    ) -> Optional[AIPosition]:
        """
        Close an existing position.

        Args:
            position_id: The position ID to close
            exit_price: Exit price per share
            reason: Exit reason (target, stop, manual)

        Returns:
            The closed position or None if not found
        """
        position = self.get_position(position_id)
        if not position or position.status != "open":
            return None

        now = datetime.now()
        exit_amount = position.quantity * exit_price
        pnl = exit_amount - position.entry_amount
        pnl_pct = float(pnl / position.entry_amount * 100)

        # Determine status based on reason
        if "target" in reason.lower():
            status = "closed_target"
        elif "stop" in reason.lower():
            status = "closed_stop"
        else:
            status = "closed_manual"

        with self.db.connect() as conn:
            conn.execute(
                """
                UPDATE ai_positions
                SET status = ?, exit_timestamp = ?, exit_price = ?,
                    exit_reason = ?, pnl = ?, pnl_pct = ?
                WHERE id = ?
                """,
                (
                    status,
                    now.isoformat(),
                    float(exit_price),
                    reason,
                    float(pnl),
                    pnl_pct,
                    position_id,
                ),
            )

            # Record the exit trade
            conn.execute(
                """
                INSERT INTO ai_trades
                (position_id, symbol, side, quantity, price, amount, timestamp, reason)
                VALUES (?, ?, 'SELL', ?, ?, ?, ?, ?)
                """,
                (
                    position_id,
                    position.symbol,
                    float(position.quantity),
                    float(exit_price),
                    float(exit_amount),
                    now.isoformat(),
                    reason,
                ),
            )

        return self.get_position(position_id)

    def close_position_by_symbol(
        self,
        symbol: str,
        exit_price: Decimal,
        reason: str,
    ) -> Optional[AIPosition]:
        """
        Close an open position by symbol.

        Args:
            symbol: Stock symbol
            exit_price: Exit price per share
            reason: Exit reason

        Returns:
            The closed position or None if not found
        """
        position = self.get_open_position(symbol)
        if not position:
            return None
        return self.close_position(position.id, exit_price, reason)

    def get_position(self, position_id: int) -> Optional[AIPosition]:
        """Get a position by ID."""
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM ai_positions WHERE id = ?",
                (position_id,),
            ).fetchone()

        if not row:
            return None

        return self._row_to_position(row)

    def get_open_position(self, symbol: str) -> Optional[AIPosition]:
        """Get an open position for a symbol."""
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM ai_positions WHERE symbol = ? AND status = 'open' LIMIT 1",
                (symbol,),
            ).fetchone()

        if not row:
            return None

        return self._row_to_position(row)

    def get_open_positions(self) -> List[AIPosition]:
        """Get all open positions."""
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM ai_positions WHERE status = 'open' ORDER BY entry_timestamp DESC"
            ).fetchall()

        return [self._row_to_position(row) for row in rows]

    def get_all_positions(self, limit: int = 100) -> List[AIPosition]:
        """Get all positions (open and closed)."""
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM ai_positions ORDER BY entry_timestamp DESC LIMIT ?",
                (limit,),
            ).fetchall()

        return [self._row_to_position(row) for row in rows]

    def get_trades(self, position_id: Optional[int] = None, limit: int = 100) -> List[AITrade]:
        """Get trades, optionally filtered by position."""
        with self.db.connect() as conn:
            if position_id:
                rows = conn.execute(
                    "SELECT * FROM ai_trades WHERE position_id = ? ORDER BY timestamp DESC",
                    (position_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM ai_trades ORDER BY timestamp DESC LIMIT ?",
                    (limit,),
                ).fetchall()

        return [self._row_to_trade(row) for row in rows]

    def get_performance_summary(self) -> dict:
        """Get performance summary for all AI trading."""
        with self.db.connect() as conn:
            # Total stats
            total_stats = conn.execute(
                """
                SELECT
                    COUNT(*) as total_trades,
                    SUM(CASE WHEN status LIKE 'closed_%' THEN 1 ELSE 0 END) as closed_trades,
                    SUM(CASE WHEN status = 'open' THEN 1 ELSE 0 END) as open_trades,
                    SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as winning_trades,
                    SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END) as losing_trades,
                    SUM(COALESCE(pnl, 0)) as total_pnl,
                    AVG(CASE WHEN status LIKE 'closed_%' THEN pnl_pct ELSE NULL END) as avg_pnl_pct
                FROM ai_positions
                """
            ).fetchone()

        return {
            "total_positions": total_stats[0] or 0,
            "closed_positions": total_stats[1] or 0,
            "open_positions": total_stats[2] or 0,
            "winning_trades": total_stats[3] or 0,
            "losing_trades": total_stats[4] or 0,
            "total_pnl": Decimal(str(total_stats[5] or 0)),
            "avg_pnl_pct": total_stats[6] or 0.0,
            "win_rate": (total_stats[3] or 0) / max(total_stats[1] or 1, 1) * 100,
        }

    def _row_to_position(self, row) -> AIPosition:
        """Convert a database row to an AIPosition."""
        return AIPosition(
            id=row[0],
            symbol=row[1],
            quantity=Decimal(str(row[2])),
            entry_price=Decimal(str(row[3])),
            entry_amount=Decimal(str(row[4])),
            stop_loss_pct=row[5],
            target_pct=row[6],
            strategy=row[7],
            rationale=row[8],
            status=row[9],
            entry_timestamp=datetime.fromisoformat(row[10]),
            exit_timestamp=datetime.fromisoformat(row[11]) if row[11] else None,
            exit_price=Decimal(str(row[12])) if row[12] else None,
            exit_reason=row[13],
            pnl=Decimal(str(row[14])) if row[14] else None,
            pnl_pct=row[15],
        )

    def _row_to_trade(self, row) -> AITrade:
        """Convert a database row to an AITrade."""
        return AITrade(
            id=row[0],
            position_id=row[1],
            symbol=row[2],
            side=row[3],
            quantity=Decimal(str(row[4])),
            price=Decimal(str(row[5])),
            amount=Decimal(str(row[6])),
            timestamp=datetime.fromisoformat(row[7]),
            reason=row[8],
        )
