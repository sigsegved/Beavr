"""Tests for Reddit post analyzer."""

from beavr.reddit.analyzer import RedditAnalyzer
from beavr.reddit.models import RedditPost, TickerMention


class TestTickerExtraction:
    """Tests for ticker extraction from text."""

    def setup_method(self) -> None:
        self.analyzer = RedditAnalyzer(min_mentions=1)

    def test_dollar_sign_ticker(self) -> None:
        tickers = self.analyzer.extract_tickers("I'm buying $GME today")
        assert "GME" in tickers

    def test_uppercase_known_ticker(self) -> None:
        tickers = self.analyzer.extract_tickers("GME is going to the moon")
        assert "GME" in tickers

    def test_multiple_tickers(self) -> None:
        tickers = self.analyzer.extract_tickers("$GME and $AMC are squeezing")
        assert "GME" in tickers
        assert "AMC" in tickers

    def test_deduplication(self) -> None:
        tickers = self.analyzer.extract_tickers("$GME GME $GME more GME")
        assert tickers.count("GME") == 1

    def test_false_positive_filtering(self) -> None:
        tickers = self.analyzer.extract_tickers("I AM THE CEO OF IPO")
        assert len(tickers) == 0

    def test_unknown_ticker_ignored(self) -> None:
        tickers = self.analyzer.extract_tickers("$ZZZZZ is unknown")
        assert "ZZZZZ" not in tickers

    def test_common_words_not_tickers(self) -> None:
        tickers = self.analyzer.extract_tickers("THE BEST BUY IS TO SELL NOW")
        assert len(tickers) == 0

    def test_mixed_case_ignored(self) -> None:
        """Only uppercase words are considered as ticker candidates."""
        tickers = self.analyzer.extract_tickers("gme is great")
        assert "GME" not in tickers
        assert "gme" not in tickers

    def test_known_mega_cap(self) -> None:
        tickers = self.analyzer.extract_tickers("AAPL and MSFT are solid picks")
        assert "AAPL" in tickers
        assert "MSFT" in tickers

    def test_etf_tickers(self) -> None:
        tickers = self.analyzer.extract_tickers("Buy SPY and QQQ for diversity")
        assert "SPY" in tickers
        assert "QQQ" in tickers


class TestSentimentScoring:
    """Tests for sentiment analysis."""

    def setup_method(self) -> None:
        self.analyzer = RedditAnalyzer()

    def test_bullish_text(self) -> None:
        score = self.analyzer.score_sentiment("GME to the moon rocket diamond hands")
        assert score > 0

    def test_bearish_text(self) -> None:
        score = self.analyzer.score_sentiment("crash dump sell puts short bear")
        assert score < 0

    def test_neutral_text(self) -> None:
        score = self.analyzer.score_sentiment("this is a regular sentence")
        assert score == 0.0

    def test_mixed_sentiment(self) -> None:
        score = self.analyzer.score_sentiment("buy the dip but also puts on crash")
        # Mixed should be close to 0
        assert -0.5 <= score <= 0.5

    def test_score_range(self) -> None:
        score_bull = self.analyzer.score_sentiment("moon rocket diamond hands buy long bull")
        score_bear = self.analyzer.score_sentiment("crash dump sell puts short bear bearish")
        assert -1.0 <= score_bull <= 1.0
        assert -1.0 <= score_bear <= 1.0


class TestPostAnalysis:
    """Tests for full post analysis."""

    def setup_method(self) -> None:
        self.analyzer = RedditAnalyzer(min_mentions=1)

    def _make_post(
        self,
        title: str,
        selftext: str = "",
        subreddit: str = "wallstreetbets",
        score: int = 100,
    ) -> RedditPost:
        return RedditPost(
            post_id="test",
            subreddit=subreddit,
            title=title,
            selftext=selftext,
            score=score,
            num_comments=50,
            created_utc=1700000000.0,
        )

    def test_analyze_post_with_ticker(self) -> None:
        post = self._make_post("$GME diamond hands to the moon!")
        mentions = self.analyzer.analyze_post(post)
        assert len(mentions) >= 1
        assert mentions[0].ticker == "GME"
        assert mentions[0].sentiment > 0

    def test_analyze_post_without_ticker(self) -> None:
        post = self._make_post("Just a random discussion about nothing")
        mentions = self.analyzer.analyze_post(post)
        assert len(mentions) == 0

    def test_analyze_post_preserves_metadata(self) -> None:
        post = self._make_post("$TSLA is amazing", subreddit="stocks", score=500)
        mentions = self.analyzer.analyze_post(post)
        assert len(mentions) == 1
        assert mentions[0].subreddit == "stocks"
        assert mentions[0].post_score == 500

    def test_analyze_multiple_posts(self) -> None:
        posts = [
            self._make_post("$GME squeeze!"),
            self._make_post("$AMC to the moon!"),
            self._make_post("Regular discussion"),
        ]
        mentions = self.analyzer.analyze_posts(posts)
        tickers = {m.ticker for m in mentions}
        assert "GME" in tickers
        assert "AMC" in tickers


