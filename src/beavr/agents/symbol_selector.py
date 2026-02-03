"""Symbol Selector Agent - decides which symbols to trade.

This agent analyzes market movers, news, and current conditions to
automatically select the best symbols for trading.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import ClassVar, Optional

from pydantic import BaseModel, Field

from beavr.agents.base import AgentContext, AgentProposal, BaseAgent

logger = logging.getLogger(__name__)


class SymbolSelection(BaseModel):
    """Structured output from symbol selection."""

    selected_symbols: list[str] = Field(
        description="List of 5-8 symbols to trade today",
        min_length=3,
        max_length=10,
    )
    reasoning: str = Field(
        description="Brief explanation of why these symbols were selected"
    )
    market_theme: str = Field(
        description="Today's dominant market theme (e.g., 'tech selloff', 'rotation to value', 'broad rally')"
    )
    risk_assessment: str = Field(
        description="Overall market risk level: low, medium, high, extreme"
    )


class SymbolSelectorAgent(BaseAgent):
    """
    Symbol Selector agent that decides which symbols to trade.
    
    Analyzes:
    - Top gainers and losers
    - Most active stocks
    - Recent news headlines
    - Current positions
    
    Selects a focused list of 5-8 symbols for the trading session.
    """

    name: ClassVar[str] = "Symbol Selector"
    role: ClassVar[str] = "selector"
    description: ClassVar[str] = "Selects optimal symbols to trade based on market conditions"
    version: ClassVar[str] = "0.1.0"

    def __init__(
        self,
        llm: "LLMClient",
        screener: Optional["MarketScreener"] = None,
        news_scanner: Optional["NewsScanner"] = None,
    ):
        """Initialize with LLM and optional data sources."""
        super().__init__(llm)
        self.screener = screener
        self.news_scanner = news_scanner

    def get_system_prompt(self) -> str:
        return """You are a symbol selection agent for an automated trading system.
Your job is to analyze market data and select the best 5-8 symbols to trade today.

SELECTION CRITERIA:
1. LIQUIDITY: Prefer liquid stocks (high volume, tight spreads)
2. VOLATILITY: Look for stocks with tradeable volatility (not too calm, not too extreme)
3. OPPORTUNITY: Focus on symbols with clear technical setups or catalysts
4. DIVERSIFICATION: Don't over-concentrate in one sector
5. PRICE: Prefer stocks $10-$300 (easier to trade reasonable position sizes)

ALWAYS INCLUDE:
- SPY or QQQ for market context and hedging
- At least one symbol from your current positions (if any)

AVOID:
- Penny stocks (< $5) - manipulation risk
- Extreme movers (> 50% change) - often pump & dumps
- Illiquid stocks - hard to exit
- Stocks with only bad news and no technical support

NEWS INTERPRETATION:
- Positive earnings surprise → potential momentum play
- Sector rotation news → look at affected sectors
- Macro news (Fed, inflation) → affects entire market, adjust risk

