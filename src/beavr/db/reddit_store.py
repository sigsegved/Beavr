"""Database storage for Reddit scan results."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

from beavr.db.connection import Database
from beavr.reddit.models import MemeStockTrend, RedditScanResult, TickerMention


class RedditStore:
    """Stores and retrieves Reddit scan results from SQLite.

    Attributes:
        db: Database connection manager
    """

    def __init__(self, db: Database) -> None:
        """Initialize the store.

        Args:
            db: Database instance
        """
        self.db = db

    def save_scan(self, result: RedditScanResult) -> None:
        """Save a scan result to the database.

        Args:
            result: Scan result to persist
        """
        with self.db.connect() as conn:
            # Save scan metadata
            conn.execute(
                """INSERT INTO reddit_scans (id, subreddits, post_count, ticker_count, scanned_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    result.scan_id,
                    json.dumps(result.subreddits),
                    result.post_count,
                    result.ticker_count,
                    result.scanned_at.isoformat(),
                ),
            )

            # Save mentions
            for mention in result.mentions:
                conn.execute(
                    """INSERT INTO reddit_mentions
                       (scan_id, ticker, subreddit, post_title, sentiment,
                        post_score, post_comments, post_created_utc)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        result.scan_id,
                        mention.ticker,
                        mention.subreddit,
                        mention.post_title,
                        mention.sentiment,
                        mention.post_score,
                        mention.post_comments,
                        mention.post_created_utc,
                    ),
                )

            # Save trends
            for trend in result.trends:
                conn.execute(
                    """INSERT INTO reddit_trends
                       (scan_id, ticker, mention_count, avg_sentiment,
                        total_score, total_comments, trending_score, rank)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        result.scan_id,
                        trend.ticker,
                        trend.mention_count,
                        trend.avg_sentiment,
                        trend.total_post_score,
                        trend.total_comments,
                        trend.trending_score,
                        trend.rank,
                    ),
                )

    def get_latest_scan(self) -> Optional[RedditScanResult]:
        """Get the most recent scan result.

        Returns:
            Latest scan result or None if no scans exist
        """
        with self.db.connect() as conn:
            cursor = conn.execute(
                "SELECT id, subreddits, post_count, ticker_count, scanned_at "
                "FROM reddit_scans ORDER BY scanned_at DESC LIMIT 1"
            )
            row = cursor.fetchone()
            if not row:
                return None

            return self._load_scan(conn, row)

    def get_scan_history(self, limit: int = 10) -> list[dict[str, object]]:
        """Get summary of past scans.

        Args:
            limit: Maximum number of scans to return

        Returns:
            List of scan summaries
        """
        with self.db.connect() as conn:
            cursor = conn.execute(
                "SELECT id, subreddits, post_count, ticker_count, scanned_at "
                "FROM reddit_scans ORDER BY scanned_at DESC LIMIT ?",
                (limit,),
            )
            rows = cursor.fetchall()
            return [
                {
                    "scan_id": row["id"],
                    "subreddits": json.loads(row["subreddits"]),
                    "post_count": row["post_count"],
                    "ticker_count": row["ticker_count"],
                    "scanned_at": row["scanned_at"],
                }
                for row in rows
            ]

    def get_ticker_history(self, ticker: str, limit: int = 10) -> list[dict[str, object]]:
        """Get trend history for a specific ticker across scans.

        Args:
            ticker: Stock ticker symbol
            limit: Maximum number of entries

        Returns:
            List of trend entries for the ticker
        """
        with self.db.connect() as conn:
            cursor = conn.execute(
                """SELECT t.ticker, t.mention_count, t.avg_sentiment,
                          t.total_score, t.total_comments, t.trending_score,
                          t.rank, s.scanned_at
                   FROM reddit_trends t
                   JOIN reddit_scans s ON t.scan_id = s.id
                   WHERE t.ticker = ?
                   ORDER BY s.scanned_at DESC LIMIT ?""",
                (ticker.upper(), limit),
            )
            return [
                {
                    "ticker": row["ticker"],
                    "mention_count": row["mention_count"],
                    "avg_sentiment": row["avg_sentiment"],
                    "total_score": row["total_score"],
                    "total_comments": row["total_comments"],
                    "trending_score": row["trending_score"],
                    "rank": row["rank"],
                    "scanned_at": row["scanned_at"],
                }
                for row in cursor.fetchall()
            ]

    def _load_scan(self, conn: object, row: object) -> RedditScanResult:
        """Load a full scan result from database rows.

        Args:
            conn: Active database connection
            row: Scan metadata row

        Returns:
            Complete RedditScanResult
        """
        import sqlite3

        assert isinstance(conn, sqlite3.Connection)
        assert isinstance(row, sqlite3.Row)

        scan_id = row["id"]

        # Load trends
        trend_cursor = conn.execute(
            """SELECT ticker, mention_count, avg_sentiment, total_score,
                      total_comments, trending_score, rank
               FROM reddit_trends WHERE scan_id = ? ORDER BY rank""",
            (scan_id,),
        )
        trends = [
            MemeStockTrend(
                ticker=t["ticker"],
                mention_count=t["mention_count"],
                avg_sentiment=t["avg_sentiment"] or 0.0,
                total_post_score=t["total_score"] or 0,
                total_comments=t["total_comments"] or 0,
                trending_score=t["trending_score"] or 0.0,
                rank=t["rank"] or 0,
            )
            for t in trend_cursor.fetchall()
        ]

        # Load mentions
        mention_cursor = conn.execute(
            """SELECT ticker, subreddit, post_title, sentiment,
                      post_score, post_comments, post_created_utc
               FROM reddit_mentions WHERE scan_id = ?""",
            (scan_id,),
        )
        mentions = [
            TickerMention(
                ticker=m["ticker"],
                subreddit=m["subreddit"],
                post_id="",
                post_title=m["post_title"] or "",
                sentiment=m["sentiment"] or 0.0,
                post_score=m["post_score"] or 0,
                post_comments=m["post_comments"] or 0,
                post_created_utc=m["post_created_utc"] or 0.0,
            )
            for m in mention_cursor.fetchall()
        ]

        scanned_at_str = row["scanned_at"]
        try:
            scanned_at = datetime.fromisoformat(scanned_at_str)
        except (ValueError, TypeError):
            scanned_at = datetime.utcnow()

        return RedditScanResult(
            scan_id=scan_id,
            subreddits=json.loads(row["subreddits"]),
            post_count=row["post_count"],
            trends=trends,
            scanned_at=scanned_at,
            mentions=mentions,
        )
