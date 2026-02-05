"""Trade Executor Agent for order execution with power hour logic.

The Trade Executor converts approved trades into actual orders via Alpaca API.

Key responsibilities:
- Wait 5 minutes after market open (opening range)
- Validate opening range confirms thesis direction
- Calculate position sizes
- Execute orders with stop loss and take profit attached
- Record keeping with thesis/DD linkage
"""

from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING, ClassVar, Optional

from pydantic import BaseModel, Field

from beavr.agents.base import AgentContext, AgentProposal, BaseAgent
from beavr.models.dd_report import DueDiligenceReport
from beavr.models.thesis import TradeDirection, TradeThesis, TradeType

if TYPE_CHECKING:
    from beavr.llm.client import LLMClient

logger = logging.getLogger(__name__)


class OrderType(str, Enum):
    """Order types for execution."""
    
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


class TimeInForce(str, Enum):
    """Time in force for orders."""
    
    DAY = "day"
    GTC = "gtc"  # Good til cancelled
    IOC = "ioc"  # Immediate or cancel


class ExecutionStatus(str, Enum):
    """Status of trade execution."""
    
    EXECUTED = "executed"
    SKIPPED = "skipped"
    FAILED = "failed"
    QUEUED = "queued"


class OpeningRangeAnalysis(BaseModel):
    """Analysis of the 5-minute opening range."""
    
    symbol: str
    analysis_time: datetime
    open_price: Decimal
    high_5min: Decimal
    low_5min: Decimal
    current_price: Decimal
    
    # Direction analysis
    thesis_direction: str = Field(description="Expected direction from thesis")
    price_confirms_thesis: bool = Field(description="Does price action confirm thesis?")
    confirmation_reason: str = Field(description="Why price does/doesn't confirm")
    
    # Volume analysis
    volume_5min: int
    avg_volume_5min: int
    volume_confirms: bool = Field(description="Is volume supporting the move?")
    
    # Final verdict
    should_execute: bool
    execution_reason: str


class ExecutionPlan(BaseModel):
    """Plan for executing a trade."""
    
    thesis_id: str
    dd_report_id: Optional[str] = None
    symbol: str
    direction: str = Field(description="buy or sell")
    
    # Sizing
    portfolio_value: Decimal
    position_value: Decimal
    shares: Decimal
    position_pct: float = Field(description="Position as % of portfolio")
    
    # Order details
    order_type: OrderType
    limit_price: Optional[Decimal] = None
    time_in_force: TimeInForce
    
    # Risk levels (attached to position)
    stop_loss_price: Decimal
    target_price: Decimal
    
    # Time management
    is_day_trade: bool = False
    exit_deadline: Optional[datetime] = None  # For day trades
    max_hold_until: date
    
    # Rationale
    execution_rationale: str


class ExecutionResult(BaseModel):
    """Result of a trade execution attempt."""
    
    execution_id: str
    timestamp: datetime
    symbol: str
    status: ExecutionStatus
    
    # If executed
    executed_price: Optional[Decimal] = None
    executed_shares: Optional[Decimal] = None
    order_id: Optional[str] = None
    
    # If skipped/failed
    skip_reason: Optional[str] = None
    error_message: Optional[str] = None
    
    # Linked data
    thesis_id: Optional[str] = None
    dd_report_id: Optional[str] = None


