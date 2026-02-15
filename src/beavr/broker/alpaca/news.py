"""Alpaca news adapter implementing NewsProvider protocol."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class AlpacaNews:
    """NewsProvider implementation for Alpaca."""

    def __init__(self, api_key: str, api_secret: str) -> None:
        try:
            from alpaca.data import NewsClient, NewsRequest

            self._client = NewsClient(api_key, api_secret)
            self._NewsRequest = NewsRequest
        except ImportError as err:
            raise ImportError("alpaca-py required for news") from err

    def get_news(self, symbols: list[str], limit: int = 10) -> list[dict]:
        """Fetch news articles for given symbols."""
        try:
            request_params: dict[str, Any] = {"limit": limit}
            if symbols:
                request_params["symbols"] = ",".join(symbols)

            response = self._client.get_news(
                self._NewsRequest(**request_params)
            )

            news_items: list[dict] = []
            try:
                news_list = (
                    response.data.get("news", [])
                    if hasattr(response, "data")
                    else []
                )
                for n in news_list[:limit]:
                    if isinstance(n, dict):
                        news_items.append(
                            {
                                "headline": n.get("headline", "") or "",
                                "summary": n.get("summary", "") or "",
                                "symbols": list(n.get("symbols", [])) or [],
                                "source": n.get("source", "") or "",
                                "created_at": str(n.get("created_at", "")),
                                "url": n.get("url", "") or "",
                            }
                        )
                    else:
                        news_items.append(
                            {
                                "headline": getattr(n, "headline", "") or "",
                                "summary": getattr(n, "summary", "") or "",
                                "symbols": list(getattr(n, "symbols", []))
                                or [],
                                "source": getattr(n, "source", "") or "",
                                "created_at": str(
                                    getattr(n, "created_at", "")
                                ),
                                "url": getattr(n, "url", "") or "",
                            }
                        )
            except Exception as e:
                logger.warning(f"Error parsing news response: {e}")

            return news_items
        except Exception as e:
            logger.warning(f"Failed to get news: {e}")
            return []
