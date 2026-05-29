"""Tests for Reddit data models."""

from datetime import datetime

from beavr.reddit.models import (
    MemeStockTrend,
    RedditPost,
    RedditScanResult,
    TickerMention,
)


class TestRedditPost:
    """Tests for RedditPost model."""

    def test_basic_construction(self) -> None:
        post = RedditPost(
            post_id="abc123",
            subreddit="wallstreetbets",
            title="GME to the moon!",
            selftext="Diamond hands!",
            score=1500,
            num_comments=300,
            created_utc=1700000000.0,
        )
        assert post.post_id == "abc123"
        assert post.subreddit == "wallstreetbets"
        assert post.score == 1500

    def test_full_text_combines_title_and_body(self) -> None:
        post = RedditPost(
            post_id="x",
            subreddit="stocks",
            title="Buy GME",
            selftext="It's going up",
            created_utc=1700000000.0,
        )
        assert "Buy GME" in post.full_text
        assert "It's going up" in post.full_text

    def test_full_text_with_empty_body(self) -> None:
        post = RedditPost(
            post_id="x",
            subreddit="stocks",
            title="Link post",
            created_utc=1700000000.0,
        )
        assert post.full_text == "Link post"

    def test_created_datetime(self) -> None:
        post = RedditPost(
            post_id="x",
            subreddit="stocks",
            title="Test",
            created_utc=1700000000.0,
        )
        dt = post.created_datetime
        assert isinstance(dt, datetime)

    def test_frozen_model(self) -> None:
        post = RedditPost(
            post_id="x",
            subreddit="stocks",
            title="Test",
            created_utc=1700000000.0,
        )
        try:
            post.title = "Changed"  # type: ignore[misc]
            raise AssertionError("Should be frozen")
        except Exception:
            pass


class TestTickerMention:
    """Tests for TickerMention model."""

    def test_basic_construction(self) -> None:
        mention = TickerMention(
            ticker="GME",
            subreddit="wallstreetbets",
            post_id="abc",
            post_title="GME squeeze!",
            sentiment=0.7,
            post_score=500,
        )
        assert mention.ticker == "GME"
        assert mention.sentiment == 0.7

    def test_sentiment_bounds(self) -> None:
        mention = TickerMention(
            ticker="AMC",
            subreddit="wallstreetbets",
            post_id="x",
            sentiment=1.0,
        )
        assert mention.sentiment == 1.0

        mention_neg = TickerMention(
            ticker="AMC",
            subreddit="wallstreetbets",
            post_id="x",
            sentiment=-1.0,
        )
        assert mention_neg.sentiment == -1.0


class TestMemeStockTrend:
    """Tests for MemeStockTrend model."""

    def test_sentiment_label_bullish(self) -> None:
        trend = MemeStockTrend(ticker="GME", avg_sentiment=0.5)
        assert trend.sentiment_label == "Bullish"

    def test_sentiment_label_slightly_bullish(self) -> None:
        trend = MemeStockTrend(ticker="GME", avg_sentiment=0.2)
        assert trend.sentiment_label == "Slightly Bullish"

    def test_sentiment_label_neutral(self) -> None:
        trend = MemeStockTrend(ticker="GME", avg_sentiment=0.0)
        assert trend.sentiment_label == "Neutral"

    def test_sentiment_label_slightly_bearish(self) -> None:
        trend = MemeStockTrend(ticker="GME", avg_sentiment=-0.2)
        assert trend.sentiment_label == "Slightly Bearish"

    def test_sentiment_label_bearish(self) -> None:
        trend = MemeStockTrend(ticker="GME", avg_sentiment=-0.5)
        assert trend.sentiment_label == "Bearish"


class TestRedditScanResult:
    """Tests for RedditScanResult model."""

    def test_ticker_count(self) -> None:
        result = RedditScanResult(
            scan_id="scan-1",
            subreddits=["wallstreetbets"],
            post_count=100,
            trends=[
                MemeStockTrend(ticker="GME", mention_count=10),
                MemeStockTrend(ticker="AMC", mention_count=5),
            ],
        )
        assert result.ticker_count == 2

    def test_empty_result(self) -> None:
        result = RedditScanResult(
            scan_id="scan-1",
            subreddits=[],
            post_count=0,
        )
        assert result.ticker_count == 0
        assert result.trends == []