class TestTrendAggregation:
    """Tests for trend aggregation."""

    def setup_method(self) -> None:
        self.analyzer = RedditAnalyzer(min_mentions=2)

    def test_aggregate_filters_low_mentions(self) -> None:
        mentions = [
            TickerMention(ticker="GME", subreddit="wsb", post_id="1", sentiment=0.5, post_score=100, post_comments=10),
        ]
        trends = self.analyzer.aggregate_trends(mentions)
        assert len(trends) == 0  # Only 1 mention, min is 2

    def test_aggregate_groups_by_ticker(self) -> None:
        mentions = [
            TickerMention(ticker="GME", subreddit="wsb", post_id="1", sentiment=0.5, post_score=100, post_comments=10),
            TickerMention(ticker="GME", subreddit="wsb", post_id="2", sentiment=0.3, post_score=200, post_comments=20),
            TickerMention(ticker="AMC", subreddit="wsb", post_id="3", sentiment=-0.2, post_score=50, post_comments=5),
            TickerMention(ticker="AMC", subreddit="stocks", post_id="4", sentiment=0.1, post_score=30, post_comments=3),
        ]
        trends = self.analyzer.aggregate_trends(mentions)
        assert len(trends) == 2

        gme_trend = next(t for t in trends if t.ticker == "GME")
        assert gme_trend.mention_count == 2
        assert gme_trend.total_post_score == 300

        amc_trend = next(t for t in trends if t.ticker == "AMC")
        assert amc_trend.mention_count == 2

    def test_trends_ranked_by_score(self) -> None:
        mentions = [
            TickerMention(ticker="GME", subreddit="wsb", post_id="1", sentiment=0.5, post_score=1000, post_comments=100),
            TickerMention(ticker="GME", subreddit="wsb", post_id="2", sentiment=0.5, post_score=1000, post_comments=100),
            TickerMention(ticker="GME", subreddit="wsb", post_id="3", sentiment=0.5, post_score=1000, post_comments=100),
            TickerMention(ticker="AMC", subreddit="wsb", post_id="4", sentiment=0.1, post_score=10, post_comments=1),
            TickerMention(ticker="AMC", subreddit="wsb", post_id="5", sentiment=0.1, post_score=10, post_comments=1),
        ]
        trends = self.analyzer.aggregate_trends(mentions)
        assert trends[0].ticker == "GME"
        assert trends[0].rank == 1
        assert trends[1].rank == 2

    def test_subreddit_breakdown(self) -> None:
        mentions = [
            TickerMention(ticker="GME", subreddit="wallstreetbets", post_id="1", sentiment=0.5),
            TickerMention(ticker="GME", subreddit="stocks", post_id="2", sentiment=0.3),
            TickerMention(ticker="GME", subreddit="wallstreetbets", post_id="3", sentiment=0.4),
        ]
        analyzer = RedditAnalyzer(min_mentions=1)
        trends = analyzer.aggregate_trends(mentions)
        assert trends[0].subreddit_breakdown["wallstreetbets"] == 2
        assert trends[0].subreddit_breakdown["stocks"] == 1


class TestFullScan:
    """Tests for full scan workflow."""

    def test_scan_produces_result(self) -> None:
        analyzer = RedditAnalyzer(min_mentions=1)
        posts = [
            RedditPost(
                post_id="1",
                subreddit="wallstreetbets",
                title="$GME diamond hands moon rocket",
                created_utc=1700000000.0,
                score=500,
                num_comments=100,
            ),
            RedditPost(
                post_id="2",
                subreddit="wallstreetbets",
                title="$GME still holding! Buy the dip!",
                created_utc=1700000100.0,
                score=300,
                num_comments=50,
            ),
        ]

        result = analyzer.scan(posts, subreddits=["wallstreetbets"])
        assert result.post_count == 2
        assert result.ticker_count >= 1
        assert len(result.mentions) >= 1
        assert result.scan_id != ""

    def test_scan_empty_posts(self) -> None:
        analyzer = RedditAnalyzer()
        result = analyzer.scan([], subreddits=["wallstreetbets"])
        assert result.post_count == 0
        assert result.ticker_count == 0
