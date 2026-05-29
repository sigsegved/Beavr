"""Reddit API client for fetching posts from meme stock subreddits."""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from typing import Any, Optional

from beavr.reddit.models import RedditPost

logger = logging.getLogger(__name__)

# Default subreddits for meme stock analysis
DEFAULT_SUBREDDITS = ["wallstreetbets", "stocks", "pennystocks"]

# Rate limiting: minimum seconds between requests
_MIN_REQUEST_INTERVAL = 2.0
_last_request_time = 0.0


class RedditClientError(Exception):
    """Base exception for Reddit client errors."""


class RedditRateLimitError(RedditClientError):
    """Rate limit hit from Reddit API."""


class RedditClient:
    """Fetches posts from Reddit using the public JSON API.

    No authentication required - uses Reddit's .json endpoints
    for read-only access.

    Attributes:
        user_agent: User-Agent string for requests
        subreddits: List of subreddits to scan
        post_limit: Maximum posts per subreddit
    """

    def __init__(
        self,
        user_agent: str = "beavr/0.1.0 (https://github.com/sigsegved/Beavr)",
        subreddits: Optional[list[str]] = None,
        post_limit: int = 100,
        request_timeout: int = 15,
    ) -> None:
        """Initialize the Reddit client.

        Args:
            user_agent: User-Agent for Reddit API requests
            subreddits: Subreddits to scan (defaults to meme stock subs)
            post_limit: Max posts to fetch per subreddit
            request_timeout: HTTP request timeout in seconds
        """
        self.user_agent = user_agent
        self.subreddits = subreddits or list(DEFAULT_SUBREDDITS)
        self.post_limit = min(post_limit, 100)  # Reddit caps at 100
        self.request_timeout = request_timeout

    def _rate_limit(self) -> None:
        """Enforce rate limiting between requests."""
        global _last_request_time
        elapsed = time.time() - _last_request_time
        if elapsed < _MIN_REQUEST_INTERVAL:
            time.sleep(_MIN_REQUEST_INTERVAL - elapsed)
        _last_request_time = time.time()

    def _fetch_json(self, url: str) -> dict[str, Any]:
        """Fetch JSON from a URL with rate limiting and error handling.

        Args:
            url: URL to fetch

        Returns:
            Parsed JSON response

        Raises:
            RedditClientError: On network or parsing errors
            RedditRateLimitError: On 429 responses
        """
        self._rate_limit()

        req = urllib.request.Request(
            url,
            headers={"User-Agent": self.user_agent},
        )

        try:
            with urllib.request.urlopen(req, timeout=self.request_timeout) as resp:
                data = resp.read().decode("utf-8")
                parsed: dict[str, Any] = json.loads(data)
                return parsed
        except urllib.error.HTTPError as e:
            if e.code == 429:
                raise RedditRateLimitError("Reddit rate limit exceeded. Try again later.") from e
            raise RedditClientError(f"Reddit API returned HTTP {e.code}: {e.reason}") from e
        except urllib.error.URLError as e:
            raise RedditClientError(f"Failed to connect to Reddit: {e.reason}") from e
        except json.JSONDecodeError as e:
            raise RedditClientError(f"Invalid JSON response from Reddit: {e}") from e

    def _parse_posts(self, data: dict[str, Any], subreddit: str) -> list[RedditPost]:
        """Parse Reddit API response into RedditPost models.

        Args:
            data: Raw JSON response from Reddit
            subreddit: Source subreddit name

        Returns:
            List of parsed posts
        """
        posts: list[RedditPost] = []

        listing = data.get("data", {})
        children = listing.get("children", [])

        for child in children:
            if child.get("kind") != "t3":
                continue

            post_data = child.get("data", {})

            try:
                post = RedditPost(
                    post_id=post_data.get("id", ""),
                    subreddit=subreddit,
                    title=post_data.get("title", ""),
                    selftext=post_data.get("selftext", "") or "",
                    score=post_data.get("score", 0),
                    num_comments=post_data.get("num_comments", 0),
                    created_utc=post_data.get("created_utc", 0.0),
                    url=post_data.get("url", ""),
                    is_self=post_data.get("is_self", True),
                    upvote_ratio=post_data.get("upvote_ratio", 0.5),
                )
                posts.append(post)
            except Exception:
                logger.debug(f"Skipping malformed post in r/{subreddit}: {post_data.get('id', '?')}")
                continue

        return posts

    def fetch_hot_posts(self, subreddit: str) -> list[RedditPost]:
        """Fetch hot posts from a subreddit.

        Args:
            subreddit: Subreddit name (without r/)

        Returns:
            List of hot posts

        Raises:
            RedditClientError: On API errors
        """
        url = f"https://www.reddit.com/r/{subreddit}/hot.json?limit={self.post_limit}&raw_json=1"
        logger.debug(f"Fetching hot posts from r/{subreddit}")

        data = self._fetch_json(url)
        posts = self._parse_posts(data, subreddit)
        logger.info(f"Fetched {len(posts)} hot posts from r/{subreddit}")
        return posts

    def fetch_new_posts(self, subreddit: str) -> list[RedditPost]:
        """Fetch new posts from a subreddit.

        Args:
            subreddit: Subreddit name (without r/)

        Returns:
            List of new posts

        Raises:
            RedditClientError: On API errors
        """
        url = f"https://www.reddit.com/r/{subreddit}/new.json?limit={self.post_limit}&raw_json=1"
        logger.debug(f"Fetching new posts from r/{subreddit}")

        data = self._fetch_json(url)
        posts = self._parse_posts(data, subreddit)
        logger.info(f"Fetched {len(posts)} new posts from r/{subreddit}")
        return posts

    def fetch_rising_posts(self, subreddit: str) -> list[RedditPost]:
        """Fetch rising posts from a subreddit.

        Args:
            subreddit: Subreddit name (without r/)

        Returns:
            List of rising posts

        Raises:
            RedditClientError: On API errors
        """
        url = f"https://www.reddit.com/r/{subreddit}/rising.json?limit={self.post_limit}&raw_json=1"
        logger.debug(f"Fetching rising posts from r/{subreddit}")

        data = self._fetch_json(url)
        posts = self._parse_posts(data, subreddit)
        logger.info(f"Fetched {len(posts)} rising posts from r/{subreddit}")
        return posts

    def fetch_all_posts(self) -> list[RedditPost]:
        """Fetch hot and rising posts from all configured subreddits.

        Returns:
            Combined list of posts from all subreddits.
            Continues on errors from individual subreddits.
        """
        all_posts: list[RedditPost] = []
        seen_ids: set[str] = set()

        for subreddit in self.subreddits:
            for fetch_fn in [self.fetch_hot_posts, self.fetch_rising_posts]:
                try:
                    posts = fetch_fn(subreddit)
                    for post in posts:
                        if post.post_id not in seen_ids:
                            seen_ids.add(post.post_id)
                            all_posts.append(post)
                except RedditClientError as e:
                    logger.warning(f"Failed to fetch from r/{subreddit}: {e}")
                    continue

        logger.info(f"Fetched {len(all_posts)} unique posts from {len(self.subreddits)} subreddits")
        return all_posts
