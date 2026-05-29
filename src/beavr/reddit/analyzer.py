"""Ticker extraction and sentiment analysis for Reddit posts."""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime
from typing import Optional
from uuid import uuid4

from beavr.reddit.models import MemeStockTrend, RedditPost, RedditScanResult, TickerMention

# Common words that look like tickers but aren't
FALSE_POSITIVE_TICKERS = frozenset({
    # Pronouns / articles / prepositions
    "I", "A", "AM", "AN", "AS", "AT", "BE", "BY", "DO", "GO", "IF", "IN",
    "IS", "IT", "ME", "MY", "NO", "OF", "OK", "ON", "OR", "SO", "TO", "UP",
    "US", "WE",
    # Common finance/Reddit abbreviations
    "DD", "EPS", "CEO", "CFO", "CTO", "COO", "IPO", "ETF", "SEC", "FDA",
    "FED", "GDP", "CPI", "ATH", "ATL", "OTM", "ITM", "RSI", "EMA", "SMA",
    "DCA", "YOLO", "HODL", "FOMO", "IMO", "TBH", "FYI", "PSA", "TLDR",
    "LOL", "OMG", "WTF", "LMAO", "RIP", "GG", "TY", "EU", "UK",
    "USD", "EUR", "GBP", "JPY", "CAD", "AUD",
    # Reddit-specific
    "OP", "OC", "TIL", "AMA", "NSFW", "EDIT", "ETA",
    # Common words that are also short
    "THE", "FOR", "ARE", "BUT", "NOT", "YOU", "ALL", "CAN", "HER", "WAS",
    "ONE", "OUR", "OUT", "HAS", "HIS", "HOW", "ITS", "LET", "MAY", "NEW",
    "NOW", "OLD", "SEE", "WAY", "WHO", "BOY", "DID", "GET", "HIM", "MAN",
    "RUN", "SAY", "SHE", "TOO", "USE", "DAD", "MOM", "OWN", "TOP", "BIG",
    "PUT", "END", "WHY", "BUY", "LOW", "FAR", "SET", "TRY", "ASK",
    "MEN", "RAN", "HIGH", "LONG", "REAL", "JUST", "CALL", "HOLD", "SELL",
    "STOP", "RISK", "GAIN", "LOSS", "CASH", "DEBT", "BEAR", "BULL", "PUMP",
    "DUMP", "OPEN", "WILL", "FREE", "BEST", "NEXT", "EVER", "MUCH", "VERY",
    "GOOD", "BACK", "OVER", "SAVE", "HUGE", "DOWN", "MOVE", "EASY", "HARD",
    "FAST", "ONLY", "MOST", "SURE", "HOPE", "NEED", "EVEN", "EACH", "PLAY",
    "MORE", "SAME", "ZERO", "MANY", "WELL", "DONE", "HALF", "LIFE", "HELP",
    "TRUE", "BEEN", "LIKE", "SOME", "THAN", "THEM", "THEN", "THEY", "THIS",
    "THAT", "WHAT", "WHEN", "WITH", "HAVE", "MAKE", "TAKE", "COME", "LOOK",
    "WANT", "GIVE", "TELL", "WORK", "ALSO", "HERE", "YEAR", "KEEP",
    # Common finance terms
    "STOCK", "SHARE", "TRADE", "PENNY", "HEDGE", "SHORT", "CALLS", "PUTS",
    "MARKET", "PRICE",
})

