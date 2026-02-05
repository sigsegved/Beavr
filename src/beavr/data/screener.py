"""Market screener for dynamic symbol discovery.

Uses Alpaca's screener API to find top gainers, losers, and most active stocks.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class MarketMover:
    """A stock that's moving significantly."""
    
    symbol: str
    price: Decimal
    percent_change: float
    volume: Optional[int] = None
    trade_count: Optional[int] = None


@dataclass 
class MarketScreenerResult:
    """Results from market screening."""
    
    top_gainers: list[MarketMover]
    top_losers: list[MarketMover]
    most_active: list[MarketMover]


class MarketScreener:
    """
    Screens the market for trading opportunities.
    
    Uses Alpaca's screener API to find:
    - Top gainers (biggest % increase)
    - Top losers (biggest % decrease)
    - Most active (highest volume)
    """
    
    def __init__(self, api_key: str, api_secret: str) -> None:
        """Initialize screener with Alpaca credentials."""
        try:
            from alpaca.data import (
                MarketMoversRequest,
                MostActivesBy,
                MostActivesRequest,
                ScreenerClient,
            )
            
            self._client = ScreenerClient(api_key, api_secret)
            self._MarketMoversRequest = MarketMoversRequest
            self._MostActivesRequest = MostActivesRequest
            self._MostActivesBy = MostActivesBy
            
        except ImportError as err:
            raise ImportError("alpaca-py required for screener") from err
    
    def get_market_movers(self, top_n: int = 10) -> MarketScreenerResult:
        """
        Get top market movers.
        
        Args:
            top_n: Number of stocks to return in each category
            
        Returns:
            MarketScreenerResult with gainers, losers, and most active
        """
        logger.info(f"Fetching top {top_n} market movers...")
        
        # Get gainers and losers
        movers_response = self._client.get_market_movers(
            self._MarketMoversRequest(top=top_n)
        )
        
        gainers = [
            MarketMover(
                symbol=m.symbol,
                price=Decimal(str(m.price)),
                percent_change=float(m.percent_change),
            )
            for m in movers_response.gainers[:top_n]
        ]
        
        losers = [
            MarketMover(
                symbol=m.symbol,
                price=Decimal(str(m.price)),
                percent_change=float(m.percent_change),
            )
            for m in movers_response.losers[:top_n]
        ]
        
        # Get most active by volume
        actives_response = self._client.get_most_actives(
            self._MostActivesRequest(top=top_n, by=self._MostActivesBy.VOLUME)
        )
        
        most_active = [
            MarketMover(
                symbol=a.symbol,
                price=Decimal("0"),  # Price not available in actives
                percent_change=0.0,
                volume=int(a.volume) if a.volume else None,
                trade_count=int(a.trade_count) if a.trade_count else None,
            )
            for a in actives_response.most_actives[:top_n]
        ]
        
        logger.info(
            f"Found {len(gainers)} gainers, {len(losers)} losers, "
            f"{len(most_active)} most active"
        )
        
        return MarketScreenerResult(
            top_gainers=gainers,
            top_losers=losers,
            most_active=most_active,
        )
    
    def get_tradeable_movers(
        self,
        top_n: int = 5,
        min_price: float = 5.0,
        max_price: float = 500.0,
        max_change_pct: float = 50.0,
    ) -> list[str]:
        """
        Get a filtered list of tradeable symbols from movers.
        
        Filters out:
        - Penny stocks (< min_price)
        - Expensive stocks (> max_price)
        - Extreme movers (> max_change_pct) - often pump & dumps
        
        Args:
            top_n: Max symbols to return
            min_price: Minimum stock price
            max_price: Maximum stock price
            max_change_pct: Maximum % change (filters extreme movers)
            
        Returns:
            List of tradeable symbols
        """
        result = self.get_market_movers(top_n=50)  # Get more to filter from
        
        symbols = set()
        
        # Add filtered gainers (for momentum plays)
        for m in result.top_gainers:
            if (
                float(m.price) >= min_price
                and float(m.price) <= max_price
                and abs(m.percent_change) <= max_change_pct
            ):
                symbols.add(m.symbol)
                if len(symbols) >= top_n:
                    break
        
        # Add filtered losers (for mean reversion plays)
        for m in result.top_losers:
            if (
                float(m.price) >= min_price
                and float(m.price) <= max_price
                and abs(m.percent_change) <= max_change_pct
            ):
                symbols.add(m.symbol)
                if len(symbols) >= top_n * 2:
                    break
        
        logger.info(f"Filtered to {len(symbols)} tradeable symbols: {list(symbols)}")
        
        return list(symbols)[:top_n]


class NewsScanner:
    """
    Scans news for trading-relevant information.
    
    Uses Alpaca's news API to get recent headlines.
    """
    
    def __init__(self, api_key: str, api_secret: str) -> None:
        """Initialize news scanner."""
        try:
            from alpaca.data import NewsClient, NewsRequest
            
            self._client = NewsClient(api_key, api_secret)
            self._NewsRequest = NewsRequest
            
        except ImportError as err:
            raise ImportError("alpaca-py required for news scanner") from err
    
    def get_news(
        self,
        symbols: Optional[list[str] | str] = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """
        Get recent news for symbols.
        
        Args:
            symbols: Symbols to get news for (list or comma-separated string)
            limit: Max news items to return
            
        Returns:
            List of news items with headline, summary, symbols, timestamp
        """
        logger.info(f"Fetching news for {symbols or 'market'}...")
        
        try:
            request_params: dict[str, Any] = {"limit": limit}
            if symbols:
                if isinstance(symbols, list):
                    request_params["symbols"] = ",".join(symbols)
                else:
                    request_params["symbols"] = symbols
            
            response = self._client.get_news(self._NewsRequest(**request_params))
            
            news_items = []
            # Alpaca NewsSet stores news in response.data['news'] as list of dicts
            try:
                news_list = response.data.get('news', []) if hasattr(response, 'data') else []
                
                for n in news_list[:limit]:
                    # News items are dicts, not objects
                    if isinstance(n, dict):
                        news_items.append({
                            "headline": n.get('headline', '') or '',
                            "summary": n.get('summary', '') or '',
                            "symbols": list(n.get('symbols', [])) or [],
                            "source": n.get('source', '') or '',
                            "created_at": str(n.get('created_at', '')),
                            "url": n.get('url', '') or '',
                        })
                    else:
                        # Fallback for News objects
                        news_items.append({
                            "headline": getattr(n, 'headline', '') or '',
                            "summary": getattr(n, 'summary', '') or '',
                            "symbols": list(getattr(n, 'symbols', [])) or [],
                            "source": getattr(n, 'source', '') or '',
                            "created_at": str(getattr(n, 'created_at', '')),
                            "url": getattr(n, 'url', '') or '',
                        })
            except Exception as e:
                logger.warning(f"Error parsing news response: {e}")
            
            logger.info(f"Found {len(news_items)} news items")
            return news_items
            
        except Exception as e:
            logger.warning(f"Failed to get news: {e}")
            return []
    
    def get_market_sentiment_summary(self, limit: int = 10) -> str:
        """
        Get a summary of recent market news for AI analysis.
        
        Returns:
            Text summary of recent headlines
        """
        news = self.get_news(limit=limit)
        
        if not news:
            return "No recent news available."
        
        lines = ["Recent Market News:"]
        for n in news:
            symbols_str = ", ".join(n["symbols"][:3]) if n["symbols"] else "General"
            lines.append(f"- [{symbols_str}] {n['headline']}")
        
        return "\n".join(lines)
