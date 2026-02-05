"""News Monitor Agent for continuous market event monitoring.

The News Monitor runs 24/7, scanning for market-moving events including:
- Earnings announcements and upcoming reports
- SEC filings (8-K, 10-K/Q)
- Analyst upgrades/downgrades
- Macro economic releases
- News catalysts

Events are classified by importance and forwarded to the Thesis Generator
for potential trading hypothesis formation.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any, ClassVar, Optional

from pydantic import BaseModel, Field

from beavr.agents.base import AgentContext, AgentProposal, BaseAgent
from beavr.models.market_event import (
    EventImportance,
    EventType,
    MarketEvent,
)

if TYPE_CHECKING:
    from beavr.db.events_repo import EventsRepository
    from beavr.llm.client import LLMClient

logger = logging.getLogger(__name__)


class EventClassification(BaseModel):
    """Structured output from LLM event classification."""
    
    is_actionable: bool = Field(
        description="Whether this event is actionable for trading"
    )
    event_type: str = Field(
        description="Event type classification"
    )
    importance: str = Field(
        description="Importance level: high, medium, or low"
    )
    direction_implied: str = Field(
        description="Expected price direction: positive, negative, neutral"
    )
    magnitude: str = Field(
        description="Expected magnitude: high (5%+), medium (2-5%), low (<2%)"
    )
    urgency: str = Field(
        description="Time window: immediate, days, weeks"
    )
    summary: str = Field(
        description="Brief summary of the event's trading implications"
    )
    affected_symbols: list[str] = Field(
        default_factory=list,
        description="List of symbols affected by this event"
    )


class NewsMonitorAgent(BaseAgent):
    """
    News Monitor Agent for continuous market event monitoring.
    
    Operates 24/7 (market hours agnostic) in the continuous research pipeline.
    Monitors:
    - Alpaca News API for real-time headlines
    - Earnings calendars for upcoming/announced earnings
    - SEC EDGAR for regulatory filings
    - Macro data releases (Fed, CPI, jobs)
    
    Events are classified and stored for the Thesis Generator to process.
    """
    
    name: ClassVar[str] = "News Monitor"
    role: ClassVar[str] = "analyst"
    description: ClassVar[str] = "Continuous market event monitoring and classification"
    version: ClassVar[str] = "2.0.0"
    
    # System prompt for the News Monitor
    SYSTEM_PROMPT: ClassVar[str] = """You are a financial news analyst for an automated trading system.
Your job is to classify incoming news and events by their potential market impact.

ROLE:
- Monitor market events (earnings, filings, news, macro releases)
- Classify events by type and importance
- Flag actionable events for the trading pipeline
- DO NOT make trading decisions—only surface information

ANALYSIS FRAMEWORK:
For each event, assess:

1. EVENT TYPE: earnings_announced | earnings_upcoming | guidance_change | 
   analyst_upgrade | analyst_downgrade | insider_buy | insider_sell |
   sec_filing | macro_release | news_catalyst | other
   
2. IMPORTANCE: high | medium | low
   - HIGH: Could drive 5%+ move in liquid stock
   - MEDIUM: Could drive 2-5% move
   - LOW: Unlikely to drive significant move
   
3. ACTIONABILITY: Is this something we can trade?
   - Specific symbol affected?
   - Clear direction implied?
   - Timing known?

4. URGENCY: immediate | days | weeks
   - When will this impact price?

CONSTRAINTS:
- Only flag events rated MEDIUM or higher importance
- Do not speculate beyond what the news states
- If uncertain about classification, default to LOWER importance
- Never recommend trades—only classify and describe