OUTPUT: Select 5-8 symbols that offer the best risk/reward opportunities today."""

    def analyze(self, ctx: AgentContext) -> AgentProposal:
        """Analyze market and select symbols."""
        start_time = datetime.now()
        
        # Gather market data
        market_data = self._gather_market_data(ctx)
        
        # Build prompt
        user_prompt = self._build_selection_prompt(ctx, market_data)
        
        logger.info("Symbol Selector analyzing market opportunities...")
        
        try:
            # Get structured selection from LLM
            selection: SymbolSelection = self.llm.reason(
                system_prompt=self.get_system_prompt(),
                user_prompt=user_prompt,
                output_schema=SymbolSelection,
            )
            
            processing_time = (datetime.now() - start_time).total_seconds() * 1000
            
            logger.info(
                f"Selected {len(selection.selected_symbols)} symbols: "
                f"{selection.selected_symbols}"
            )
            logger.info(f"Market theme: {selection.market_theme}")
            logger.info(f"Risk assessment: {selection.risk_assessment}")
            
            return AgentProposal(
                agent_name=self.name,
                timestamp=datetime.now(),
                signals=[],  # Symbol selector doesn't produce trading signals
                conviction=0.8,
                rationale=selection.reasoning,
                risk_score=self._risk_to_score(selection.risk_assessment),
                risk_factors=[f"Market theme: {selection.market_theme}"],
                model_version=self.version,
                processing_time_ms=processing_time,
                extra={
                    "selected_symbols": selection.selected_symbols,
                    "market_theme": selection.market_theme,
                    "risk_assessment": selection.risk_assessment,
                },
            )
            
        except Exception as e:
            logger.error(f"Symbol Selector failed: {e}")
            # Fallback to safe defaults
            return AgentProposal(
                agent_name=self.name,
                timestamp=datetime.now(),
                signals=[],
                conviction=0.5,
                rationale=f"Selection failed: {e}. Using default symbols.",
                risk_score=0.5,
                risk_factors=["Symbol selection failed"],
                model_version=self.version,
                processing_time_ms=(datetime.now() - start_time).total_seconds() * 1000,
                extra={
                    "selected_symbols": ["SPY", "QQQ", "AAPL", "MSFT", "GOOGL"],
                    "market_theme": "unknown",
                    "risk_assessment": "medium",
                },
            )

    def _gather_market_data(self, ctx: AgentContext) -> dict:
        """Gather market movers and news."""
        data = {
            "gainers": [],
            "losers": [],
            "most_active": [],
            "news": [],
        }
        
        # Get market movers
        if self.screener:
            try:
                movers = self.screener.get_market_movers(top_n=15)
                data["gainers"] = [
                    {"symbol": m.symbol, "change": m.percent_change, "price": float(m.price)}
                    for m in movers.top_gainers[:10]
                ]
                data["losers"] = [
                    {"symbol": m.symbol, "change": m.percent_change, "price": float(m.price)}
                    for m in movers.top_losers[:10]
                ]
                data["most_active"] = [
                    {"symbol": m.symbol, "volume": m.volume}
                    for m in movers.most_active[:10]
                ]
            except Exception as e:
                logger.warning(f"Failed to get market movers: {e}")
        
        # Get news
        if self.news_scanner:
            try:
                data["news"] = self.news_scanner.get_news(limit=10)
            except Exception as e:
                logger.warning(f"Failed to get news: {e}")
        
        return data

    def _build_selection_prompt(self, ctx: AgentContext, market_data: dict) -> str:
        """Build the selection prompt."""
        # Format gainers
        gainers_text = "\n".join(
            f"  {g['symbol']}: {g['change']:+.1f}% @ ${g['price']:.2f}"
            for g in market_data["gainers"][:8]
        ) or "  (no data)"
        
        # Format losers
        losers_text = "\n".join(
            f"  {l['symbol']}: {l['change']:+.1f}% @ ${l['price']:.2f}"
            for l in market_data["losers"][:8]
        ) or "  (no data)"
        
        # Format most active
        active_text = "\n".join(
            f"  {a['symbol']}: {a['volume']:,} volume" if a['volume'] else f"  {a['symbol']}"
            for a in market_data["most_active"][:8]
        ) or "  (no data)"
        
        # Format news
        news_text = "\n".join(
            f"  - [{', '.join(n['symbols'][:3]) if n['symbols'] else 'Market'}] {n['headline'][:80]}"
            for n in market_data["news"][:6]
        ) or "  (no news)"
        
        # Format current positions
        positions_text = "\n".join(
            f"  {symbol}: {float(shares):.2f} shares"
            for symbol, shares in ctx.positions.items()
        ) or "  (no positions)"
        
        return f"""
DATE: {ctx.current_date}

PORTFOLIO STATE:
- Cash: ${ctx.cash:,.2f}
- Portfolio Value: ${ctx.portfolio_value:,.2f}
- Current Drawdown: {ctx.current_drawdown:.1%}

CURRENT POSITIONS:
{positions_text}

TODAY'S TOP GAINERS:
{gainers_text}

TODAY'S TOP LOSERS:
{losers_text}

MOST ACTIVE BY VOLUME:
{active_text}

RECENT NEWS:
{news_text}

Based on this data, select 5-8 symbols that offer the best trading opportunities today.
Consider:
1. Which movers have sustainable momentum vs pump-and-dumps?
2. Which losers might be oversold and ready to bounce?
3. What does the news suggest about sector rotation?
4. Include SPY or QQQ for market context.
5. Include any current positions that need management.
"""

    def _risk_to_score(self, risk_level: str) -> float:
        """Convert risk level to numeric score."""
        mapping = {
            "low": 0.2,
            "medium": 0.5,
            "high": 0.7,
            "extreme": 0.9,
        }
        return mapping.get(risk_level.lower(), 0.5)
