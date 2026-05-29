"""Tests for Reddit API client."""

import json
from unittest.mock import MagicMock, patch

from beavr.reddit.client import RedditClient


def _make_reddit_response(posts: list[dict]) -> dict:
    """Create a mock Reddit API JSON response."""
    return {
        "kind": "Listing",
        "data": {
            "children": [
                {"kind": "t3", "data": post}
                for post in posts
            ],
        },
    }


class TestRedditClient:
    """Tests for RedditClient."""

    def test_default_subreddits(self) -> None:
        client = RedditClient()
        assert "wallstreetbets" in client.subreddits
        assert "stocks" in client.subreddits

    def test_custom_subreddits(self) -> None:
        client = RedditClient(subreddits=["mysubreddit"])
        assert client.subreddits == ["mysubreddit"]

    def test_post_limit_capped(self) -> None:
        client = RedditClient(post_limit=200)
        assert client.post_limit == 100  # Reddit caps at 100

    @patch("beavr.reddit.client.urllib.request.urlopen")
    @patch("beavr.reddit.client._last_request_time", 0.0)
    def test_fetch_hot_posts(self, mock_urlopen: MagicMock) -> None:
        response_data = _make_reddit_response([
            {
                "id": "abc123",
                "title": "GME to the moon!",
                "selftext": "Diamond hands!",
                "score": 1500,
                "num_comments": 300,
                "created_utc": 1700000000.0,
                "url": "https://reddit.com/r/wsb/abc123",
                "is_self": True,
                "upvote_ratio": 0.95,
            }
        ])

        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(response_data).encode("utf-8")
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        client = RedditClient(subreddits=["wallstreetbets"], post_limit=10)
        posts = client.fetch_hot_posts("wallstreetbets")

        assert len(posts) == 1
        assert posts[0].post_id == "abc123"
        assert posts[0].title == "GME to the moon!"
        assert posts[0].score == 1500

    @patch("beavr.reddit.client.urllib.request.urlopen")
    @patch("beavr.reddit.client._last_request_time", 0.0)
    def test_parse_multiple_posts(self, mock_urlopen: MagicMock) -> None:
        response_data = _make_reddit_response([
            {"id": "1", "title": "Post 1", "selftext": "", "score": 10,
             "num_comments": 1, "created_utc": 1700000000.0, "url": "", "is_self": True, "upvote_ratio": 0.5},
            {"id": "2", "title": "Post 2", "selftext": "", "score": 20,
             "num_comments": 2, "created_utc": 1700000100.0, "url": "", "is_self": True, "upvote_ratio": 0.6},
        ])

        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(response_data).encode("utf-8")
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        client = RedditClient()
        posts = client.fetch_hot_posts("stocks")
        assert len(posts) == 2

    @patch("beavr.reddit.client.urllib.request.urlopen")
    @patch("beavr.reddit.client._last_request_time", 0.0)
    def test_skips_non_t3_entries(self, mock_urlopen: MagicMock) -> None:
        response_data = {
            "kind": "Listing",
            "data": {
                "children": [
                    {"kind": "t1", "data": {"id": "comment"}},  # Comment, not post
                    {"kind": "t3", "data": {
                        "id": "post1", "title": "Real post", "selftext": "",
                        "score": 10, "num_comments": 1, "created_utc": 1700000000.0,
                        "url": "", "is_self": True, "upvote_ratio": 0.5,
                    }},
                ],
            },
        }

        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(response_data).encode("utf-8")
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        client = RedditClient()
        posts = client.fetch_hot_posts("wallstreetbets")
        assert len(posts) == 1
        assert posts[0].post_id == "post1"

    @patch("beavr.reddit.client.urllib.request.urlopen")
    @patch("beavr.reddit.client._last_request_time", 0.0)
    def test_fetch_all_deduplicates(self, mock_urlopen: MagicMock) -> None:
        """fetch_all_posts should deduplicate posts across feeds."""
        response_data = _make_reddit_response([
            {"id": "same_post", "title": "Test", "selftext": "", "score": 10,
             "num_comments": 1, "created_utc": 1700000000.0, "url": "", "is_self": True, "upvote_ratio": 0.5},
        ])

        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(response_data).encode("utf-8")
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        client = RedditClient(subreddits=["wallstreetbets"])
        posts = client.fetch_all_posts()

        # Even though hot + rising both return "same_post", it should be deduped
        same_post_count = sum(1 for p in posts if p.post_id == "same_post")
        assert same_post_count == 1