class TradeExecutorAgent(BaseAgent):
    """
    Trade Executor Agent for order execution with power hour logic.
    
    Operates during market hours with special handling for power hour:
    - DO NOT execute at 9:30 AM market open
    - WAIT until 9:35 AM (opening range established)
    - Validate opening range confirms thesis direction
    - Optimal entry window: 9:35 AM - 9:45 AM
    - Day trades must exit by 10:30 AM
    """
    
    name: ClassVar[str] = "Trade Executor"
    role: ClassVar[str] = "trader"
    description: ClassVar[str] = "Order execution with power hour logic"
    version: ClassVar[str] = "2.0.0"
    
    # Time constants (Eastern Time)
    MARKET_OPEN = time(9, 30)
    OPENING_RANGE_END = time(9, 35)  # 5 minutes after open
    OPTIMAL_ENTRY_END = time(9, 45)  # Optimal entry window closes
    POWER_HOUR_END = time(10, 30)
    MARKET_CLOSE = time(16, 0)
    
    # System prompt
    SYSTEM_PROMPT: ClassVar[str] = """You are a Trade Executor for an automated trading system.
Your job is to execute approved trades at optimal prices.

EXECUTION RULES:

1. TIMING (Critical for Day Trades)
   - DO NOT execute at 9:30 AM market open
   - WAIT until 9:35 AM (opening range established)
   - Optimal entry window: 9:35 AM - 9:45 AM
   - For swing trades: can execute anytime during market hours

2. OPENING RANGE CONFIRMATION
   Before executing a day trade at 9:35 AM:
   - Check if price confirms thesis direction
   - Gap UP expected, trading BELOW open → thesis invalid
   - Gap UP expected, holding/extending gains → thesis confirmed

3. POSITION SIZING
   Use risk-based sizing:
   position_value = (risk_budget × portfolio_value) / risk_per_share × entry_price
   
   Caps:
   - Day trade: max 5% of portfolio
   - Swing short: max 10% of portfolio
   - Swing medium/long: max 15-25% of portfolio

4. ORDER TYPES
   - Day trades: MARKET order (speed is priority)
   - Swing limit entry: LIMIT order at DD entry price
   - Swing market entry: MARKET order if at/below entry target

5. ATTACHED ORDERS
   For every entry, attach:
   - Stop loss order (STOP)
   - Take profit order (LIMIT)

CONSTRAINTS:
- Never exceed daily trade limit
- Never exceed position size caps
- Always attach stop loss and take profit
- Log every execution decision for audit"""

    def __init__(
        self,
        llm: LLMClient,
        opening_wait_minutes: int = 5,
        max_daily_trades: int = 5,
        max_position_pct: float = 0.25,
        day_trade_max_pct: float = 0.05,
        swing_short_max_pct: float = 0.10,
        swing_medium_max_pct: float = 0.15,
        swing_long_max_pct: float = 0.25,
    ) -> None:
        """
        Initialize the Trade Executor.
        
        Args:
            llm: LLM client for reasoning
            opening_wait_minutes: Minutes to wait after market open
            max_daily_trades: Maximum trades per day
            max_position_pct: Maximum single position size
            day_trade_max_pct: Max position for day trades
            swing_short_max_pct: Max position for short swings
            swing_medium_max_pct: Max position for medium swings
            swing_long_max_pct: Max position for long swings
        """
        super().__init__(llm)
        self.opening_wait_minutes = opening_wait_minutes
        self.max_daily_trades = max_daily_trades
        self.max_position_pct = max_position_pct
        self.position_limits = {
            TradeType.DAY_TRADE: day_trade_max_pct,
            TradeType.SWING_SHORT: swing_short_max_pct,
            TradeType.SWING_MEDIUM: swing_medium_max_pct,
            TradeType.SWING_LONG: swing_long_max_pct,
        }
        self.trades_today = 0
    
    def get_system_prompt(self) -> str:
        """Return the agent's system prompt."""
        return self.SYSTEM_PROMPT
    
    def analyze(self, _ctx: AgentContext) -> AgentProposal:
        """
        Analyze pending trades and execute if conditions are met.
        
        This is typically called with pending approved theses/DD reports.
        """
        # This method is mostly for orchestrator compatibility
        # Real execution happens via execute_from_dd or execute_from_thesis
        return AgentProposal(
            agent_name=self.name,
            timestamp=datetime.now(),
            signals=[],
            conviction=0.0,
            rationale="Trade Executor ready for execution commands",
            risk_score=0.0,
            risk_factors=[],
            model_version=self.version,
        )
    
    def can_execute_now(self, is_day_trade: bool = False) -> tuple[bool, str]:
        """
        Check if we can execute trades now.
        
        Args:
            is_day_trade: Whether this is a day trade
            
        Returns:
            Tuple of (can_execute, reason)
        """
        now = datetime.now()
        current_time = now.time()
        
        # Check if market is open
        if current_time < self.MARKET_OPEN:
            return False, "Market not yet open"
        
        if current_time > self.MARKET_CLOSE:
            return False, "Market is closed"
        
        # For day trades, enforce opening wait
        if is_day_trade:
            if current_time < self.OPENING_RANGE_END:
                return False, f"Waiting for opening range (wait until {self.OPENING_RANGE_END})"
            
            if current_time > self.OPTIMAL_ENTRY_END:
                return False, "Optimal day trade entry window has passed (9:35-9:45 AM)"
        
        # Check daily trade limit
        if self.trades_today >= self.max_daily_trades:
            return False, f"Daily trade limit reached ({self.max_daily_trades})"
        
        return True, "Clear to execute"
    
    def analyze_opening_range(
        self,
        symbol: str,
        ctx: AgentContext,
        thesis: TradeThesis,
    ) -> OpeningRangeAnalysis:
        """
        Analyze the 5-minute opening range to confirm thesis direction.
        
        Args:
            symbol: Trading symbol
            ctx: Current market context
            thesis: The trade thesis
            
        Returns:
            OpeningRangeAnalysis with execution recommendation
        """
        current_price = ctx.prices.get(symbol, Decimal("0"))
        bars = ctx.bars.get(symbol, [])
        
        # Get opening range data (would come from real-time data in production)
        # For now, use available bar data
        if bars:
            recent_bar = bars[-1]
            open_price = Decimal(str(recent_bar.get("open", current_price)))
            high_5min = Decimal(str(recent_bar.get("high", current_price)))
            low_5min = Decimal(str(recent_bar.get("low", current_price)))
            volume = int(recent_bar.get("volume", 0))
        else:
            open_price = current_price
            high_5min = current_price
            low_5min = current_price
            volume = 0
        
        # Determine if price confirms thesis
        thesis_is_long = thesis.direction == TradeDirection.LONG
        
        # For long thesis: price should be above open (gap holding/extending)
        # For short thesis: price should be below open
        if thesis_is_long:
            price_confirms = current_price >= open_price
            if price_confirms:
                reason = f"Price ${current_price:.2f} holding above open ${open_price:.2f} - bullish confirmed"
            else:
                reason = f"Price ${current_price:.2f} below open ${open_price:.2f} - thesis direction not confirmed"
        else:
            price_confirms = current_price <= open_price
            if price_confirms:
                reason = f"Price ${current_price:.2f} below open ${open_price:.2f} - bearish confirmed"
            else:
                reason = f"Price ${current_price:.2f} above open ${open_price:.2f} - thesis direction not confirmed"
        
        # Volume confirmation (heuristic)
        avg_volume = volume  # Would compare to historical average
        volume_confirms = volume > 0
        
        # Final decision
        should_execute = price_confirms and volume_confirms
        execution_reason = reason if should_execute else f"Skipping: {reason}"
        
        return OpeningRangeAnalysis(
            symbol=symbol,
            analysis_time=datetime.now(),
            open_price=open_price,
            high_5min=high_5min,
            low_5min=low_5min,
            current_price=current_price,
            thesis_direction=thesis.direction.value,
            price_confirms_thesis=price_confirms,
            confirmation_reason=reason,
            volume_5min=volume,
            avg_volume_5min=avg_volume,
            volume_confirms=volume_confirms,
            should_execute=should_execute,
            execution_reason=execution_reason,
        )
    
    def create_execution_plan(
        self,
        thesis: TradeThesis,
        dd_report: Optional[DueDiligenceReport],
        ctx: AgentContext,
    ) -> ExecutionPlan:
        """
        Create an execution plan for a trade.
        
        Args:
            thesis: The trade thesis
            dd_report: Optional DD report (preferred for targets)
            ctx: Current market context
            
        Returns:
            ExecutionPlan with all details
        """
        symbol = thesis.symbol
        current_price = ctx.prices.get(symbol, Decimal("0"))
        portfolio_value = ctx.portfolio_value
        
        # Use DD report targets if available, else thesis targets
        if dd_report:
            entry_price = dd_report.recommended_entry
            target_price = dd_report.recommended_target
            stop_price = dd_report.recommended_stop
            position_size_pct = dd_report.recommended_position_size_pct
        else:
            entry_price = thesis.entry_price_target
            target_price = thesis.profit_target
            stop_price = thesis.stop_loss
            position_size_pct = 0.05  # Default 5%
        
        # Determine trade type and apply position limits
        trade_type = thesis.trade_type
        max_pct = self.position_limits.get(trade_type, self.max_position_pct)
        position_size_pct = min(position_size_pct, max_pct)
        
        # Calculate position value and shares
        position_value = portfolio_value * Decimal(str(position_size_pct))
        shares = position_value / current_price
        
        # Determine order type
        is_day_trade = trade_type == TradeType.DAY_TRADE
        if is_day_trade:
            order_type = OrderType.MARKET  # Speed priority
            time_in_force = TimeInForce.DAY
        else:
            # Use limit if price is above entry target (wait for pullback)
            if current_price > entry_price:
                order_type = OrderType.LIMIT
            else:
                order_type = OrderType.MARKET
            time_in_force = TimeInForce.GTC
        
        # Set exit deadline for day trades
        exit_deadline = None
        if is_day_trade:
            today = date.today()
            exit_deadline = datetime.combine(today, self.POWER_HOUR_END)
        
        direction = "buy" if thesis.direction == TradeDirection.LONG else "sell"
        
        return ExecutionPlan(
            thesis_id=thesis.id,
            dd_report_id=dd_report.id if dd_report else None,
            symbol=symbol,
            direction=direction,
            portfolio_value=portfolio_value,
            position_value=position_value,
            shares=shares,
            position_pct=position_size_pct * 100,
            order_type=order_type,
            limit_price=entry_price if order_type == OrderType.LIMIT else None,
            time_in_force=time_in_force,
            stop_loss_price=stop_price,
            target_price=target_price,
            is_day_trade=is_day_trade,
            exit_deadline=exit_deadline,
            max_hold_until=thesis.max_hold_date,
            execution_rationale=f"Executing {trade_type.value} for {symbol}",
        )
    
    def execute(
        self,
        plan: ExecutionPlan,
        ctx: AgentContext,
    ) -> ExecutionResult:
        """
        Execute a trade based on the plan.
        
        In production, this would interface with Alpaca API.
        Currently returns a mock result.
        
        Args:
            plan: The execution plan
            ctx: Market context
            
        Returns:
            ExecutionResult indicating success/failure
        """
        import uuid
        
        # Check if we can execute
        can_execute, reason = self.can_execute_now(plan.is_day_trade)
        if not can_execute:
            return ExecutionResult(
                execution_id=str(uuid.uuid4())[:8],
                timestamp=datetime.now(),
                symbol=plan.symbol,
                status=ExecutionStatus.SKIPPED,
                skip_reason=reason,
                thesis_id=plan.thesis_id,
                dd_report_id=plan.dd_report_id,
            )
        
        # For day trades, we would analyze opening range here
        # and skip if thesis isn't confirmed
        
        current_price = ctx.prices.get(plan.symbol, Decimal("0"))
        
        # In production: Submit to Alpaca API
        # For now: Simulate successful execution
        logger.info(f"Executing {plan.direction} {plan.shares:.2f} shares of {plan.symbol} @ ${current_price:.2f}")
        
        self.trades_today += 1
        
        return ExecutionResult(
            execution_id=str(uuid.uuid4())[:8],
            timestamp=datetime.now(),
            symbol=plan.symbol,
            status=ExecutionStatus.EXECUTED,
            executed_price=current_price,
            executed_shares=plan.shares,
            order_id=f"order_{uuid.uuid4().hex[:8]}",
            thesis_id=plan.thesis_id,
            dd_report_id=plan.dd_report_id,
        )
    
    def execute_from_dd(
        self,
        dd_report: DueDiligenceReport,
        thesis: Optional[TradeThesis],
        ctx: AgentContext,
    ) -> ExecutionResult:
        """
        Execute a trade from an approved DD report.
        
        Args:
            dd_report: The approved DD report
            thesis: Optional associated thesis
            ctx: Market context
            
        Returns:
            ExecutionResult
        """
        if dd_report.recommendation.value != "approve":
            return ExecutionResult(
                execution_id="",
                timestamp=datetime.now(),
                symbol=dd_report.symbol,
                status=ExecutionStatus.SKIPPED,
                skip_reason=f"DD not approved: {dd_report.rejection_rationale}",
            )
        
        # Create thesis if not provided
        if not thesis:
            thesis = TradeThesis(
                symbol=dd_report.symbol,
                trade_type=TradeType(dd_report.recommended_trade_type.value),
                direction=TradeDirection.LONG,
                entry_rationale=dd_report.executive_summary,
                catalyst=dd_report.catalyst_assessment,
                entry_price_target=dd_report.recommended_entry,
                profit_target=dd_report.recommended_target,
                stop_loss=dd_report.recommended_stop,
                expected_exit_date=date.today() + timedelta(days=7),
                max_hold_date=date.today() + timedelta(days=14),
            )
        
        plan = self.create_execution_plan(thesis, dd_report, ctx)
        return self.execute(plan, ctx)
    
    def reset_daily_counter(self) -> None:
        """Reset the daily trade counter (call at start of each trading day)."""
        self.trades_today = 0
        logger.info("Trade Executor: Daily trade counter reset")