# Well-known US stock tickers - popular/meme stocks and major companies
# This is a curated subset; a production system would use a full exchange list
KNOWN_TICKERS = frozenset({
    # Meme stocks
    "GME", "AMC", "BB", "NOK", "BBBY", "PLTR", "WISH", "CLOV", "SOFI",
    "SPCE", "TLRY", "SNDL", "WKHS", "RKT", "UWMC", "MVIS", "CLNE",
    # Mega caps
    "AAPL", "MSFT", "AMZN", "GOOGL", "GOOG", "META", "TSLA", "NVDA",
    "BRK", "JPM", "JNJ", "UNH", "PG", "MA", "HD", "DIS", "BAC",
    "XOM", "PFE", "ABBV", "KO", "PEP", "TMO", "COST", "AVGO", "MRK",
    "CVX", "WMT", "CSCO", "ABT", "ACN", "DHR", "LLY", "TXN", "NEE",
    "BMY", "UPS", "RTX", "AMGN", "PM", "HON", "IBM", "QCOM", "LOW",
    "GE", "CAT", "BA", "MMM", "GS", "AXP", "SBUX", "MDLZ", "ADI",
    "BLK", "ISRG", "GILD", "CVS", "CI", "SYK", "ZTS", "BKNG", "VRTX",
    "REGN", "ATVI", "FISV", "APD", "CME", "CL", "ITW", "SHW", "NSC",
    "LRCX", "KLAC", "SNPS", "CDNS", "MRVL", "FTNT", "PANW", "CRWD",
    # Popular tech
    "AMD", "INTC", "MU", "NFLX", "CRM", "PYPL", "SQ", "SHOP", "SNAP",
    "UBER", "LYFT", "PINS", "TWLO", "ZM", "DOCU", "NET", "DDOG",
    "SNOW", "COIN", "HOOD", "RBLX", "RIVN", "LCID", "NIO", "XPEV",
    "LI", "F", "GM", "TM", "RACE",
    # ETFs
    "SPY", "QQQ", "DIA", "IWM", "VTI", "VOO", "VXX", "ARKK", "ARKG",
    "ARKW", "XLF", "XLE", "XLK", "XLV", "XLI", "GLD", "SLV", "TLT",
    # Crypto-related
    "MARA", "RIOT", "MSTR", "BITO",
    # Other frequently discussed
    "V", "WFC", "T", "VZ", "CMCSA", "TMUS", "MO",
    "CLF", "X", "AA", "FCX", "VALE",
    # Biotech/pharma
    "MRNA", "BNTX", "DNA", "EDIT", "CRSP", "BEAM",
    # Retail
    "TGT", "LULU", "NKE", "GPS",
})

# Bullish sentiment keywords
BULLISH_KEYWORDS = frozenset({
    "moon", "rocket", "tendies", "diamond", "hands", "squeeze",
    "calls", "long", "bull", "bullish", "buy", "buying", "bought",
    "yolo", "lambo", "gain", "gains", "gainz", "profit", "profits",
    "green", "up", "rally", "rip", "soar", "surge", "breakout",
    "undervalued", "cheap", "dip", "btfd", "hold", "hodl", "holding",
    "accumulate", "load", "loaded", "loading",
})

# Bearish sentiment keywords
BEARISH_KEYWORDS = frozenset({
    "puts", "short", "shorting", "bear", "bearish", "sell", "selling",
    "sold", "dump", "dumping", "crash", "crashing", "tank", "tanking",
    "bag", "bagholder", "bagholding", "loss", "losses", "red",
    "down", "drop", "dropping", "fall", "falling", "overvalued",
    "bubble", "scam", "fraud", "bankrupt", "bankruptcy", "dead",
    "rip", "avoid", "warning",
})

# Regex for $TICKER pattern
_DOLLAR_TICKER_RE = re.compile(r"\$([A-Z]{1,5})\b")

# Regex for standalone uppercase words (potential tickers)
_UPPER_WORD_RE = re.compile(r"\b([A-Z]{1,5})\b")


