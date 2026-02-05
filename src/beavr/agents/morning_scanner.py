"""Morning Scanner Agent for pre-market momentum opportunity detection."""

from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, ClassVar, Optional

from pydantic import BaseModel, Field

from beavr.agents.base import AgentContext, AgentProposal, BaseAgent
from beavr.models.morning_candidate import (
    MorningCandidate,
    MorningScanResult,
    ScanType,
)

if TYPE_CHECKING:
    from beavr.db.thesis_repo import ThesisRepository
    from beavr.llm.client import LLMClient

logger = logging.getLogger(__name__)


class ScannerOutput(BaseModel):
    """Structured output from scanner LLM analysis."""
    
    top_picks: list[dict] = Field(
        description="Top 3-5 momentum candidates with analysis"
    )
    market_sentiment: str = Field(
        description="Overall market sentiment: bullish, bearish, neutral"
    )
    conviction_summary: str = Field(
        description="One sentence summary of conviction in today's opportunities"
    )


class MorningScannerAgent(BaseAgent):
    """
    Morning Scanner Agent for pre-market momentum opportunity detection.
    
    Runs during pre-market (4:00 AM - 9:30 AM ET) to identify:
    - Gap ups > 3% on volume
    - Volume surges (2x+ average)
    - Technical breakouts
    - Sector rotation leaders
    - Alignment with active theses
    
    Unlike the v1 swing trader that focused on oversold bounces,
    the Morning Scanner prioritizes STRENGTH and MOMENTUM.
    """
    
    name: ClassVar[str] = "Morning Scanner"
    role: ClassVar[str] = "trader"
    description: ClassVar[str] = "Pre-market momentum opportunity scanner"
    version: ClassVar[str] = "2.0.0"
    
    def __init__(
        self,
        llm: LLMClient,
        gap_threshold_pct: float = 3.0,
        volume_surge_multiple: float = 2.0,
        max_candidates: int = 5,
        thesis_repo: Optional[ThesisRepository] = None,
    ) -> None:
        """
        Initialize the Morning Scanner.
        
        Args:
            llm: LLM client for analysis
            gap_threshold_pct: Minimum gap % to consider (default 3%)
            volume_surge_multiple: Volume multiple vs average (default 2x)
            max_candidates: Maximum candidates to return (default 5)
            thesis_repo: Optional thesis repository for alignment checks
        """
        super().__init__(llm)
        self.gap_threshold_pct = gap_threshold_pct
        self.volume_surge_multiple = volume_surge_multiple
        self.max_candidates = max_candidates
        self.thesis_repo = thesis_repo
    
    def get_system_prompt(self) -> str:
        """Return the scanner's system prompt."""
        return """You are a Morning Scanner agent analyzing pre-market data 
for momentum trading opportunities.

YOUR FOCUS IS MOMENTUM, NOT VALUE.
Look for STRENGTH, not weakness. We are NOT catching falling knives.

WHAT TO LOOK FOR:

1. GAP UPS (3%+ pre-market)
   - Gap on HIGH VOLUME suggests real demand
   - Gap on NEWS has follow-through potential
   - Avoid gaps on no news (often fade)

2. VOLUME SURGES
   - Pre-market volume 2x+ average = institutional interest
   - Volume precedes price movement
   - Unusual volume on breakout = confirmation

3. TECHNICAL BREAKOUTS
   - Breaking multi-day resistance
   - New 52-week highs with volume
   - Consolidation breakouts

4. SECTOR LEADERS
   - If a sector is hot, find the leaders
   - Relative strength vs peers matters
   - Quality companies with momentum

QUALITY FILTERS (MUST PASS):
- Price > $10 (no penny stocks)
- Average volume > 500K shares
- Not halted
- Not gapping on bad news (earnings miss, etc.)

RANKING CRITERIA:
1. Volume confirmation (higher volume = higher rank)
2. Catalyst clarity (clear news/catalyst = higher rank)
3. Technical setup (clean chart = higher rank)
4. Risk/reward (favorable R/R = higher rank)

OUTPUT RULES:
- Return TOP 3-5 candidates only
- Each candidate needs clear entry/target/stop
- If nothing compelling, return empty list
- Be SELECTIVE - quality over quantity"""

    def analyze(self, ctx: AgentContext) -> AgentProposal:
        """
        Analyze pre-market data for momentum opportunities.
        
        Returns an AgentProposal with candidate signals.
        """
        start_time = datetime.now()
        
        # Run the scan
        scan_result = self.scan(ctx)
        
        # Convert to signals for orchestrator compatibility
        signals = []
        for candidate in scan_result.top_candidates:
            if candidate.conviction_score >= 0.6:
                signals.append({
                    "symbol": candidate.symbol,
                    "action": "buy" if candidate.preliminary_direction == "long" else "sell",
                    "conviction": candidate.conviction_score,
                    "reason": candidate.catalyst_summary,
                    "scan_type": candidate.scan_type.value,
                    "target_pct": candidate.preliminary_target_pct,
                    "stop_pct": candidate.preliminary_stop_pct,
                })
        
        processing_time = (datetime.now() - start_time).total_seconds() * 1000
        
        return AgentProposal(
            agent_name=self.name,
            timestamp=datetime.now(),
            signals=signals,
            conviction=sum(c.conviction_score for c in scan_result.candidates[:3]) / 3 if scan_result.candidates else 0,
            rationale=f"Found {len(scan_result.candidates)} momentum candidates. Market sentiment: {scan_result.market_sentiment}",
            risk_score=0.5,
            risk_factors=[],
            model_version=self.version,
            processing_time_ms=processing_time,
            extra={
                "scan_result": scan_result.model_dump(),
            },
        )
    
    def scan(self, ctx: AgentContext) -> MorningScanResult:
        """
        Perform the morning scan.
        
        Args:
            ctx: Current market context
            
        Returns:
            MorningScanResult with ranked candidates
        """
        logger.info("Morning Scanner starting pre-market scan...")
        
        # Step 1: Collect candidates from indicator data
        raw_candidates = self._collect_candidates(ctx)
        logger.info(f"Collected {len(raw_candidates)} raw candidates")
        
        # Step 2: Apply quality filters
        filtered_candidates = self._apply_quality_filters(raw_candidates)
        logger.info(f"After quality filter: {len(filtered_candidates)} candidates")
        
        # Step 3: Check for thesis alignment
        if self.thesis_repo:
            filtered_candidates = self._check_thesis_alignment(filtered_candidates)
        
        # Step 4: Rank candidates
        ranked_candidates = self._rank_candidates(filtered_candidates, ctx)
        
        # Step 5: Limit to max candidates
        top_candidates = ranked_candidates[:self.max_candidates]
        
        # Determine market sentiment from overall data
        market_sentiment = self._assess_market_sentiment(ctx)
        
        logger.info(
            f"Morning scan complete: {len(top_candidates)} candidates, "
            f"sentiment: {market_sentiment}"
        )
        
        return MorningScanResult(
            scan_timestamp=datetime.now(),
            market_open_time=datetime.now().replace(hour=9, minute=30),  # ET
            candidates=top_candidates,
            market_sentiment=market_sentiment,
            total_scanned=len(raw_candidates),
            gaps_up_count=sum(1 for c in top_candidates if c.scan_type == ScanType.GAP_UP),
            gaps_down_count=sum(1 for c in top_candidates if c.scan_type == ScanType.GAP_DOWN),
        )
    
    def _collect_candidates(self, ctx: AgentContext) -> list[MorningCandidate]:
        """Collect initial candidates from context data."""
        candidates = []
        
        for symbol, indicators in ctx.indicators.items():
            current_price = ctx.prices.get(symbol, Decimal(0))
            if current_price == 0:
                continue
            
            # Calculate gap and volume metrics
            change_pct = indicators.get('change_1d', 0) or indicators.get('change_5d', 0) / 5
            avg_volume = indicators.get('avg_volume', 1_000_000)
            current_volume = indicators.get('volume', 0)
            
            # Determine scan type
            scan_type = self._determine_scan_type(change_pct, current_volume, avg_volume, indicators)
            if scan_type is None:
                continue
            
            # Calculate preliminary targets
            atr_pct = indicators.get('atr_pct', 2.0)
            target_pct = min(atr_pct * 2, 10.0)  # 2x ATR, max 10%
            stop_pct = max(atr_pct * 0.75, 2.0)  # 0.75x ATR, min 2%
            
            # Build candidate
            candidate = MorningCandidate(
                symbol=symbol,
                scan_type=scan_type,
                pre_market_price=current_price,
                previous_close=current_price / (1 + Decimal(str(change_pct / 100))),
                pre_market_change_pct=change_pct,
                pre_market_volume=int(current_volume),
                avg_daily_volume=int(avg_volume),
                volume_ratio=current_volume / avg_volume if avg_volume > 0 else 0,
                key_resistance=Decimal(str(indicators.get('resistance_1', 0))) or None,
                key_support=Decimal(str(indicators.get('support_1', 0))) or None,
                rsi_14=indicators.get('rsi_14'),
                sma_20=Decimal(str(indicators.get('sma_20', 0))) or None,
                sma_50=Decimal(str(indicators.get('sma_50', 0))) or None,
                catalyst_summary=self._generate_catalyst_summary(scan_type, change_pct, indicators),
                has_news=False,  # Would need news API integration
                preliminary_direction="long" if change_pct > 0 else "short",
                preliminary_target_pct=target_pct,
                preliminary_stop_pct=stop_pct,
                conviction_score=0.5,  # Will be updated during ranking
                priority_rank=999,  # Will be set during ranking
            )
            
            candidates.append(candidate)
        
        return candidates
    
    def _determine_scan_type(
        self,
        change_pct: float,
        volume: float,
        avg_volume: float,
        indicators: dict,
    ) -> Optional[ScanType]:
        """Determine the scan type based on metrics."""
        volume_ratio = volume / avg_volume if avg_volume > 0 else 0
        
        # Gap up
        if change_pct >= self.gap_threshold_pct:
            return ScanType.GAP_UP
        
        # Gap down (for potential shorts or avoidance)
        if change_pct <= -self.gap_threshold_pct:
            return ScanType.GAP_DOWN
        
        # Volume surge
        if volume_ratio >= self.volume_surge_multiple:
            return ScanType.VOLUME_SURGE
        
        # Breakout (price near/above resistance)
        rsi = indicators.get('rsi_14', 50)
        sma_20 = indicators.get('sma_20', 0)
        price = indicators.get('current_price', 0)
        
        if rsi > 60 and price > sma_20 and change_pct > 1:
            return ScanType.MOMENTUM
        
        return None
    
    def _apply_quality_filters(self, candidates: list[MorningCandidate]) -> list[MorningCandidate]:
        """Apply quality filters to candidates."""
        filtered = []
        
        for c in candidates:
            # Price filter
            if c.pre_market_price < 10:
                c.is_quality_stock = False
                c.quality_notes = "Price below $10"
                continue
            
            if c.pre_market_price > 1000:
                c.is_quality_stock = False
                c.quality_notes = "Price above $1000"
                continue
            
            # Volume filter
            if c.avg_daily_volume < 500_000:
                c.is_quality_stock = False
                c.quality_notes = "Average volume below 500K"
                continue
            
            # Extreme move filter (potential pump & dump)
            if abs(c.pre_market_change_pct) > 30:
                c.extreme_move = True
                c.quality_notes = "Extreme move >30%"
                continue
            
            filtered.append(c)
        
        return filtered
    
    def _check_thesis_alignment(self, candidates: list[MorningCandidate]) -> list[MorningCandidate]:
        """Check if candidates align with active theses."""
        if not self.thesis_repo:
            return candidates
        
        active_theses = self.thesis_repo.get_active()
        thesis_symbols = {t.symbol: t for t in active_theses}
        
        for candidate in candidates:
            if candidate.symbol in thesis_symbols:
                thesis = thesis_symbols[candidate.symbol]
                candidate.has_active_thesis = True
                candidate.thesis_id = thesis.id
                candidate.scan_type = ScanType.THESIS_SETUP
                # Boost conviction for thesis-aligned candidates
                candidate.conviction_score = min(candidate.conviction_score + 0.2, 1.0)
        
        return candidates
    
    def _rank_candidates(self, candidates: list[MorningCandidate], _ctx: AgentContext) -> list[MorningCandidate]:
        """Rank candidates by conviction score."""
        for candidate in candidates:
            score = 0.5  # Base score
            
            # Volume confirmation
            if candidate.volume_ratio >= 2:
                score += 0.15
            elif candidate.volume_ratio >= 1.5:
                score += 0.1
            
            # Gap size (moderate gaps are better than extreme)
            gap = abs(candidate.pre_market_change_pct)
            if 3 <= gap <= 8:
                score += 0.15
            elif 8 < gap <= 15:
                score += 0.1
            
            # RSI momentum (not overbought)
            rsi = candidate.rsi_14 or 50
            if 50 <= rsi <= 70:
                score += 0.1
            elif rsi > 70:
                score -= 0.1  # Overbought penalty
            
            # Thesis alignment bonus
            if candidate.has_active_thesis:
                score += 0.15
            
            # Risk/reward check
            if candidate.preliminary_target_pct > candidate.preliminary_stop_pct * 1.5:
                score += 0.1
            
            candidate.conviction_score = min(max(score, 0), 1.0)
        
        # Sort by conviction score
        candidates.sort(key=lambda c: c.conviction_score, reverse=True)
        
        # Assign ranks
        for i, candidate in enumerate(candidates):
            candidate.priority_rank = i + 1
        
        return candidates
    
    def _assess_market_sentiment(self, ctx: AgentContext) -> str:
        """Assess overall market sentiment from context."""
        regime = ctx.regime or "unknown"
        
        if regime == "bull":
            return "bullish"
        elif regime == "bear":
            return "bearish"
        else:
            # Look at indicator averages
            rsi_values = [
                ind.get('rsi_14', 50) 
                for ind in ctx.indicators.values() 
                if ind.get('rsi_14')
            ]
            
            if rsi_values:
                avg_rsi = sum(rsi_values) / len(rsi_values)
                if avg_rsi > 55:
                    return "bullish"
                elif avg_rsi < 45:
                    return "bearish"
            
            return "neutral"
    
    def _generate_catalyst_summary(
        self,
        scan_type: ScanType,
        change_pct: float,
        indicators: dict,
    ) -> str:
        """Generate a catalyst summary for the candidate."""
        rsi = indicators.get('rsi_14', 50)
        volume_ratio = indicators.get('volume_ratio', 1)
        
        if scan_type == ScanType.GAP_UP:
            return f"Gapping up {change_pct:.1f}% with RSI {rsi:.0f}"
        elif scan_type == ScanType.GAP_DOWN:
            return f"Gapping down {change_pct:.1f}% with RSI {rsi:.0f}"
        elif scan_type == ScanType.VOLUME_SURGE:
            return f"Volume surge {volume_ratio:.1f}x average"
        elif scan_type == ScanType.MOMENTUM:
            return f"Momentum breakout with RSI {rsi:.0f}"
        else:
            return "Technical setup identified"
