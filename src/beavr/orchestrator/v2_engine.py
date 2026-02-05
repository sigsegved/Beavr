"""V2 Autonomous Orchestrator for thesis-driven trading.

This is the central coordinator for the V2 AI Investor architecture.
It manages the continuous research pipeline and market hours execution.

Architecture:
- Continuous Research (24/7): News Monitor → Thesis Generator → DD Agent
- Market Hours (9:30-4:00 ET): Morning Scanner → Trade Executor → Position Manager
- Overnight DD (8 PM - 6 AM ET): Deep research on promising candidates

The orchestrator runs in an infinite loop, switching modes based on time.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field

from beavr.agents.base import AgentContext
from beavr.models.dd_report import DDRecommendation
from beavr.models.market_event import EventImportance, EventType, MarketEvent
from beavr.models.thesis import ThesisStatus, TradeThesis, TradeType

if TYPE_CHECKING:
    from beavr.agents import (
        DueDiligenceAgent,
        MorningScannerAgent,
        NewsMonitorAgent,
        PositionManagerAgent,
        ThesisGeneratorAgent,
        TradeExecutorAgent,
    )
    from beavr.db import (
        AIPositionsRepository,
        DDReportsRepository,
        EventsRepository,
        ThesisRepository,
    )
    from beavr.llm import LLMClient

logger = logging.getLogger(__name__)

# US Eastern timezone
ET = ZoneInfo("America/New_York")


class OrchestratorPhase(str, Enum):
    """Current operating phase of the orchestrator."""
    
    OVERNIGHT_DD = "overnight_dd"        # 8 PM - 6 AM: Deep research
    PRE_MARKET = "pre_market"             # 4 AM - 9:30 AM: Morning scan
    POWER_HOUR = "power_hour"             # 9:30 - 10:30 AM: Day trade execution
    MARKET_HOURS = "market_hours"         # 10:30 AM - 4 PM: Position management
    AFTER_HOURS = "after_hours"           # 4 PM - 8 PM: Learning & prep


class SystemState(BaseModel):
    """Runtime state persisted between restarts."""
    
    last_update: datetime = Field(default_factory=datetime.now)
    current_phase: OrchestratorPhase = OrchestratorPhase.AFTER_HOURS
    
    # Daily state (resets each day)
    current_date: date = Field(default_factory=date.today)
    trades_today: int = 0
    daily_pnl: Decimal = Decimal("0")
    invested_today: bool = False
    
    # Research state
    pending_dd_candidates: list[str] = Field(default_factory=list)
    dd_completed_tonight: list[str] = Field(default_factory=list)
    
    # Position state
    active_day_trades: list[str] = Field(default_factory=list)
    active_swing_trades: list[str] = Field(default_factory=list)
    
    # Performance tracking
    peak_portfolio_value: Decimal = Decimal("0")
    current_drawdown: float = 0.0
    consecutive_losses: int = 0
    
    # Circuit breaker
    trading_enabled: bool = True
    circuit_breaker_until: Optional[datetime] = None

    # Research tracking
    last_research_run: Optional[datetime] = None


@dataclass
class V2Config:
    """Configuration for V2 orchestrator."""
    
    # Risk management
    max_daily_loss_pct: float = 3.0
    max_drawdown_pct: float = 10.0
    max_consecutive_losses: int = 3
    circuit_breaker_hours: int = 24
    
    # Position sizing
    capital_allocation_pct: float = 0.80
    max_position_pct: float = 0.25
    max_day_trade_pct: float = 0.10
    daily_trade_limit: int = 5
    
    # Day trade targets (user specified)
    day_trade_target_pct: float = 5.0
    day_trade_stop_pct: float = 3.0
    
    # Swing trade targets
    swing_short_target_pct: float = 8.0
    swing_short_stop_pct: float = 4.0
    swing_medium_target_pct: float = 15.0
    swing_medium_stop_pct: float = 7.0
    swing_long_target_pct: float = 30.0
    swing_long_stop_pct: float = 12.0
    
    # Time windows (Eastern Time)
    overnight_dd_start: int = 20  # 8 PM
    overnight_dd_end: int = 6     # 6 AM
    pre_market_start: int = 4    # 4 AM
    market_open_hour: int = 9
    market_open_minute: int = 30
    power_hour_end_hour: int = 10
    power_hour_end_minute: int = 30
    market_close_hour: int = 16  # 4 PM
    
    # Polling intervals (seconds)
    news_poll_interval: int = 900      # 15 minutes
    market_research_interval: int = 900  # 15 minutes
    position_check_interval: int = 300  # 5 minutes
    power_hour_check_interval: int = 120  # 2 minutes

    # Research scope
    market_movers_limit: int = 10
    news_limit: int = 25
    max_research_symbols: int = 25
    
    # Paths
    state_file: str = "logs/ai_investor/v2_state.json"
    log_dir: str = "logs/ai_investor"


class V2AutonomousOrchestrator:
    """
    V2 Autonomous Orchestrator for thesis-driven trading.
    
    Manages the complete trading workflow:
    1. Continuous news monitoring
    2. Thesis generation from events
    3. Overnight due diligence research
    4. Pre-market scanning
    5. Power hour execution (day trades)
    6. Position management throughout the day
    
    The orchestrator is the "brain" that coordinates all agents.
    """
    
    def __init__(
        self,
        # Agents (lazy loaded if None)
        news_monitor: Optional[NewsMonitorAgent] = None,
        thesis_generator: Optional[ThesisGeneratorAgent] = None,
        dd_agent: Optional[DueDiligenceAgent] = None,
        morning_scanner: Optional[MorningScannerAgent] = None,
        trade_executor: Optional[TradeExecutorAgent] = None,
        position_manager: Optional[PositionManagerAgent] = None,
        # Repositories
        thesis_repo: Optional[ThesisRepository] = None,
        dd_repo: Optional[DDReportsRepository] = None,
        events_repo: Optional[EventsRepository] = None,
        positions_repo: Optional[AIPositionsRepository] = None,
        # Config
        config: Optional[V2Config] = None,
        # LLM client (for lazy loading agents)
        llm_client: Optional[LLMClient] = None,
    ) -> None:
        """Initialize the V2 Orchestrator."""
        self.news_monitor = news_monitor
        self.thesis_generator = thesis_generator
        self.dd_agent = dd_agent
        self.morning_scanner = morning_scanner
        self.trade_executor = trade_executor
        self.position_manager = position_manager
        
        self.thesis_repo = thesis_repo
        self.dd_repo = dd_repo
        self.events_repo = events_repo
        self.positions_repo = positions_repo
        
        self.config = config or V2Config()
        self.llm_client = llm_client
        
        # State
        self.state = SystemState()
        self._running = False
        self._shutdown_requested = False
        
        # Trading client (set externally)
        self._trading_client = None
        self._data_client = None
        
        # Context builder (set externally)
        self._ctx_builder = None

        # Lazy data utilities
        self._market_screener = None
        self._news_scanner = None
    
    def set_trading_client(self, trading_client, data_client) -> None:
        """Set the Alpaca trading and data clients."""
        self._trading_client = trading_client
        self._data_client = data_client
    
    def set_context_builder(self, builder) -> None:
        """Set the function to build AgentContext for symbols."""
        self._ctx_builder = builder
    
    def _load_state(self) -> None:
        """Load state from disk."""
        state_path = Path(self.config.state_file)
        if state_path.exists():
            try:
                data = json.loads(state_path.read_text())
                self.state = SystemState(**data)
                logger.info(f"Loaded state from {state_path}")
            except Exception as e:
                logger.warning(f"Could not load state: {e}")
                self.state = SystemState()
        
        # Reset daily state if new day
        today = date.today()
        if self.state.current_date != today:
            logger.info(f"New day: {today}, resetting daily state")
            self.state.current_date = today
            self.state.trades_today = 0
            self.state.daily_pnl = Decimal("0")
            self.state.invested_today = False
            self.state.active_day_trades = []
            self.state.dd_completed_tonight = []
            self.state.last_research_run = None
    
    def _save_state(self) -> None:
        """Save state to disk."""
        state_path = Path(self.config.state_file)
        state_path.parent.mkdir(parents=True, exist_ok=True)
        
        self.state.last_update = datetime.now()
        
        # Convert to dict, handling Decimal serialization
        data = self.state.model_dump(mode="json")
        state_path.write_text(json.dumps(data, indent=2, default=str))
    
    def _get_current_phase(self) -> OrchestratorPhase:
        """Determine current operating phase based on time."""
        now = datetime.now(ET)
        hour = now.hour
        minute = now.minute
        weekday = now.weekday()
        
        # Weekend: always overnight mode for research
        if weekday >= 5:
            return OrchestratorPhase.OVERNIGHT_DD
        
        # Overnight DD: 8 PM - 6 AM
        if hour >= self.config.overnight_dd_start or hour < self.config.overnight_dd_end:
            return OrchestratorPhase.OVERNIGHT_DD
        
        # Pre-market: 6 AM - 9:30 AM
        if hour < self.config.market_open_hour:
            return OrchestratorPhase.PRE_MARKET
        if hour == self.config.market_open_hour and minute < self.config.market_open_minute:
            return OrchestratorPhase.PRE_MARKET
        
        # Power hour: 9:30 AM - 10:30 AM
        if hour == self.config.market_open_hour and minute >= self.config.market_open_minute:
            return OrchestratorPhase.POWER_HOUR
        if hour == self.config.power_hour_end_hour and minute < self.config.power_hour_end_minute:
            return OrchestratorPhase.POWER_HOUR
        
        # Market hours: 10:30 AM - 4 PM
        if hour < self.config.market_close_hour:
            return OrchestratorPhase.MARKET_HOURS
        
        # After hours: 4 PM - 8 PM
        return OrchestratorPhase.AFTER_HOURS
    
    def _check_circuit_breaker(self) -> bool:
        """Check if circuit breaker is active."""
        if not self.state.trading_enabled:
            # Check if cooldown has expired
            if (
                self.state.circuit_breaker_until
                and datetime.now() > self.state.circuit_breaker_until
            ):
                logger.info("Circuit breaker cooldown expired, re-enabling trading")
                self.state.trading_enabled = True
                self.state.circuit_breaker_until = None
                self.state.consecutive_losses = 0
                return True
            return False
        return True
    
    def _trigger_circuit_breaker(self, reason: str) -> None:
        """Trigger the circuit breaker to halt trading."""
        logger.warning(f"🚨 CIRCUIT BREAKER TRIGGERED: {reason}")
        self.state.trading_enabled = False
        self.state.circuit_breaker_until = (
            datetime.now() + timedelta(hours=self.config.circuit_breaker_hours)
        )
        self._save_state()
    
    def _check_risk_limits(self, portfolio_value: Decimal) -> bool:
        """
        Check if we've hit any risk limits.
        
        Returns True if trading is allowed, False if limits hit.
        """
        # Update peak and drawdown
        if portfolio_value > self.state.peak_portfolio_value:
            self.state.peak_portfolio_value = portfolio_value
        
        if self.state.peak_portfolio_value > 0:
            self.state.current_drawdown = float(
                1 - portfolio_value / self.state.peak_portfolio_value
            )
        
        # Check max drawdown
        if self.state.current_drawdown >= self.config.max_drawdown_pct / 100:
            self._trigger_circuit_breaker(
                f"Max drawdown {self.config.max_drawdown_pct}% hit"
            )
            return False
        
        # Check daily loss
        if self.state.daily_pnl < 0:
            daily_loss_pct = abs(float(self.state.daily_pnl)) / float(portfolio_value) * 100
            if daily_loss_pct >= self.config.max_daily_loss_pct:
                self._trigger_circuit_breaker(
                    f"Max daily loss {self.config.max_daily_loss_pct}% hit"
                )
                return False
        
        # Check consecutive losses
        if self.state.consecutive_losses >= self.config.max_consecutive_losses:
            self._trigger_circuit_breaker(
                f"{self.config.max_consecutive_losses} consecutive losses"
            )
            return False
        
        # Check daily trade limit
        if self.state.trades_today >= self.config.daily_trade_limit:
            logger.info(f"Daily trade limit ({self.config.daily_trade_limit}) reached")
            return False
        
        return True
    
    def _get_approved_theses(self) -> list[TradeThesis]:
        """Get theses that have been DD approved and ready to trade."""
        if not self.thesis_repo:
            return []
        
        try:
            # Get active theses - filter for DD approved ones
            theses = self.thesis_repo.get_active()
            return [t for t in theses if t.dd_approved and t.status != ThesisStatus.DRAFT]
        except Exception as e:
            logger.error(f"Error getting approved theses: {e}")
            return []
    
    def _get_pending_dd_candidates(self) -> list[TradeThesis]:
        """Get theses pending DD review."""
        if not self.thesis_repo:
            return []
        
        try:
            # Use the repository's built-in method for pending DD
            return self.thesis_repo.get_pending_dd()
        except Exception as e:
            logger.error(f"Error getting pending DD candidates: {e}")
            return []

    def _build_context(self, symbols: list[str]) -> AgentContext:
        """Build agent context for the provided symbols."""
        if self._ctx_builder:
            return self._ctx_builder(symbols)

        prices = {symbol: Decimal("0") for symbol in symbols}
        return AgentContext(
            current_date=date.today(),
            timestamp=datetime.now(),
            prices=prices,
            bars={symbol: [] for symbol in symbols},
            indicators={symbol: {} for symbol in symbols},
            cash=Decimal("10000"),
            positions={},
            portfolio_value=Decimal("10000"),
            current_drawdown=0.0,
            peak_value=Decimal("10000"),
            risk_budget=1.0,
            events=[],
        )

    def _get_market_screener(self):
        """Lazy-load the market screener."""
        if self._market_screener is not None:
            return self._market_screener

        try:
            from beavr.core.config import get_settings
            from beavr.data.screener import MarketScreener

            settings = get_settings()
            self._market_screener = MarketScreener(
                settings.alpaca_api_key,
                settings.alpaca_api_secret,
            )
        except Exception as e:
            logger.warning(f"Market screener unavailable: {e}")
            self._market_screener = None

        return self._market_screener

    def _get_news_scanner(self):
        """Lazy-load the news scanner."""
        if self._news_scanner is not None:
            return self._news_scanner

        try:
            from beavr.core.config import get_settings
            from beavr.data.screener import NewsScanner

            settings = get_settings()
            self._news_scanner = NewsScanner(
                settings.alpaca_api_key,
                settings.alpaca_api_secret,
            )
        except Exception as e:
            logger.warning(f"News scanner unavailable: {e}")
            self._news_scanner = None

        return self._news_scanner

    def _fetch_market_mover_events(self) -> list[MarketEvent]:
        """Fetch market mover symbols and convert to synthetic events."""
        screener = self._get_market_screener()
        if not screener:
            return []

        max_retries = 3
        movers = None
        for attempt in range(max_retries):
            try:
                movers = screener.get_market_movers(top_n=self.config.market_movers_limit)
                break
            except Exception as e:
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    logger.warning(f"Market mover fetch failed (attempt {attempt + 1}/{max_retries}): {e}, retrying in {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    logger.warning(f"Market mover fetch failed after {max_retries} attempts: {e}")
                    return []

        if not movers:
            return []

        events: list[MarketEvent] = []

        for mover in movers.top_gainers:
            events.append(
                MarketEvent(
                    event_type=EventType.NEWS_CATALYST,
                    symbol=mover.symbol,
                    headline=f"Top gainer: {mover.symbol}",
                    summary=f"{mover.symbol} up {mover.percent_change:+.1f}% as a top gainer",
                    source="market_movers",
                    timestamp=datetime.now(),
                    importance=EventImportance.MEDIUM,
                )
            )

        for mover in movers.top_losers:
            events.append(
                MarketEvent(
                    event_type=EventType.NEWS_CATALYST,
                    symbol=mover.symbol,
                    headline=f"Top loser: {mover.symbol}",
                    summary=f"{mover.symbol} down {mover.percent_change:+.1f}% as a top loser",
                    source="market_movers",
                    timestamp=datetime.now(),
                    importance=EventImportance.MEDIUM,
                )
            )

        for mover in movers.most_active:
            events.append(
                MarketEvent(
                    event_type=EventType.OTHER,
                    symbol=mover.symbol,
                    headline=f"Most active: {mover.symbol}",
                    summary=f"{mover.symbol} is among the most active by volume",
                    source="market_movers",
                    timestamp=datetime.now(),
                    importance=EventImportance.MEDIUM,
                )
            )

        return events

    def _build_research_universe(
        self,
        mover_symbols: list[str],
        open_positions: Optional[list[str]] = None,
    ) -> list[str]:
        """Build the symbol universe for research."""
        symbols: set[str] = set(mover_symbols)

        if open_positions:
            symbols.update(open_positions)

        for thesis in self._get_approved_theses():
            symbols.add(thesis.symbol)

        for thesis in self._get_pending_dd_candidates():
            symbols.add(thesis.symbol)

        limited = list(symbols)[: self.config.max_research_symbols]
        return limited

    def _fetch_news_items(self, symbols: list[str]) -> list[dict[str, Any]]:
        """Fetch raw news items for the provided symbols with retry logic."""
        scanner = self._get_news_scanner()
        if not scanner:
            return []

        max_retries = 3
        for attempt in range(max_retries):
            try:
                if symbols:
                    return scanner.get_news(symbols=symbols, limit=self.config.news_limit)
                return scanner.get_news(limit=self.config.news_limit)
            except Exception as e:
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt  # 1s, 2s, 4s
                    logger.warning(f"News fetch failed (attempt {attempt + 1}/{max_retries}): {e}, retrying in {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    logger.warning(f"News fetch failed after {max_retries} attempts: {e}")
                    return []
        return []

    def _classify_news_events(self, news_items: list[dict[str, Any]]) -> list[MarketEvent]:
        """Classify raw news items into MarketEvent entries."""
        if not self.news_monitor or not news_items:
            return []

        try:
            return self.news_monitor.monitor_cycle(news_items)
        except Exception as e:
            logger.warning(f"News classification failed: {e}")
            return []

    def _dedupe_events(self, events: list[MarketEvent]) -> list[MarketEvent]:
        """De-duplicate events by ID."""
        unique: dict[str, MarketEvent] = {}
        for event in events:
            unique[event.id] = event
        return list(unique.values())

    def _find_existing_thesis_id(self, symbol: str, catalyst: str) -> Optional[str]:
        """Return an existing thesis ID if a similar thesis already exists."""
        if not self.thesis_repo:
            return None

        try:
            for thesis in self.thesis_repo.get_by_symbol(symbol):
                if (
                    thesis.status in {ThesisStatus.DRAFT, ThesisStatus.ACTIVE, ThesisStatus.EXECUTED}
                    and thesis.catalyst == catalyst
                ):
                    return thesis.id
        except Exception as e:
            logger.warning(f"Failed to check existing theses for {symbol}: {e}")

        return None

    def _generate_theses_from_events(self, events: list[MarketEvent]) -> list[TradeThesis]:
        """Generate theses from the provided market events."""
        if not self.thesis_generator:
            logger.info("Thesis generator not configured")
            return []

        event_symbols = sorted({event.symbol for event in events if event.symbol})
        if not event_symbols:
            return []

        ctx = self._build_context(event_symbols)
        created: list[TradeThesis] = []

        for event in events:
            if not event.symbol:
                if self.events_repo:
                    self.events_repo.mark_processed(event.id)
                continue

            existing_id = self._find_existing_thesis_id(event.symbol, event.summary or event.headline)
            if existing_id:
                if self.events_repo:
                    self.events_repo.mark_processed(event.id, existing_id)
                continue

            thesis = self.thesis_generator.generate_thesis_from_event(event, ctx)
            if not thesis:
                if self.events_repo:
                    self.events_repo.mark_processed(event.id)
                continue

            thesis.status = ThesisStatus.ACTIVE

            if self.thesis_repo:
                try:
                    self.thesis_repo.create(thesis)
                except Exception as e:
                    logger.warning(f"Failed to save thesis for {thesis.symbol}: {e}")
            created.append(thesis)

            if self.events_repo:
                self.events_repo.mark_processed(event.id, thesis.id)

        return created

    def _is_research_mode(
        self,
        approved_theses: int,
        pending_dd: int,
        open_positions: int,
    ) -> bool:
        """Return True if the system should focus on research."""
        return approved_theses == 0 and pending_dd == 0 and open_positions == 0

    def _should_run_research(
        self,
        now: datetime,
        phase: OrchestratorPhase,
        research_mode: bool = False,
    ) -> bool:
        """Determine whether a research cycle should run now.
        
        If research_mode is True (no theses, no positions), run immediately
        without waiting for the interval - no point sitting idle.
        """
        if phase not in {OrchestratorPhase.POWER_HOUR, OrchestratorPhase.MARKET_HOURS}:
            return False

        # When idle (nothing to do), research immediately
        if research_mode:
            return True

        last_run = self.state.last_research_run
        if last_run and last_run.tzinfo is None:
            last_run = last_run.replace(tzinfo=ET)

        if not last_run:
            return True

        elapsed = (now - last_run).total_seconds()
        return elapsed >= self.config.market_research_interval

    def _run_market_research_cycle(
        self,
        open_positions: list[str],
        research_mode: bool,
    ) -> None:
        """Run the continuous research pipeline during market hours."""
        self.state.last_research_run = datetime.now(ET)
        self._save_state()

        logger.info("=" * 60)
        logger.info("🔬 MARKET HOURS RESEARCH CYCLE")
        logger.info("=" * 60)

        mover_events = self._fetch_market_mover_events()
        mover_symbols = [event.symbol for event in mover_events if event.symbol]
        if mover_symbols:
            logger.info(f"📈 Market movers: {mover_symbols[:10]}")
        elif research_mode:
            logger.info("📉 No movers available; research mode remains active")

        research_universe = self._build_research_universe(mover_symbols, open_positions)
        if not research_universe:
            logger.info("No research symbols available")
            return

        news_items = self._fetch_news_items(research_universe)
        news_events = self._classify_news_events(news_items)

        # Store news events (NOT mover events - those are just for universe building)
        if self.events_repo and news_events:
            for event in news_events:
                try:
                    self.events_repo.create(event)
                except Exception as e:
                    logger.warning(f"Failed to store event {event.id}: {e}")

        # Only process REAL news events for thesis generation
        # Mover data is ONLY used to build the research universe (which symbols to scan)
        # We never trade based on movers alone - only on news/events with catalysts
        if self.events_repo:
            try:
                unprocessed_events = self.events_repo.get_unprocessed()
            except Exception as e:
                logger.warning(f"Failed to load unprocessed events: {e}")
                unprocessed_events = []
            events_to_process = self._dedupe_events(unprocessed_events)
        else:
            # Only news events, NOT mover events
            events_to_process = self._dedupe_events(news_events)

        if events_to_process:
            logger.info(f"📚 Processing {len(events_to_process)} NEWS events for thesis generation")
        elif research_mode:
            logger.info("📚 No actionable news events found (movers are for universe only)")

        created_theses = self._generate_theses_from_events(events_to_process)
        if created_theses:
            logger.info(f"✅ Created {len(created_theses)} new theses")

        pending_dd = self._get_pending_dd_candidates()
        if pending_dd:
            self._run_dd_cycle(pending_dd, "🔬 MARKET HOURS DD CYCLE")
        elif research_mode:
            logger.info("🔬 No pending DD candidates in research mode")
    
    def _run_dd_cycle(self, candidates: list[TradeThesis], label: str) -> None:
        """Run a DD cycle for the provided candidates."""
        logger.info("=" * 60)
        logger.info(label)
        logger.info("=" * 60)

        if not self.dd_agent or not self.thesis_repo:
            logger.warning("DD agent or thesis repo not configured")
            return

        if not candidates:
            logger.info("No pending DD candidates")
            return

        logger.info(f"📋 {len(candidates)} candidates for DD review")

        for thesis in candidates:
            if thesis.symbol in self.state.dd_completed_tonight:
                logger.info(f"  Skipping {thesis.symbol} - already DD'd today")
                continue

            logger.info(f"\n🔬 Researching {thesis.symbol}...")
            logger.info(f"   Trade Type: {thesis.trade_type.value}")
            logger.info(f"   Catalyst: {thesis.catalyst[:80]}...")

            try:
                ctx = self._build_context([thesis.symbol])

                dd_report = self.dd_agent.analyze_thesis(thesis, ctx)

                if dd_report:
                    if self.dd_repo:
                        self.dd_repo.create(dd_report)

                    if dd_report.recommendation == DDRecommendation.APPROVE:
                        logger.info(f"   ✅ APPROVED (confidence: {dd_report.confidence:.0%})")
                        thesis.dd_approved = True
                        thesis.dd_report_id = dd_report.id
                        thesis.status = ThesisStatus.ACTIVE

                        thesis.entry_price_target = dd_report.recommended_entry
                        thesis.profit_target = dd_report.recommended_target
                        thesis.stop_loss = dd_report.recommended_stop

                    elif dd_report.recommendation == DDRecommendation.CONDITIONAL:
                        logger.info(f"   ⚠️  CONDITIONAL (confidence: {dd_report.confidence:.0%})")
                        thesis.dd_report_id = dd_report.id

                    else:
                        logger.info(f"   ❌ REJECTED: {dd_report.rejection_reason}")
                        thesis.status = ThesisStatus.INVALIDATED
                        thesis.dd_report_id = dd_report.id

                    self.thesis_repo.update(thesis)

                self.state.dd_completed_tonight.append(thesis.symbol)

            except Exception as e:
                logger.error(f"   Error running DD for {thesis.symbol}: {e}")

            time.sleep(2)

        self._save_state()
        logger.info("\n✅ DD cycle complete")

    def _run_overnight_dd_cycle(self) -> None:
        """
        Run the overnight DD research cycle.

        This is the deep research phase where we:
        1. Get pending theses that need DD
        2. Run DD agent on each
        3. Save DD reports
        4. Mark theses as approved/rejected
        """
        candidates = self._get_pending_dd_candidates()
        self._run_dd_cycle(candidates, "🌙 OVERNIGHT DD RESEARCH CYCLE")
    
    def _run_pre_market_scan(self) -> list[str]:
        """
        Run pre-market momentum scan.
        
        Returns list of candidate symbols for today.
        """
        logger.info("=" * 60)
        logger.info("🌅 PRE-MARKET SCAN")
        logger.info("=" * 60)
        
        candidates = []
        
        # First, get DD-approved theses ready for today
        approved = self._get_approved_theses()
        day_trade_candidates = [
            t.symbol for t in approved 
            if t.trade_type == TradeType.DAY_TRADE
        ]
        swing_candidates = [
            t.symbol for t in approved
            if t.trade_type != TradeType.DAY_TRADE
        ]
        
        if day_trade_candidates:
            logger.info(f"📋 Day trade candidates from DD: {day_trade_candidates}")
            candidates.extend(day_trade_candidates)
        
        if swing_candidates:
            logger.info(f"📋 Swing candidates from DD: {swing_candidates}")
            candidates.extend(swing_candidates)
        
        # Run morning scanner for additional momentum plays
        if self.morning_scanner and self._ctx_builder:
            logger.info("\n🔍 Running morning scanner...")
            try:
                # Build context with broad universe
                from beavr.cli.ai import QUALITY_UNIVERSE
                sample_symbols = list(QUALITY_UNIVERSE)[:20]
                ctx = self._ctx_builder(sample_symbols)
                
                scan_result = self.morning_scanner.scan(ctx)
                
                for candidate in scan_result.top_candidates:
                    if candidate.conviction_score >= 0.6 and candidate.symbol not in candidates:
                        candidates.append(candidate.symbol)
                        logger.info(
                            f"   📈 {candidate.symbol}: {candidate.catalyst_summary[:60]}..."
                        )
                
            except Exception as e:
                logger.error(f"Morning scan error: {e}")
        
        if not candidates:
            logger.info("❌ No candidates found for today")
        else:
            logger.info(f"\n✅ {len(candidates)} candidates for today: {candidates}")
        
        return candidates
    
    def _execute_power_hour(self, _candidates: list[str]) -> None:
        """
        Execute day trades during power hour (9:35-10:30 AM).
        
        Continuous pipeline - can enter trades throughout power hour.
        Only constraint: wait until 9:35 AM for opening range to establish.
        """
        logger.info("=" * 60)
        logger.info("⚡ POWER HOUR EXECUTION")
        logger.info("=" * 60)
        
        now = datetime.now(ET)
        
        # Only constraint: wait for opening range (first 5 min)
        entry_start = now.replace(hour=9, minute=35, second=0, microsecond=0)
        power_hour_end = now.replace(
            hour=self.config.power_hour_end_hour,
            minute=self.config.power_hour_end_minute,
            second=0, microsecond=0
        )
        
        if now < entry_start:
            wait_seconds = (entry_start - now).total_seconds()
            logger.info(f"⏳ Waiting {wait_seconds/60:.1f} min for opening range (9:35 AM)")
            return
        
        if now > power_hour_end:
            logger.info("⏰ Power hour ended (10:30 AM) - switching to market hours mode")
            return
        
        if not self._check_circuit_breaker():
            logger.warning("🚨 Circuit breaker active - no trading")
            return
        
        # Get approved day trade theses
        approved = self._get_approved_theses()
        day_trades = [t for t in approved if t.trade_type == TradeType.DAY_TRADE]
        
        if not day_trades:
            logger.info("No approved day trades for today")
            return
        
        logger.info(f"📋 {len(day_trades)} approved day trades to execute")
        
        for thesis in day_trades:
            if self.state.trades_today >= self.config.daily_trade_limit:
                logger.info("Daily trade limit reached")
                break
            
            try:
                self._execute_trade(thesis, is_day_trade=True)
            except Exception as e:
                logger.error(f"Error executing {thesis.symbol}: {e}")
    
    def _execute_swing_trades(self) -> None:
        """
        Execute swing trades during market hours.
        
        Continuous pipeline - can enter swing positions anytime during market hours.
        This allows the system to react to market events throughout the day.
        """
        if not self._check_circuit_breaker():
            return
        
        # Get approved swing trade theses (not day trades)
        approved = self._get_approved_theses()
        swing_trades = [
            t for t in approved 
            if t.trade_type != TradeType.DAY_TRADE
            and t.symbol not in self.state.active_swing_trades  # Not already in
        ]
        
        if not swing_trades:
            return  # No need to log - this is continuous
        
        logger.info("=" * 40)
        logger.info("📊 SWING TRADE EXECUTION")
        logger.info("=" * 40)
        logger.info(f"📋 {len(swing_trades)} approved swing trades to execute")
        
        for thesis in swing_trades:
            if self.state.trades_today >= self.config.daily_trade_limit:
                logger.info("Daily trade limit reached")
                break
            
            try:
                self._execute_trade(thesis, is_day_trade=False)
            except Exception as e:
                logger.error(f"Error executing swing trade {thesis.symbol}: {e}")
    
    def _execute_trade(self, thesis: TradeThesis, is_day_trade: bool = False) -> bool:
        """Execute a trade based on an approved thesis."""
        if not self._trading_client:
            logger.warning("Trading client not configured")
            return False
        
        logger.info(f"\n💰 Executing {'DAY TRADE' if is_day_trade else 'SWING'}: {thesis.symbol}")
        
        try:
            # Get current portfolio value
            account = self._trading_client.get_account()
            portfolio_value = Decimal(str(account.equity))
            cash = Decimal(str(account.cash))
            
            # Check risk limits
            if not self._check_risk_limits(portfolio_value):
                return False
            
            # Calculate position size
            if is_day_trade:
                max_position = portfolio_value * Decimal(str(self.config.max_day_trade_pct))
            else:
                max_position = portfolio_value * Decimal(str(self.config.max_position_pct))
            
            # Use DD recommended size if available
            if thesis.dd_report_id and self.dd_repo:
                dd_report = self.dd_repo.get(thesis.dd_report_id)
                if dd_report and dd_report.recommended_position_size_pct:
                    dd_size = portfolio_value * Decimal(str(dd_report.recommended_position_size_pct))
                    max_position = min(max_position, dd_size)
            
            position_value = min(max_position, cash * Decimal("0.95"))  # Keep 5% buffer
            
            if position_value < Decimal("50"):
                logger.warning(f"Position value ${position_value} too small")
                return False
            
            # Calculate shares
            current_price = thesis.entry_price_target  # TODO: Get live price
            shares = (position_value / current_price).quantize(Decimal("0.001"))
            
            logger.info(f"   Entry: ${current_price:.2f}")
            logger.info(f"   Shares: {shares}")
            logger.info(f"   Value: ${position_value:.2f}")
            logger.info(f"   Target: ${thesis.profit_target:.2f} (+{thesis.target_pct:.1f}%)")
            logger.info(f"   Stop: ${thesis.stop_loss:.2f} (-{thesis.stop_pct:.1f}%)")
            
            # Execute order via Alpaca
            from alpaca.trading.enums import OrderSide, TimeInForce
            from alpaca.trading.requests import MarketOrderRequest
            
            order_request = MarketOrderRequest(
                symbol=thesis.symbol,
                notional=float(position_value),
                side=OrderSide.BUY,
                time_in_force=TimeInForce.DAY,
            )
            
            order = self._trading_client.submit_order(order_request)
            
            logger.info(f"   ✅ Order submitted: {order.id}")
            
            # Track position in DB
            if self.positions_repo:
                self.positions_repo.open_position(
                    symbol=thesis.symbol,
                    quantity=float(shares),
                    entry_price=float(current_price),
                    stop_loss_pct=float(thesis.stop_pct),
                    target_pct=float(thesis.target_pct),
                    strategy=f"v2_{thesis.trade_type.value}",
                    rationale=thesis.entry_rationale[:500],
                )
            
            # Update state
            self.state.trades_today += 1
            if is_day_trade:
                self.state.active_day_trades.append(thesis.symbol)
            else:
                self.state.active_swing_trades.append(thesis.symbol)
            
            # Mark thesis as executed
            thesis.status = ThesisStatus.EXECUTED
            if self.thesis_repo:
                self.thesis_repo.update(thesis)
            
            self._save_state()
            return True
            
        except Exception as e:
            logger.error(f"Trade execution error: {e}")
            return False
    
    def _monitor_positions(self) -> None:
        """
        Monitor all open positions during market hours.
        
        Checks:
        - Stop loss / target hits
        - Day trade deadline (10:30 AM)
        - Thesis invalidation
        """
        if not self._trading_client:
            return
        
        try:
            positions = self._trading_client.get_all_positions()
            
            if not positions:
                logger.debug("No open positions")
                return
            
            now = datetime.now(ET)
            power_hour_end = now.replace(
                hour=self.config.power_hour_end_hour,
                minute=self.config.power_hour_end_minute,
                second=0
            )
            
            for pos in positions:
                symbol = pos.symbol
                pnl_pct = float(pos.unrealized_plpc) * 100
                
                # Get position-specific targets from DB
                db_pos = None
                if self.positions_repo:
                    db_pos = self.positions_repo.get_open_position(symbol)
                
                if db_pos:
                    target_pct = db_pos.target_pct
                    stop_pct = db_pos.stop_loss_pct
                else:
                    target_pct = self.config.swing_short_target_pct
                    stop_pct = self.config.swing_short_stop_pct
                
                # Check if day trade needs to exit
                is_day_trade = symbol in self.state.active_day_trades
                
                if is_day_trade and now >= power_hour_end:
                    logger.info(f"⏰ DAY TRADE DEADLINE: Closing {symbol}")
                    self._close_position(symbol, "day_trade_deadline", pnl_pct)
                    continue
                
                # Check target hit
                if pnl_pct >= target_pct:
                    logger.info(f"🎯 TARGET HIT: {symbol} at +{pnl_pct:.1f}%")
                    self._close_position(symbol, "target_hit", pnl_pct)
                    continue
                
                # Check stop loss
                if pnl_pct <= -stop_pct:
                    logger.info(f"🛑 STOP LOSS: {symbol} at {pnl_pct:.1f}%")
                    self._close_position(symbol, "stop_loss", pnl_pct)
                    continue
                
                logger.debug(f"   {symbol}: {pnl_pct:+.1f}% (T:+{target_pct}% S:-{stop_pct}%)")
                
        except Exception as e:
            logger.error(f"Position monitoring error: {e}")
    
    def _close_position(self, symbol: str, reason: str, pnl_pct: float) -> None:
        """Close a position."""
        if not self._trading_client:
            return
        
        try:
            self._trading_client.close_position(symbol)
            logger.info(f"✅ Closed {symbol} ({reason}): {pnl_pct:+.1f}%")
            
            # Update state
            if symbol in self.state.active_day_trades:
                self.state.active_day_trades.remove(symbol)
            if symbol in self.state.active_swing_trades:
                self.state.active_swing_trades.remove(symbol)
            
            # Track PnL
            if pnl_pct > 0:
                self.state.consecutive_losses = 0
            else:
                self.state.consecutive_losses += 1
            
            # Update DB
            if self.positions_repo:
                db_pos = self.positions_repo.get_open_position(symbol)
                if db_pos:
                    # Get current price for close
                    positions = self._trading_client.get_all_positions()
                    exit_price = 0
                    for p in positions:
                        if p.symbol == symbol:
                            exit_price = float(p.current_price)
                            break
                    self.positions_repo.close_position(db_pos.id, exit_price, reason)
            
            self._save_state()
            
        except Exception as e:
            logger.error(f"Error closing {symbol}: {e}")
    
    def run(self) -> None:
        """
        Main run loop for the autonomous orchestrator.
        
        Runs continuously, switching between phases based on time.
        """
        self._running = True
        self._load_state()
        
        logger.info("=" * 60)
        logger.info("🤖 V2 AUTONOMOUS ORCHESTRATOR STARTED")
        logger.info("=" * 60)
        logger.info(f"Config: {self.config.__dict__}")
        logger.info(f"State: {self.state.model_dump()}")
        
        candidates_today = []
        last_news_check = datetime.min.replace(tzinfo=ET)
        
        while self._running and not self._shutdown_requested:
            try:
                now = datetime.now(ET)
                current_phase = self._get_current_phase()
                
                # Log phase changes
                if current_phase != self.state.current_phase:
                    logger.info(f"\n📍 Phase change: {self.state.current_phase.value} → {current_phase.value}")
                    self.state.current_phase = current_phase
                    self._save_state()
                
                # Run phase-specific logic
                if current_phase == OrchestratorPhase.OVERNIGHT_DD:
                    # Heartbeat log
                    pending = self._get_pending_dd_candidates()
                    logger.info(f"🌙 Overnight DD | Pending Candidates: {len(pending)}")
                    
                    # Deep research overnight
                    self._run_overnight_dd_cycle()
                    # Check news periodically
                    if (now - last_news_check).total_seconds() > self.config.news_poll_interval:
                        # TODO: Run news monitor
                        last_news_check = now
                    logger.info("💤 Sleeping 300s...")
                    time.sleep(300)  # 5 min between DD cycles
                    
                elif current_phase == OrchestratorPhase.PRE_MARKET:
                    # Heartbeat log
                    approved = self._get_approved_theses()
                    logger.info(f"🌅 Pre-Market | Approved Theses: {len(approved)} | Candidates: {len(candidates_today)}")
                    
                    # Run morning scan once
                    if not candidates_today:
                        candidates_today = self._run_pre_market_scan()
                    logger.info("💤 Sleeping 300s...")
                    time.sleep(300)  # Check every 5 min
                    
                elif current_phase == OrchestratorPhase.POWER_HOUR:
                    # Heartbeat log
                    approved = self._get_approved_theses()
                    day_trades = [t for t in approved if t.trade_type == TradeType.DAY_TRADE]
                    positions = self._trading_client.get_all_positions() if self._trading_client else []
                    open_symbols = [pos.symbol for pos in positions] if positions else []
                    pending_dd = self._get_pending_dd_candidates()
                    research_mode = self._is_research_mode(
                        approved_theses=len(approved),
                        pending_dd=len(pending_dd),
                        open_positions=len(positions),
                    )
                    logger.info(
                        f"⚡ Power Hour | Day Trade Theses: {len(day_trades)} | "
                        f"Open Positions: {len(positions)} | "
                        f"Trades Today: {self.state.trades_today}/{self.config.daily_trade_limit}"
                    )

                    if self._should_run_research(now, current_phase, research_mode):
                        self._run_market_research_cycle(open_symbols, research_mode)
                    elif research_mode:
                        logger.info("🔬 Research mode idle - awaiting next research window")
                    
                    # Execute day trades
                    self._execute_power_hour(candidates_today)
                    # Monitor positions frequently
                    self._monitor_positions()
                    
                    logger.info(f"💤 Sleeping {self.config.power_hour_check_interval}s...")
                    time.sleep(self.config.power_hour_check_interval)
                    
                elif current_phase == OrchestratorPhase.MARKET_HOURS:
                    # Heartbeat log
                    approved = self._get_approved_theses()
                    positions = self._trading_client.get_all_positions() if self._trading_client else []
                    open_symbols = [pos.symbol for pos in positions] if positions else []
                    pending_dd = self._get_pending_dd_candidates()
                    research_mode = self._is_research_mode(
                        approved_theses=len(approved),
                        pending_dd=len(pending_dd),
                        open_positions=len(positions),
                    )
                    logger.info(
                        f"📊 Market Hours | Approved Theses: {len(approved)} | "
                        f"Open Positions: {len(positions)} | "
                        f"Trades Today: {self.state.trades_today}/{self.config.daily_trade_limit}"
                    )

                    if self._should_run_research(now, current_phase, research_mode):
                        self._run_market_research_cycle(open_symbols, research_mode)
                    elif research_mode:
                        logger.info("🔬 Research mode idle - awaiting next research window")
                    
                    # Execute any pending swing trades
                    self._execute_swing_trades()
                    # Monitor positions
                    self._monitor_positions()
                    
                    logger.info(f"💤 Sleeping {self.config.position_check_interval}s until next check...")
                    time.sleep(self.config.position_check_interval)
                    
                else:  # AFTER_HOURS
                    # Heartbeat log
                    logger.info("🌆 After Hours | Preparing for overnight research...")
                    # Reset for next day
                    candidates_today = []
                    # Learn from today's trades (TODO)
                    logger.info("💤 Sleeping 300s...")
                    time.sleep(300)
                
            except KeyboardInterrupt:
                logger.info("⛔ Shutdown requested")
                self._shutdown_requested = True
            except Exception as e:
                logger.error(f"Orchestrator error: {e}")
                time.sleep(60)  # Back off on errors
        
        self._save_state()
        logger.info("=" * 60)
        logger.info("🤖 V2 AUTONOMOUS ORCHESTRATOR STOPPED")
        logger.info("=" * 60)
    
    def stop(self) -> None:
        """Request graceful shutdown."""
        self._shutdown_requested = True
        self._running = False