class RedditAnalyzer:
    """Analyzes Reddit posts for stock ticker mentions and sentiment.

    Attributes:
        min_mentions: Minimum mentions for a ticker to be included in trends
        known_tickers: Set of valid ticker symbols
    """

    def __init__(
        self,
        min_mentions: int = 2,
        known_tickers: Optional[frozenset[str]] = None,
    ) -> None:
        """Initialize the analyzer.

        Args:
            min_mentions: Minimum mentions to qualify as trending
            known_tickers: Set of known valid tickers (defaults to built-in list)
        """
        self.min_mentions = min_mentions
        self.known_tickers = known_tickers or KNOWN_TICKERS

    def extract_tickers(self, text: str) -> list[str]:
        """Extract stock ticker symbols from text.

        Looks for $TICKER patterns first, then standalone uppercase words
        that match known tickers.

        Args:
            text: Text to search for tickers

        Returns:
            List of unique ticker symbols found (deduplicated, order preserved)
        """
        found: list[str] = []
        seen: set[str] = set()

        # Priority 1: $TICKER patterns (strong signal)
        for match in _DOLLAR_TICKER_RE.finditer(text):
            ticker = match.group(1)
            if ticker not in seen and ticker not in FALSE_POSITIVE_TICKERS and ticker in self.known_tickers:
                seen.add(ticker)
                found.append(ticker)

        # Priority 2: Standalone uppercase words matching known tickers
        for match in _UPPER_WORD_RE.finditer(text):
            ticker = match.group(1)
            if ticker not in seen and ticker not in FALSE_POSITIVE_TICKERS and ticker in self.known_tickers:
                seen.add(ticker)
                found.append(ticker)

        return found

    def score_sentiment(self, text: str) -> float:
        """Score the sentiment of text on a -1.0 to +1.0 scale.

        Uses keyword matching against bullish and bearish term lists.

        Args:
            text: Text to analyze

        Returns:
            Sentiment score: positive = bullish, negative = bearish
        """
        words = set(text.lower().split())

        bullish_count = len(words & BULLISH_KEYWORDS)
        bearish_count = len(words & BEARISH_KEYWORDS)

        total = bullish_count + bearish_count
        if total == 0:
            return 0.0

        # Normalized score: (bullish - bearish) / total
        raw_score = (bullish_count - bearish_count) / total
        # Clamp to [-1.0, 1.0]
        return max(-1.0, min(1.0, raw_score))

    def analyze_post(self, post: RedditPost) -> list[TickerMention]:
        """Analyze a single post for ticker mentions and sentiment.

        Args:
            post: Reddit post to analyze

        Returns:
            List of ticker mentions found in the post
        """
        tickers = self.extract_tickers(post.full_text)
        if not tickers:
            return []

        sentiment = self.score_sentiment(post.full_text)

        mentions: list[TickerMention] = []
        for ticker in tickers:
            mention = TickerMention(
                ticker=ticker,
                subreddit=post.subreddit,
                post_id=post.post_id,
                post_title=post.title,
                sentiment=sentiment,
                post_score=post.score,
                post_comments=post.num_comments,
                post_created_utc=post.created_utc,
            )
            mentions.append(mention)

        return mentions

    def analyze_posts(self, posts: list[RedditPost]) -> list[TickerMention]:
        """Analyze multiple posts for ticker mentions.

        Args:
            posts: List of Reddit posts

        Returns:
            All ticker mentions found across all posts
        """
        all_mentions: list[TickerMention] = []
        for post in posts:
            all_mentions.extend(self.analyze_post(post))
        return all_mentions

    def aggregate_trends(self, mentions: list[TickerMention]) -> list[MemeStockTrend]:
        """Aggregate ticker mentions into trend summaries.

        Groups mentions by ticker, computes statistics, and ranks
        by a composite trending score.

        Args:
            mentions: List of ticker mentions

        Returns:
            List of trends sorted by rank (most trending first)
        """
        # Group by ticker
        by_ticker: dict[str, list[TickerMention]] = defaultdict(list)
        for mention in mentions:
            by_ticker[mention.ticker].append(mention)

        trends: list[MemeStockTrend] = []
        for ticker, ticker_mentions in by_ticker.items():
            if len(ticker_mentions) < self.min_mentions:
                continue

            # Compute aggregate stats
            mention_count = len(ticker_mentions)
            avg_sentiment = sum(m.sentiment for m in ticker_mentions) / mention_count
            total_post_score = sum(m.post_score for m in ticker_mentions)
            total_comments = sum(m.post_comments for m in ticker_mentions)

            # Subreddit breakdown
            sub_counts: dict[str, int] = defaultdict(int)
            for m in ticker_mentions:
                sub_counts[m.subreddit] += 1

            # Composite trending score:
            # Weight mentions heavily, add engagement (log-scaled post score)
            import math
            engagement = math.log1p(abs(total_post_score)) + math.log1p(total_comments)
            trending_score = mention_count * 10.0 + engagement

            trends.append(MemeStockTrend(
                ticker=ticker,
                mention_count=mention_count,
                avg_sentiment=round(avg_sentiment, 3),
                total_post_score=total_post_score,
                total_comments=total_comments,
                subreddit_breakdown=dict(sub_counts),
                trending_score=round(trending_score, 2),
            ))

        # Sort by trending score descending and assign ranks
        trends.sort(key=lambda t: t.trending_score, reverse=True)
        ranked_trends: list[MemeStockTrend] = []
        for i, trend in enumerate(trends, start=1):
            ranked_trends.append(trend.model_copy(update={"rank": i}))

        return ranked_trends

    def scan(
        self,
        posts: list[RedditPost],
        subreddits: Optional[list[str]] = None,
    ) -> RedditScanResult:
        """Run a full scan: extract tickers, score sentiment, aggregate trends.

        Args:
            posts: Reddit posts to analyze
            subreddits: List of subreddits that were scanned

        Returns:
            Complete scan result with trends and mentions
        """
        mentions = self.analyze_posts(posts)
        trends = self.aggregate_trends(mentions)

        return RedditScanResult(
            scan_id=str(uuid4()),
            subreddits=subreddits or [],
            post_count=len(posts),
            trends=trends,
            scanned_at=datetime.utcnow(),
            mentions=mentions,
        )
