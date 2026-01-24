"""Bar data caching repository."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING, Optional, Tuple

import pandas as pd

if TYPE_CHECKING:
    from beavr.db.connection import Database


class BarCache:
    """
    Repository for caching OHLCV bar data.

    Provides methods to save and retrieve bar data from the SQLite database.
    Data is stored with symbol, timestamp, and timeframe as the unique key.

    Attributes:
        db: Database connection manager
    """

    def __init__(self, db: Database):
        """
        Initialize the bar cache.

        Args:
            db: Database connection manager
        """
        self.db = db

    def get_bars(
        self,
        symbol: str,
        start: date,
        end: date,
        timeframe: str = "1Day",
    ) -> Optional[pd.DataFrame]:
        """
        Retrieve cached bars for symbol/date range.

        Returns None if data not fully cached for the range.
        Returns DataFrame with columns: timestamp, open, high, low, close, volume

        Args:
            symbol: Stock symbol (e.g., "SPY")
            start: Start date (inclusive)
            end: End date (inclusive)
            timeframe: Bar timeframe (default "1Day")

        Returns:
            DataFrame with bar data or None if not fully cached
        """
        # Check if we have complete data for the range
        if not self.has_data(symbol, start, end, timeframe):
            return None

        with self.db.connect() as conn:
            cursor = conn.execute(
                """
                SELECT timestamp, open, high, low, close, volume
                FROM bars
                WHERE symbol = ? AND timeframe = ?
                    AND date(timestamp) >= ? AND date(timestamp) <= ?
                ORDER BY timestamp
                """,
                (symbol, timeframe, start.isoformat(), end.isoformat()),
            )
            rows = cursor.fetchall()

        if not rows:
            return None

        # Convert to DataFrame
        data = {
            "timestamp": [row["timestamp"] for row in rows],
            "open": [Decimal(str(row["open"])) for row in rows],
            "high": [Decimal(str(row["high"])) for row in rows],
            "low": [Decimal(str(row["low"])) for row in rows],
            "close": [Decimal(str(row["close"])) for row in rows],
            "volume": [int(row["volume"]) for row in rows],
        }

        df = pd.DataFrame(data)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        return df

    def save_bars(
        self,
        symbol: str,
        bars: pd.DataFrame,
        timeframe: str = "1Day",
    ) -> None:
        """
        Save bars to cache.

        Uses UPSERT to handle duplicate inserts gracefully.

        Args:
            symbol: Stock symbol (e.g., "SPY")
            bars: DataFrame with columns: timestamp, open, high, low, close, volume
            timeframe: Bar timeframe (default "1Day")
        """
        if bars.empty:
            return

        # Validate required columns
        required_cols = {"timestamp", "open", "high", "low", "close", "volume"}
        if not required_cols.issubset(bars.columns):
            missing = required_cols - set(bars.columns)
            raise ValueError(f"Missing required columns: {missing}")

        # Prepare data for insertion
        rows = []
        for _, row in bars.iterrows():
            # Handle timestamp conversion
            timestamp = row["timestamp"]
            if hasattr(timestamp, "isoformat"):
                timestamp_str = timestamp.isoformat()
            else:
                timestamp_str = str(timestamp)

            rows.append((
                symbol,
                timestamp_str,
                float(row["open"]),
                float(row["high"]),
                float(row["low"]),
                float(row["close"]),
                int(row["volume"]),
                timeframe,
            ))

        with self.db.connect() as conn:
            conn.executemany(
                """
                INSERT INTO bars (symbol, timestamp, open, high, low, close, volume, timeframe)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol, timestamp, timeframe) DO UPDATE SET
                    open = excluded.open,
                    high = excluded.high,
                    low = excluded.low,
                    close = excluded.close,
                    volume = excluded.volume
                """,
                rows,
            )

    def has_data(
        self,
        symbol: str,
        start: date,
        end: date,
        timeframe: str = "1Day",
    ) -> bool:
        """
        Check if we have complete data for date range.

        Checks if we have data covering from start to end dates.
        Returns False if the cached data doesn't cover the full range.

        Args:
            symbol: Stock symbol (e.g., "SPY")
            start: Start date (inclusive)
            end: End date (inclusive)
            timeframe: Bar timeframe (default "1Day")

        Returns:
            True if data exists for the full range, False otherwise
        """
        with self.db.connect() as conn:
            # Get the min and max dates we have cached for this symbol
            cursor = conn.execute(
                """
                SELECT MIN(date(timestamp)) as min_date, MAX(date(timestamp)) as max_date
                FROM bars
                WHERE symbol = ? AND timeframe = ?
                """,
                (symbol, timeframe),
            )
            result = cursor.fetchone()
            
            if not result or not result["min_date"] or not result["max_date"]:
                return False
            
            # Parse the cached date range
            cached_start = date.fromisoformat(result["min_date"])
            cached_end = date.fromisoformat(result["max_date"])
            
            # Check if our cached range covers the requested range
            return cached_start <= start and cached_end >= end

    def get_date_range(
        self,
        symbol: str,
        timeframe: str = "1Day",
    ) -> Optional[Tuple[date, date]]:
        """
        Get the date range we have cached for a symbol.

        Args:
            symbol: Stock symbol (e.g., "SPY")
            timeframe: Bar timeframe (default "1Day")

        Returns:
            Tuple of (min_date, max_date) or None if no data cached
        """
        with self.db.connect() as conn:
            cursor = conn.execute(
                """
                SELECT
                    MIN(date(timestamp)) as min_date,
                    MAX(date(timestamp)) as max_date
                FROM bars
                WHERE symbol = ? AND timeframe = ?
                """,
                (symbol, timeframe),
            )
            result = cursor.fetchone()

        if result is None or result["min_date"] is None:
            return None

        return (
            date.fromisoformat(result["min_date"]),
            date.fromisoformat(result["max_date"]),
        )

    def delete_bars(
        self,
        symbol: str,
        timeframe: str = "1Day",
    ) -> int:
        """
        Delete all cached bars for a symbol.

        Args:
            symbol: Stock symbol (e.g., "SPY")
            timeframe: Bar timeframe (default "1Day")

        Returns:
            Number of rows deleted
        """
        with self.db.connect() as conn:
            cursor = conn.execute(
                "DELETE FROM bars WHERE symbol = ? AND timeframe = ?",
                (symbol, timeframe),
            )
            return cursor.rowcount

    def get_symbols(self) -> list[str]:
        """
        Get list of all symbols with cached data.

        Returns:
            List of unique symbol names
        """
        with self.db.connect() as conn:
            cursor = conn.execute("SELECT DISTINCT symbol FROM bars ORDER BY symbol")
            rows = cursor.fetchall()
        return [row["symbol"] for row in rows]