Be precise and factual. We need actionable intelligence, not speculation."""

    def __init__(
        self,
        llm: LLMClient,
        poll_interval_minutes: int = 15,
        importance_threshold: EventImportance = EventImportance.MEDIUM,
        events_repo: Optional[EventsRepository] = None,
    ) -> None:
        """
        Initialize the News Monitor.
        
        Args:
            llm: LLM client for event classification
            poll_interval_minutes: How often to poll for news
            importance_threshold: Minimum importance to surface events
            events_repo: Repository for storing events
        """
        super().__init__(llm)
        self.poll_interval_minutes = poll_interval_minutes
        self.importance_threshold = importance_threshold
        self.events_repo = events_repo
    
    def get_system_prompt(self) -> str:
        """Return the agent's system prompt."""
        return self.SYSTEM_PROMPT
    
    def analyze(self, ctx: AgentContext) -> AgentProposal:
        """
        Analyze current news and events.
        
        This is called by the orchestrator during the analysis phase.
        """
        start_time = datetime.now()
        
        # Extract news events from context
        raw_events = ctx.events
        
        if not raw_events:
            return AgentProposal(
                agent_name=self.name,
                timestamp=datetime.now(),
                signals=[],
                conviction=0.0,
                rationale="No new events to process",
                risk_score=0.0,
                risk_factors=[],
                model_version=self.version,
            )
        
        # Process and classify events
        classified_events = []
        high_priority_events = []
        
        for raw_event in raw_events:
            try:
                event = self.classify_event(raw_event)
                if event:
                    classified_events.append(event)
                    if event.importance == EventImportance.HIGH:
                        high_priority_events.append(event)
            except Exception as e:
                logger.warning(f"Failed to classify event: {e}")
                continue
        
        # Store events if repository available
        if self.events_repo and classified_events:
            for event in classified_events:
                try:
                    self.events_repo.save(event)
                except Exception as e:
                    logger.error(f"Failed to save event: {e}")
        
        processing_time = (datetime.now() - start_time).total_seconds() * 1000
        
        return AgentProposal(
            agent_name=self.name,
            timestamp=datetime.now(),
            signals=[],  # News Monitor doesn't generate trading signals
            conviction=len(high_priority_events) / max(len(classified_events), 1),
            rationale=f"Processed {len(classified_events)} events, {len(high_priority_events)} high priority",
            risk_score=0.0,
            risk_factors=[],
            model_version=self.version,
            processing_time_ms=processing_time,
            extra={
                "events_processed": len(classified_events),
                "high_priority_count": len(high_priority_events),
                "events": [e.model_dump() for e in classified_events[:10]],  # Limit to 10
            },
        )
    
    def classify_event(
        self,
        raw_event: dict[str, Any],
    ) -> Optional[MarketEvent]:
        """
        Classify a raw news event using LLM.
        
        Args:
            raw_event: Raw event data from news source
            
        Returns:
            Classified MarketEvent or None if not actionable
        """
        headline = raw_event.get("headline", raw_event.get("title", ""))
        summary = raw_event.get("summary", raw_event.get("content", ""))
        source = raw_event.get("source", "unknown")
        symbols = raw_event.get("symbols", [])
        
        if not headline:
            return None
        
        # Build the classification prompt
        user_prompt = f"""Classify this market event:

HEADLINE: {headline}

SUMMARY: {summary[:500] if summary else "No summary available"}

SOURCE: {source}

RELATED SYMBOLS: {', '.join(symbols) if symbols else 'None specified'}

Respond with your classification in JSON format."""

        try:
            classification: EventClassification = self.llm.reason(
                system_prompt=self.get_system_prompt(),
                user_prompt=user_prompt,
                output_schema=EventClassification,
            )
            
            # Skip non-actionable events
            if not classification.is_actionable:
                logger.info(f"  ❌ Not actionable: {headline[:60]}...")
                return None
            
            # Skip low importance events based on threshold
            importance = EventImportance(classification.importance.lower())
            if self._below_threshold(importance):
                logger.info(f"  ⬇️ Below threshold ({importance.value}): {headline[:60]}...")
                return None
            
            # Convert to EventType enum
            try:
                event_type = EventType(classification.event_type.lower())
            except ValueError:
                event_type = EventType.OTHER
            
            # Create MarketEvent
            symbol = classification.affected_symbols[0] if classification.affected_symbols else None
            
            return MarketEvent(
                event_type=event_type,
                symbol=symbol,
                headline=headline,
                summary=classification.summary,
                source=source,
                url=raw_event.get("url"),
                timestamp=datetime.now(),
                importance=importance,
                raw_data=raw_event,
            )
            
        except Exception as e:
            logger.warning(f"LLM classification failed: {e}")
            # Fall back to simple heuristic classification
            return self._heuristic_classify(raw_event)
    
    def _below_threshold(self, importance: EventImportance) -> bool:
        """Check if importance is below the configured threshold."""
        importance_order = [EventImportance.LOW, EventImportance.MEDIUM, EventImportance.HIGH]
        return importance_order.index(importance) < importance_order.index(self.importance_threshold)
    
    def _heuristic_classify(
        self,
        raw_event: dict[str, Any],
    ) -> Optional[MarketEvent]:
        """
        Fall back heuristic classification when LLM fails.
        
        Uses keyword matching for basic classification.
        """
        headline = raw_event.get("headline", "").lower()
        
        # Keyword-based classification
        if any(w in headline for w in ["earnings", "quarter", "revenue", "eps"]):
            event_type = EventType.EARNINGS_ANNOUNCED
            importance = EventImportance.HIGH
        elif any(w in headline for w in ["upgrade", "buy rating", "outperform"]):
            event_type = EventType.ANALYST_UPGRADE
            importance = EventImportance.MEDIUM
        elif any(w in headline for w in ["downgrade", "sell rating", "underperform"]):
            event_type = EventType.ANALYST_DOWNGRADE
            importance = EventImportance.MEDIUM
        elif any(w in headline for w in ["insider", "purchase", "bought shares"]):
            event_type = EventType.INSIDER_BUY
            importance = EventImportance.MEDIUM
        elif any(w in headline for w in ["sec", "filing", "8-k", "10-k", "10-q"]):
            event_type = EventType.SEC_FILING
            importance = EventImportance.LOW
        elif any(w in headline for w in ["fed", "interest rate", "inflation", "cpi", "jobs"]):
            event_type = EventType.MACRO_RELEASE
            importance = EventImportance.HIGH
        else:
            # Not enough keywords to classify
            return None
        
        if self._below_threshold(importance):
            return None
        
        return MarketEvent(
            event_type=event_type,
            symbol=raw_event.get("symbols", [None])[0],
            headline=raw_event.get("headline", ""),
            summary=raw_event.get("summary", ""),
            source=raw_event.get("source", "unknown"),
            timestamp=datetime.now(),
            importance=importance,
            raw_data=raw_event,
        )
    
    def monitor_cycle(
        self,
        news_data: list[dict[str, Any]],
    ) -> list[MarketEvent]:
        """
        Run a single monitoring cycle.
        
        Args:
            news_data: Raw news data from sources
            
        Returns:
            List of classified and actionable MarketEvents
        """
        events = []
        
        for raw_event in news_data:
            try:
                event = self.classify_event(raw_event)
                if event:
                    events.append(event)
                    logger.info(f"News Monitor: {event.importance.value.upper()} - {event.headline[:80]}")
                    
                    # Save to repository if available
                    if self.events_repo:
                        self.events_repo.save(event)
                        
            except Exception as e:
                logger.warning(f"Failed to process event: {e}")
                continue
        
        return events
