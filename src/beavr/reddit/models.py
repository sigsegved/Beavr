"""Data models for Reddit meme stock analysis."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class RedditPost(BaseModel):
    """A Reddit post with metadata relevant to stock analysis.

    Attributes:
        post_id: Reddit post ID
        subreddit: Subreddit name (without r/ prefix)
        title: Post title
        selftext: Post body text (may be empty for link posts)
        score: Net upvotes
        num_comments: Number of comments
        created_utc: Post creation time (UTC epoch)
        url: Post URL
        is_self: Whether this is a self/text post
        upvote_ratio: Ratio of upvotes to total votes
    """

    post_id: str = Field(..., description="Reddit post ID")
    subreddit: str = Field(..., description="Subreddit name")
    title: str = Field(..., description="Post title")
    selftext: str = Field(default="", description="Post body text")
    score: int = Field(default=0, description="Net upvotes")
    num_comments: int = Field(default=0, description="Number of comments")
    created_utc: float = Field(..., description="Creation time (UTC epoch)")
    url: str = Field(default="", description="Post URL")
    is_self: bool = Field(default=True, description="Is a self/text post")
    upvote_ratio: float = Field(default=0.5, description="Upvote ratio")

    model_config = ConfigDict(frozen=True)

    @property
    def created_datetime(self) -> datetime:
        """Get creation time as datetime."""
        return datetime.utcfromtimestamp(self.created_utc)

    @property
    def full_text(self) -> str:
        """Get combined title and body text for analysis."""
        parts = [self.title]
        if self.selftext:
            parts.append(self.selftext)
        return " ".join(parts)


class TickerMention(BaseModel):
    """A single mention of a stock ticker in a Reddit post.

    Attributes:
        ticker: Stock ticker symbol (e.g., "GME")
        subreddit: Source subreddit
        post_id: Reddit post ID where mentioned
        post_title: Post title for context
        sentiment: Sentiment score (-1.0 bearish to +1.0 bullish)
        post_score: Post's net upvotes (weight signal)
        post_comments: Post's comment count
        post_created_utc: Post creation time
    """

    ticker: str = Field(..., description="Stock ticker symbol")
    subreddit: str = Field(..., description="Source subreddit")
    post_id: str = Field(..., description="Reddit post ID")
    post_title: str = Field(default="", description="Post title")
    sentiment: float = Field(default=0.0, description="Sentiment score", ge=-1.0, le=1.0)
    post_score: int = Field(default=0, description="Post net upvotes")
    post_comments: int = Field(default=0, description="Post comment count")
    post_created_utc: float = Field(default=0.0, description="Post creation time")

    model_config = ConfigDict(frozen=True)


class MemeStockTrend(BaseModel):
    """Aggregated trend data for a single ticker across Reddit.

    Attributes:
        ticker: Stock ticker symbol
        mention_count: Total number of mentions
        avg_sentiment: Average sentiment across mentions
        total_post_score: Sum of post scores where mentioned
        total_comments: Sum of comments on posts where mentioned
        subreddit_breakdown: Mention count per subreddit
        rank: Rank by trending score (1 = most trending)
        trending_score: Composite score for ranking
    """

    ticker: str = Field(..., description="Stock ticker symbol")
    mention_count: int = Field(default=0, description="Total mentions")
    avg_sentiment: float = Field(default=0.0, description="Average sentiment")
    total_post_score: int = Field(default=0, description="Sum of post scores")
    total_comments: int = Field(default=0, description="Sum of comment counts")
    subreddit_breakdown: dict[str, int] = Field(default_factory=dict, description="Mentions per subreddit")
    rank: int = Field(default=0, description="Trending rank")
    trending_score: float = Field(default=0.0, description="Composite trending score")

    model_config = ConfigDict(frozen=True)

    @property
    def sentiment_label(self) -> str:
        """Human-readable sentiment label."""
        if self.avg_sentiment > 0.3:
            return "Bullish"
        elif self.avg_sentiment > 0.1:
            return "Slightly Bullish"
        elif self.avg_sentiment < -0.3:
            return "Bearish"
        elif self.avg_sentiment < -0.1:
            return "Slightly Bearish"
        return "Neutral"


class RedditScanResult(BaseModel):
    """Result of a full Reddit scan for meme stock trends.

    Attributes:
        scan_id: Unique scan identifier
        subreddits: Subreddits that were scanned
        post_count: Total posts analyzed
        trends: List of trending tickers sorted by rank
        scanned_at: Scan timestamp
        mentions: Raw ticker mentions
    """

    scan_id: str = Field(..., description="Scan ID")
    subreddits: list[str] = Field(default_factory=list, description="Scanned subreddits")
    post_count: int = Field(default=0, description="Posts analyzed")
    trends: list[MemeStockTrend] = Field(default_factory=list, description="Trending tickers")
    scanned_at: datetime = Field(default_factory=datetime.utcnow, description="Scan time")
    mentions: list[TickerMention] = Field(default_factory=list, description="Raw mentions")

    model_config = ConfigDict(frozen=True)

    @property
    def ticker_count(self) -> int:
        """Number of unique tickers found."""
        return len(self.trends)
