"""Due Diligence Agent for comprehensive stock analysis before trading.

The DD Agent runs during NON-MARKET HOURS (overnight) to perform deep research
without time pressure. It classifies opportunities as day trades or swing trades
and generates detailed reports saved for user consumption.

Key responsibilities:
- Deep fundamental and technical analysis
- Trade type classification (day_trade, swing_short, swing_medium, swing_long)
- Generate and persist DD reports in JSON and Markdown formats
- Approve/reject candidates with detailed rationale
"""

from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar, Optional

from pydantic import BaseModel, Field

from beavr.agents.base import AgentContext, AgentProposal, BaseAgent
from beavr.models.dd_report import (
    DayTradePlan,
    DDRecommendation,
    DueDiligenceReport,
    RecommendedTradeType,
    SwingTradePlan,
)
from beavr.models.thesis import TradeThesis

if TYPE_CHECKING:
    from beavr.llm.client import LLMClient

logger = logging.getLogger(__name__)


class DDAnalysisOutput(BaseModel):
    """Structured output from DD LLM analysis."""
    
    # Verdict
    recommendation: str = Field(
        description="Final verdict: 'approve', 'reject', or 'conditional'"
    )
    confidence: float = Field(
        ge=0.0, le=1.0,
        description="Confidence in recommendation (0.0 to 1.0)"
    )
    
    # Trade Type Classification (NEW)
    recommended_trade_type: str = Field(
        description="Trade type: 'day_trade', 'swing_short', 'swing_medium', or 'swing_long'"
    )
    trade_type_rationale: str = Field(
        description="Why this trade type was selected (1-2 sentences)"
    )
    
    # Executive Summary
    executive_summary: str = Field(
        description="2-3 sentence summary of the entire analysis"
    )
    
    # Analysis summaries
    fundamental_summary: str = Field(
        description="Detailed fundamental analysis (3-5 sentences)"
    )
    technical_summary: str = Field(
        description="Detailed technical analysis (3-5 sentences)"
    )
    catalyst_assessment: str = Field(
        description="Deep dive on the catalyst and historical patterns"
    )
    competitive_landscape: Optional[str] = Field(
        default=None,
        description="How company compares to peers"
    )
    
    # Scenario Analysis
    bull_case: Optional[str] = Field(
        default=None,
        description="Best case scenario"
    )
    bear_case: Optional[str] = Field(
        default=None,
        description="Worst case scenario"
    )
    base_case: Optional[str] = Field(
        default=None,
        description="Most likely outcome"
    )
    
    # Risk factors
    risk_factors: list[str] = Field(
        description="Top 3-5 risk factors identified"
    )
    
    # Recommendations
    recommended_entry: float = Field(
        description="Recommended entry price"
    )
    recommended_target: float = Field(
        description="Recommended profit target price"
    )
    recommended_stop: float = Field(
        description="Recommended stop loss price"
    )
    recommended_position_size_pct: float = Field(
        ge=0.01, le=0.30,
        description="Recommended position size as % of portfolio (0.01 to 0.30)"
    )
    
    # Day Trade Plan (if day_trade)
    day_trade_opening_confirmation: Optional[str] = Field(
        default=None,
        description="What to look for in opening range to confirm entry"
    )
    
    # Swing Trade Plan (if swing)
    swing_entry_strategy: Optional[str] = Field(
        default=None,
        description="Entry strategy for swing trade"
    )
    swing_key_dates: Optional[list[str]] = Field(
        default=None,
        description="Key dates to monitor for swing trade"
    )
    
    # Rationale
    primary_rationale: str = Field(
        description="Main reason for the recommendation (1-2 sentences)"
    )
    
    # Conditions (for conditional approvals)
    conditions: Optional[list[str]] = Field(
        default=None,
        description="Conditions that must be met for conditional approval"
    )


