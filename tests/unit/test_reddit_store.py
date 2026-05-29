"""Tests for Reddit database store."""

from datetime import datetime

import pytest

from beavr.db.connection import Database
from beavr.db.reddit_store import RedditStore
from beavr.reddit.models import MemeStockTrend, RedditScanResult, TickerMention


class TestRedditStore:
    """Tests for RedditStore persistence."""

    @pytest.fixture
    def db(self) -> Database:
        return Database(":memory:")

    @pytest.fixture
    def store(self, db: Database) -> RedditStore:
        return RedditStore(db)

    def _make_scan_result(self, scan_id: str = "test-scan-1") -> RedditScanResult:
        return RedditScanResult(
            scan_id=scan_id,
            subreddits=["wallstreetbets", "stocks"],
            post_count=50,
            trends=[
                MemeStockTrend(
                    ticker="GME",
                    mention_count=10,
                    avg_sentiment=0.5,
                    total_post_score=500,
                    total_comments=100,
                    subreddit_breakdown={"wallstreetbets": 8, "stocks": 2},
                    trending_score=115.0,
                    rank=1,
                ),
                MemeStockTrend(
                    ticker="AMC",
                    mention_count=5,
                    avg_sentiment=-0.1,
                    total_post_score=200,
                    total_comments=30,
                    subreddit_breakdown={"wallstreetbets": 5},
                    trending_score=60.0,
                    rank=2,
                ),
            ],
            scanned_at=datetime(2024, 1, 15, 12, 0, 0),
            mentions=[
                TickerMention(
                    ticker="GME",
                    subreddit="wallstreetbets",
                    post_id="p1",
                    post_title="GME squeeze!",
                    sentiment=0.7,
                    post_score=200,
                    post_comments=50,
                    post_created_utc=1700000000.0,
                ),
                TickerMention(
                    ticker="AMC",
                    subreddit="wallstreetbets",
                    post_id="p2",
                    post_title="AMC discussion",
                    sentiment=-0.1,
                    post_score=100,
                    post_comments=20,
                    post_created_utc=1700000100.0,
                ),
            ],
        )

    def test_save_and_retrieve_scan(self, store: RedditStore) -> None:
        result = self._make_scan_result()
        store.save_scan(result)

        latest = store.get_latest_scan()
        assert latest is not None
        assert latest.scan_id == "test-scan-1"
        assert latest.post_count == 50
        assert len(latest.trends) == 2
        assert latest.trends[0].ticker == "GME"
        assert latest.trends[0].rank == 1
        assert latest.trends[1].ticker == "AMC"

    def test_get_latest_scan_empty(self, store: RedditStore) -> None:
        latest = store.get_latest_scan()
        assert latest is None

    def test_scan_history(self, store: RedditStore) -> None:
        store.save_scan(self._make_scan_result("scan-1"))
        store.save_scan(self._make_scan_result("scan-2"))

        history = store.get_scan_history(limit=5)
        assert len(history) == 2

    def test_ticker_history(self, store: RedditStore) -> None:
        store.save_scan(self._make_scan_result("scan-1"))

        history = store.get_ticker_history("GME", limit=5)
        assert len(history) == 1
        assert history[0]["ticker"] == "GME"
        assert history[0]["mention_count"] == 10

    def test_ticker_history_not_found(self, store: RedditStore) -> None:
        store.save_scan(self._make_scan_result())
        history = store.get_ticker_history("ZZZZZ", limit=5)
        assert len(history) == 0

    def test_mentions_persisted(self, store: RedditStore) -> None:
        result = self._make_scan_result()
        store.save_scan(result)

        latest = store.get_latest_scan()
        assert latest is not None
        assert len(latest.mentions) == 2
        gme_mentions = [m for m in latest.mentions if m.ticker == "GME"]
        assert len(gme_mentions) == 1
        assert gme_mentions[0].sentiment == 0.7
