"""Tests for AlpacaNews adapter."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# ===== Mock helpers =====


class MockNewsArticle:
    """Mimics an Alpaca news article object (attribute-based)."""

    def __init__(
        self,
        headline: str = "Test headline",
        summary: str = "Test summary",
        symbols: list[str] | None = None,
        source: str = "Reuters",
        created_at: str = "2026-02-15T10:00:00Z",
        url: str = "https://example.com/news",
    ) -> None:
        self.headline = headline
        self.summary = summary
        self.symbols = symbols or ["AAPL"]
        self.source = source
        self.created_at = created_at
        self.url = url


class MockNewsResponse:
    """Mimics the response from NewsClient.get_news with .data dict."""

    def __init__(self, news: list) -> None:
        self.data = {"news": news}


# ===== Fixtures =====


@pytest.fixture
def mock_news_client() -> MagicMock:
    """Create a mock NewsClient."""
    return MagicMock()


@pytest.fixture
def _patch_alpaca_modules() -> Any:
    """Patch all alpaca submodules so imports succeed without alpaca-py."""
    mods = {
        "alpaca": MagicMock(),
        "alpaca.data": MagicMock(),
        "alpaca.data.requests": MagicMock(),
        "alpaca.data.timeframe": MagicMock(),
    }
    with patch.dict("sys.modules", mods):
        yield


@pytest.fixture
def news_adapter(
    _patch_alpaca_modules: Any, mock_news_client: MagicMock
) -> Any:
    """Create an AlpacaNews with a mocked client."""
    from beavr.broker.alpaca.news import AlpacaNews

    instance = AlpacaNews.__new__(AlpacaNews)
    instance._client = mock_news_client
    instance._NewsRequest = MagicMock()
    return instance


# ===== Tests =====


class TestAlpacaNews:
    """Tests for AlpacaNews."""

    # ===== Init =====

    def test_init_stores_client(self, news_adapter: Any) -> None:
        """AlpacaNews should store a news client."""
        assert news_adapter._client is not None

    # ===== get_news — happy path =====

    def test_get_news_returns_list_of_dicts(
        self,
        news_adapter: Any,
        mock_news_client: MagicMock,
    ) -> None:
        """get_news should return list of dicts with expected keys."""
        mock_news_client.get_news.return_value = MockNewsResponse(
            news=[
                {
                    "headline": "AAPL earnings beat",
                    "summary": "Apple reported strong Q1",
                    "symbols": ["AAPL"],
                    "source": "Reuters",
                    "created_at": "2026-02-15T10:00:00Z",
                    "url": "https://example.com/aapl",
                },
            ]
        )

        result = news_adapter.get_news(symbols=["AAPL"], limit=5)

        assert len(result) == 1
        article = result[0]
        assert article["headline"] == "AAPL earnings beat"
        assert article["summary"] == "Apple reported strong Q1"
        assert article["symbols"] == ["AAPL"]
        assert article["source"] == "Reuters"
        assert article["url"] == "https://example.com/aapl"

    def test_get_news_with_attribute_based_articles(
        self,
        news_adapter: Any,
        mock_news_client: MagicMock,
    ) -> None:
        """get_news should handle attribute-based article objects."""
        mock_news_client.get_news.return_value = MockNewsResponse(
            news=[MockNewsArticle(headline="Tech rally", source="Bloomberg")]
        )

        result = news_adapter.get_news(symbols=["MSFT"], limit=5)

        assert len(result) == 1
        assert result[0]["headline"] == "Tech rally"
        assert result[0]["source"] == "Bloomberg"

    # ===== get_news — empty symbols =====

    def test_get_news_empty_symbols(
        self,
        news_adapter: Any,
        mock_news_client: MagicMock,
    ) -> None:
        """get_news with empty symbols list should not pass symbols param."""
        mock_news_client.get_news.return_value = MockNewsResponse(news=[])

        result = news_adapter.get_news(symbols=[], limit=5)

        assert result == []
        # Verify _NewsRequest was called without symbols
        call_kwargs = news_adapter._NewsRequest.call_args
        assert "symbols" not in call_kwargs.kwargs

    # ===== get_news — passes symbols correctly =====

    def test_get_news_passes_symbols_as_comma_string(
        self,
        news_adapter: Any,
        mock_news_client: MagicMock,
    ) -> None:
        """get_news should join symbols with comma and pass to request."""
        mock_news_client.get_news.return_value = MockNewsResponse(news=[])

        news_adapter.get_news(symbols=["AAPL", "MSFT", "GOOG"], limit=10)

        call_kwargs = news_adapter._NewsRequest.call_args.kwargs
        assert call_kwargs["symbols"] == "AAPL,MSFT,GOOG"
        assert call_kwargs["limit"] == 10

    # ===== get_news — error handling =====

    def test_get_news_error_returns_empty_list(
        self,
        news_adapter: Any,
        mock_news_client: MagicMock,
    ) -> None:
        """get_news should return empty list on error (graceful degradation)."""
        mock_news_client.get_news.side_effect = RuntimeError("API unavailable")

        result = news_adapter.get_news(symbols=["AAPL"], limit=5)

        assert result == []

    # ===== __init__ coverage =====

    def test_init_actually_calls_constructor(
        self, _patch_alpaca_modules: Any
    ) -> None:
        """Instantiating AlpacaNews should import NewsClient and store it."""
        from beavr.broker.alpaca.news import AlpacaNews

        adapter = AlpacaNews("key", "secret")
        assert adapter._client is not None
        assert adapter._NewsRequest is not None

    def test_init_import_error_when_alpaca_missing(
        self, _patch_alpaca_modules: Any
    ) -> None:
        """AlpacaNews should raise ImportError when alpaca-py is not installed."""
        import builtins

        from beavr.broker.alpaca.news import AlpacaNews

        original_import = builtins.__import__

        def selective_import(name: str, *args: Any, **kwargs: Any) -> Any:
            if name == "alpaca.data":
                raise ImportError("No module named 'alpaca.data'")
            return original_import(name, *args, **kwargs)

        with (
            patch("builtins.__import__", side_effect=selective_import),
            pytest.raises(ImportError, match="alpaca-py required for news"),
        ):
            AlpacaNews("key", "secret")

    # ===== inner parsing exception (lines 67-68) =====

    def test_get_news_inner_parse_error_returns_empty(
        self,
        news_adapter: Any,
        mock_news_client: MagicMock,
    ) -> None:
        """When parsing the news list raises, should log and return empty."""
        # Create a response whose .data.get("news") returns a value that
        # raises an exception when iterated / sliced.
        bad_response = MagicMock()
        bad_data: dict[str, Any] = {"news": None}  # None[:limit] raises TypeError
        bad_response.data = bad_data
        mock_news_client.get_news.return_value = bad_response

        result = news_adapter.get_news(symbols=["AAPL"], limit=5)

        assert result == []