class DueDiligenceAgent(BaseAgent):
    """
    Due Diligence Agent for comprehensive pre-trade analysis.
    
    RUNS OVERNIGHT (8 PM - 6 AM ET) to allow for thorough research
    without time pressure. Reports are persisted for user consumption.
    
    The DD Agent is the quality gate before any trade executes.
    It performs deep analysis of:
    - Fundamentals: Real business, reasonable valuation, growth metrics
    - Technicals: Support/resistance, trend, momentum
    - Catalyst verification: Is the catalyst still valid? Timing?
    - Risk assessment: Downside scenarios, known risks
    - Trade type classification: Day trade vs swing (short/medium/long)
    
    No trade executes without DD approval. The agent can:
    - Approve: Trade is good to go
    - Reject: Do not trade, with explanation
    - Conditional: Trade only if certain conditions are met
    """
    
    name: ClassVar[str] = "Due Diligence Agent"
    role: ClassVar[str] = "risk"
    description: ClassVar[str] = "Comprehensive overnight pre-trade analysis and quality gate"
    version: ClassVar[str] = "2.0.0"
    
    # Default report directory
    DEFAULT_REPORT_DIR: ClassVar[str] = "logs/dd_reports"
    
    def __init__(
        self,
        llm: LLMClient,
        min_confidence_threshold: float = 0.65,
        require_positive_rr: bool = True,
        report_dir: Optional[str] = None,
        save_reports: bool = True,
    ) -> None:
        """
        Initialize the DD Agent.
        
        Args:
            llm: LLM client for reasoning
            min_confidence_threshold: Minimum confidence to approve (default 0.65)
            require_positive_rr: Require positive risk/reward ratio
            report_dir: Directory to save reports (default: logs/dd_reports)
            save_reports: Whether to save reports to disk
        """
        super().__init__(llm)
        self.min_confidence_threshold = min_confidence_threshold
        self.require_positive_rr = require_positive_rr
        self.report_dir = Path(report_dir or self.DEFAULT_REPORT_DIR)
        self.save_reports = save_reports
    
    def get_system_prompt(self) -> str:
        """Return the DD Agent's system prompt."""
        return """You are a senior research analyst conducting comprehensive due diligence on
trading candidates. Your research runs OVERNIGHT, allowing for thorough analysis
without time pressure. Your DD reports are saved for human review.

ROLE:
- Conduct deep fundamental and technical analysis
- Classify opportunities as day trade or swing trade
- Generate detailed reports for human consumption
- Approve or reject candidates with clear rationale

RESEARCH PHILOSOPHY:
"Every trade must have a documented thesis that a human can read and validate."

You have TIME. Unlike market-hours decisions, overnight DD should be thorough.
Better to research deeply than to surface trade quickly.

ANALYSIS FRAMEWORK:

1. FUNDAMENTAL ANALYSIS (30%)
   - Revenue and earnings trends
   - Valuation (P/E, P/S vs sector)
   - Competitive position
   - Management quality signals
   - Balance sheet health

2. TECHNICAL ANALYSIS (25%)
   - Multi-timeframe trend (daily, weekly, monthly)
   - Key support/resistance levels
   - Volume patterns
   - Momentum indicators (RSI, MACD)
   - Chart patterns

3. CATALYST ASSESSMENT (25%)
   - Is the catalyst real and verified?
   - Historical price reaction to similar catalysts
   - Market expectations (priced in?)
   - Timing and clarity

4. RISK ASSESSMENT (20%)
   - Maximum realistic downside
   - Known upcoming risks
   - Liquidity assessment
   - Correlation to portfolio

TRADE TYPE DECISION:
Based on your analysis, classify as:

DAY_TRADE if:
- Catalyst is happening TODAY
- Pre-market gap > 3%
- High volume expected
- Can capture 1-3% in opening hour
- Must include opening_confirmation for Power Hour

SWING_SHORT (1-2 weeks) if:
- Catalyst in next 1-2 weeks
- Expect 5-10% move
- Clear entry/exit setup

SWING_MEDIUM (1-3 months) if:
- Larger catalyst or theme play
- Expect 10-20% move
- Can withstand short-term volatility

SWING_LONG (3-12 months) if:
- Major business transformation
- Expect 20-50% move
- Requires highest conviction

APPROVAL CRITERIA:
APPROVE if:
- Risk/reward > 1.5:1
- Catalyst is specific and verifiable
- Technical setup supports direction
- Confidence > 65%

REJECT if:
- Thesis is vague or speculative
- Risk/reward unfavorable
- Buying into major resistance
- Too correlated with existing positions
- Red flags in fundamentals

CRITICAL: Always explain your reasoning in detail.
Capital preservation is paramount - if in doubt, REJECT."""

    def analyze(self, _ctx: AgentContext) -> AgentProposal:
        """
        Analyze context and produce recommendations.
        
        Note: For DD analysis, use analyze_thesis() or analyze_candidate()
        methods instead, which take specific inputs.
        """
        # This method is required by BaseAgent but DD Agent
        # typically uses analyze_thesis() or analyze_candidate()
        return AgentProposal(
            agent_name=self.name,
            timestamp=datetime.now(),
            signals=[],
            conviction=0.0,
            rationale="DD Agent requires specific thesis or candidate input",
            risk_score=1.0,
            risk_factors=["No input provided"],
            model_version=self.version,
        )
    
    def analyze_thesis(
        self,
        thesis: TradeThesis,
        ctx: AgentContext,
        fundamental_data: Optional[dict] = None,
    ) -> DueDiligenceReport:
        """
        Perform due diligence on a trade thesis.
        
        Args:
            thesis: The trade thesis to analyze
            ctx: Current market context
            fundamental_data: Optional pre-fetched fundamental data
            
        Returns:
            DueDiligenceReport with recommendation (also saved to disk)
        """
        start_time = datetime.now()
        symbol = thesis.symbol
        
        logger.info(f"DD Agent analyzing thesis for {symbol}...")
        
        # Build comprehensive prompt
        user_prompt = self._build_dd_prompt(thesis, ctx, fundamental_data)
        
        try:
            # Get structured analysis from LLM
            analysis: DDAnalysisOutput = self.llm.reason(
                system_prompt=self.get_system_prompt(),
                user_prompt=user_prompt,
                output_schema=DDAnalysisOutput,
            )
            
            processing_time = (datetime.now() - start_time).total_seconds() * 1000
            research_time = int(processing_time / 1000 / 60)  # Convert to minutes
            
            # Convert recommendation string to enum
            try:
                recommendation = DDRecommendation(analysis.recommendation.lower())
            except ValueError:
                logger.warning(f"Invalid recommendation: {analysis.recommendation}, defaulting to reject")
                recommendation = DDRecommendation.REJECT
            
            # Convert trade type string to enum
            try:
                trade_type = RecommendedTradeType(analysis.recommended_trade_type.lower())
            except ValueError:
                logger.warning(f"Invalid trade type: {analysis.recommended_trade_type}, defaulting to swing_short")
                trade_type = RecommendedTradeType.SWING_SHORT
            
            # Apply additional validation rules
            recommendation, analysis = self._apply_validation_rules(
                recommendation, analysis, thesis
            )
            
            # Build day trade plan if applicable
            day_trade_plan = None
            if trade_type == RecommendedTradeType.DAY_TRADE:
                day_trade_plan = DayTradePlan(
                    opening_range_confirmation=analysis.day_trade_opening_confirmation or "Price holding above pre-market levels",
                    scalp_target_pct=1.5,
                    full_target_pct=float((analysis.recommended_target - analysis.recommended_entry) / analysis.recommended_entry * 100),
                    stop_pct=float((analysis.recommended_entry - analysis.recommended_stop) / analysis.recommended_entry * 100),
                )
            
            # Build swing trade plan if applicable
            swing_trade_plan = None
            if trade_type != RecommendedTradeType.DAY_TRADE:
                swing_trade_plan = SwingTradePlan(
                    entry_strategy=analysis.swing_entry_strategy or "Enter at recommended price or better",
                    key_dates_to_monitor=analysis.swing_key_dates or [],
                )
            
            # Build the DD report
            report = DueDiligenceReport(
                thesis_id=thesis.id,
                symbol=symbol,
                company_name=fundamental_data.get("company_name") if fundamental_data else None,
                sector=fundamental_data.get("sector") if fundamental_data else None,
                timestamp=datetime.now(),
                recommended_trade_type=trade_type,
                trade_type_rationale=analysis.trade_type_rationale,
                recommendation=recommendation,
                confidence=analysis.confidence,
                executive_summary=analysis.executive_summary,
                fundamental_summary=analysis.fundamental_summary,
                technical_summary=analysis.technical_summary,
                catalyst_assessment=analysis.catalyst_assessment,
                competitive_landscape=analysis.competitive_landscape,
                risk_factors=analysis.risk_factors,
                bull_case=analysis.bull_case,
                bear_case=analysis.bear_case,
                base_case=analysis.base_case,
                market_cap=Decimal(str(fundamental_data.get("market_cap", 0))) if fundamental_data and fundamental_data.get("market_cap") else None,
                pe_ratio=fundamental_data.get("pe_ratio") if fundamental_data else None,
                revenue_growth=fundamental_data.get("revenue_growth") if fundamental_data else None,
                institutional_ownership=fundamental_data.get("institutional_ownership") if fundamental_data else None,
                recommended_entry=Decimal(str(analysis.recommended_entry)),
                recommended_target=Decimal(str(analysis.recommended_target)),
                recommended_stop=Decimal(str(analysis.recommended_stop)),
                recommended_position_size_pct=analysis.recommended_position_size_pct,
                day_trade_plan=day_trade_plan,
                swing_trade_plan=swing_trade_plan,
                approval_rationale=analysis.primary_rationale if recommendation == DDRecommendation.APPROVE else None,
                rejection_rationale=analysis.primary_rationale if recommendation == DDRecommendation.REJECT else None,
                conditions=analysis.conditions if recommendation == DDRecommendation.CONDITIONAL else None,
                research_time_minutes=max(research_time, 1),  # At least 1 minute
                data_sources_used=["technical_indicators", "thesis_data", "fundamental_data"],
                processing_time_ms=processing_time,
                llm_model=getattr(self.llm, 'config', {}).model if hasattr(self.llm, 'config') else 'unknown',
            )
            
            # Save report to disk
            if self.save_reports:
                try:
                    json_path, md_path = report.save(self.report_dir)
                    logger.info(f"DD report saved: {md_path}")
                except Exception as e:
                    logger.error(f"Failed to save DD report: {e}")
            
            logger.info(
                f"DD complete for {symbol}: {recommendation.value.upper()} "
                f"[{trade_type.value}] (confidence: {analysis.confidence:.0%})"
            )
            
            return report
            
        except Exception as e:
            logger.error(f"DD analysis failed for {symbol}: {e}")
            
            # Return a rejection report on error
            return DueDiligenceReport(
                thesis_id=thesis.id,
                symbol=symbol,
                timestamp=datetime.now(),
                recommended_trade_type=RecommendedTradeType.SWING_SHORT,
                trade_type_rationale="Unable to classify - analysis failed",
                recommendation=DDRecommendation.REJECT,
                confidence=0.0,
                executive_summary=f"Analysis failed due to error: {e}",
                fundamental_summary=f"Analysis error: {e}",
                technical_summary="Unable to complete technical analysis",
                catalyst_assessment="Unable to assess catalyst",
                risk_factors=["DD analysis failed", str(e)],
                recommended_entry=thesis.entry_price_target,
                recommended_target=thesis.profit_target,
                recommended_stop=thesis.stop_loss,
                recommended_position_size_pct=0.05,
                rejection_rationale=f"DD analysis failed: {e}",
                data_sources_used=[],
                processing_time_ms=(datetime.now() - start_time).total_seconds() * 1000,
            )
    
    def _build_dd_prompt(
        self,
        thesis: TradeThesis,
        ctx: AgentContext,
        fundamental_data: Optional[dict],
    ) -> str:
        """Build comprehensive DD prompt."""
        symbol = thesis.symbol
        
        # Get technical indicators for the symbol
        indicators = ctx.indicators.get(symbol, {})
        current_price = ctx.prices.get(symbol, Decimal(0))
        
        # Format fundamental data
        fundamentals_text = "Not available"
        if fundamental_data:
            fundamentals_text = f"""
Market Cap: ${fundamental_data.get('market_cap', 'N/A'):,.0f}
P/E Ratio: {fundamental_data.get('pe_ratio', 'N/A')}
P/S Ratio: {fundamental_data.get('ps_ratio', 'N/A')}
Revenue Growth (YoY): {fundamental_data.get('revenue_growth', 'N/A'):.1%}
Profit Margin: {fundamental_data.get('profit_margin', 'N/A')}
Debt/Equity: {fundamental_data.get('debt_equity', 'N/A')}
Institutional Ownership: {fundamental_data.get('institutional_ownership', 'N/A'):.1%}
"""
        
        # Format technical data
        technicals_text = f"""
Current Price: ${current_price:.2f}
RSI(14): {indicators.get('rsi_14', 'N/A')}
SMA(20): ${indicators.get('sma_20', 'N/A')}
SMA(50): ${indicators.get('sma_50', 'N/A')}
Price vs SMA20: {indicators.get('price_vs_sma20', 'N/A')}%
ATR%: {indicators.get('atr_pct', 'N/A')}%
Bollinger Band %: {indicators.get('bb_pct', 'N/A')}
5-day Change: {indicators.get('change_5d', 'N/A'):+.1f}%
20-day Change: {indicators.get('change_20d', 'N/A'):+.1f}%
"""
        
        return f"""
ANALYZE THIS TRADE THESIS FOR {symbol}

=== THESIS DETAILS ===
Trade Type: {thesis.trade_type.value}
Direction: {thesis.direction.value}
Entry Rationale: {thesis.entry_rationale}

Catalyst: {thesis.catalyst}
Catalyst Date: {thesis.catalyst_date or 'Not specified'}

Entry Target: ${thesis.entry_price_target:.2f}
Profit Target: ${thesis.profit_target:.2f} (+{thesis.target_pct:.1f}%)
Stop Loss: ${thesis.stop_loss:.2f} (-{thesis.stop_pct:.1f}%)
Risk/Reward: {thesis.risk_reward_ratio:.1f}:1

Expected Exit: {thesis.expected_exit_date}
Max Hold: {thesis.max_hold_date}

Invalidation Conditions:
{chr(10).join('- ' + c for c in thesis.invalidation_conditions) or '- None specified'}

=== FUNDAMENTAL DATA ===
{fundamentals_text}

=== TECHNICAL DATA ===
{technicals_text}

=== PORTFOLIO CONTEXT ===
Portfolio Value: ${ctx.portfolio_value:,.2f}
Cash Available: ${ctx.cash:,.2f}
Current Drawdown: {ctx.current_drawdown:.1%}
Risk Budget: {ctx.risk_budget:.1%}

Current Positions: {', '.join(ctx.positions.keys()) if ctx.positions else 'None'}
Market Regime: {ctx.regime or 'Unknown'}

=== INSTRUCTIONS ===
Analyze this thesis thoroughly and provide your recommendation.
Remember: You are the last line of defense. If in doubt, REJECT.
Focus on capital preservation over opportunity capture.
{self._format_directives(ctx)}
"""
    
    @staticmethod
    def _format_directives(ctx: AgentContext) -> str:
        """Format portfolio directives for prompt injection."""
        from beavr.orchestrator.portfolio_config import format_directives_for_prompt

        return format_directives_for_prompt(ctx.directives)

    def _apply_validation_rules(
        self,
        recommendation: DDRecommendation,
        analysis: DDAnalysisOutput,
        thesis: TradeThesis,
    ) -> tuple[DDRecommendation, DDAnalysisOutput]:
        """
        Apply additional validation rules to the recommendation.
        
        These rules override the LLM's recommendation in certain cases.
        """
        # Rule 1: Enforce minimum confidence threshold
        if recommendation == DDRecommendation.APPROVE and analysis.confidence < self.min_confidence_threshold:
            logger.info(
                f"Downgrading to CONDITIONAL: confidence {analysis.confidence:.0%} "
                f"< threshold {self.min_confidence_threshold:.0%}"
            )
            recommendation = DDRecommendation.CONDITIONAL
            if not analysis.conditions:
                analysis.conditions = [
                    f"Confidence below threshold ({analysis.confidence:.0%} < {self.min_confidence_threshold:.0%})"
                ]
        
        # Rule 2: Check risk/reward ratio
        if self.require_positive_rr:
            rr_ratio = thesis.risk_reward_ratio
            if rr_ratio < 1.5 and recommendation == DDRecommendation.APPROVE:
                logger.info(f"Downgrading to CONDITIONAL: R/R ratio {rr_ratio:.1f} < 1.5")
                recommendation = DDRecommendation.CONDITIONAL
                if not analysis.conditions:
                    analysis.conditions = []
                analysis.conditions.append(f"Improve entry for better R/R (current: {rr_ratio:.1f}:1)")
        
        return recommendation, analysis
    
    def quick_dd(
        self,
        _symbol: str,
        current_price: Decimal,
        indicators: dict,
        catalyst: str,
    ) -> tuple[bool, str]:
        """
        Perform quick DD without full thesis (for momentum plays).
        
        Returns:
            Tuple of (approved, rationale)
        """
        # Quick quality checks
        rsi = indicators.get('rsi_14', 50)
        sma_50 = indicators.get('sma_50', 0)
        
        # Reject if extremely overbought
        if rsi > 80:
            return False, f"Rejected: RSI extremely overbought ({rsi:.0f})"
        
        # Reject if too far extended from moving average
        if sma_50 > 0:
            extension = float((current_price - Decimal(str(sma_50))) / Decimal(str(sma_50)) * 100)
            if extension > 30:
                return False, f"Rejected: Price extended {extension:.0f}% above 50 SMA"
        
        # Basic approval for momentum plays
        if rsi < 70 and catalyst:
            return True, f"Quick DD approved: RSI {rsi:.0f}, catalyst: {catalyst[:50]}"
        
        return False, "Quick DD rejected: Insufficient momentum criteria"
