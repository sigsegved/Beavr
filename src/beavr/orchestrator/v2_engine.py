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
from beavr.broker.models import OrderRequest
from beavr.broker.protocols import BrokerProvider, MarketDataProvider, NewsProvider, ScreenerProvider
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


class CompanyNameCache:
    """
    Cache for mapping symbols to company names.
    
    Used to detect related symbols (e.g., GOOG/GOOGL are both Alphabet).
    Uses a simple cache; callers may populate it externally.
    """
    
    def __init__(self) -> None:
        self._cache: dict[str, str] = {}
    
    def _normalize_company_name(self, name: str) -> str:
        """
        Normalize company name for comparison.
        
        Removes common suffixes and variations to match
        'Alphabet Inc.' with 'Alphabet Inc. Class A', etc.
        """
        import re
        
        if not name:
            return ""
        
        # Convert to lowercase for comparison
        name = name.lower().strip()
        
        # Remove share class indicators (class a, class c capital stock, etc.)
        # This regex handles variations like "class a", "class c capital stock", etc.
        name = re.sub(r'\s+class\s+[a-z](\s+\w+)*', '', name)
        name = re.sub(r'\s+-\s+class\s+[a-z](\s+\w+)*', '', name)
        name = re.sub(r'\s+cl\s+[a-z]', '', name)
        name = re.sub(r'\s+series\s+[a-z]', '', name)
        
        # Remove common suffixes
        for suffix in [
            " common stock", " common", " ordinary shares", " capital stock",
            " (delaware)", " corp", " corporation", " inc", " inc.",
            " ltd", " ltd.", " limited", " plc", " llc", " n.v.", " nv",
            " holdings", " holding", " group", " co",
        ]:
            if name.endswith(suffix):
                name = name[:-len(suffix)].strip()
        
        # Remove trailing punctuation
        name = name.rstrip(".,- ")
        
        return name
    
    def set_name(self, symbol: str, name: str) -> None:
        """Manually set a company name for a symbol."""
        self._cache[symbol] = self._normalize_company_name(name)
    
    def get_company_name(self, symbol: str) -> str:
        """
        Get the normalized company name for a symbol.
        
        Returns cached name if available, otherwise returns the symbol itself.
        """
        if symbol in self._cache:
            return self._cache[symbol]
        
        # No broker-specific lookup; return symbol as fallback
        self._cache[symbol] = symbol
        return symbol
    
    def are_same_company(self, symbol1: str, symbol2: str) -> bool:
        """Check if two symbols represent the same company."""
        if symbol1 == symbol2:
            return True
        
        name1 = self.get_company_name(symbol1)
        name2 = self.get_company_name(symbol2)
        
        # Compare normalized names
        return name1 == name2


# Global cache instance
_company_cache = CompanyNameCache()


def get_company_name(symbol: str) -> str:
    """Get the normalized company name for a symbol."""
    return _company_cache.get_company_name(symbol)


def symbols_are_related(symbol1: str, symbol2: str) -> bool:
    """Check if two symbols represent the same company."""
    return _company_cache.are_same_company(symbol1, symbol2)


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
    # Track DD runs per symbol: {symbol: {"count": int, "last_run": str, "has_major_event": bool}}
    dd_runs_today: dict[str, dict] = Field(default_factory=dict)
    # Legacy field for backward compatibility - will be migrated to dd_runs_today
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
    overnight_sleep_interval: int = 1800  # 30 minutes for off-hours
    news_alert_interval: int = 300  # 5 minutes - continuous news scanning

    # Research scope
    market_movers_limit: int = 10
    news_limit: int = 25
    max_research_symbols: int = 25
    
    # DD limits
    max_dd_per_symbol_daily: int = 3  # Max DD runs per symbol per day
    dd_rerun_cooldown_minutes: int = 120  # Min minutes between DD reruns
    
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
        # Portfolio context (Phase 4)
        portfolio_id: Optional[str] = None,
        portfolio_directives: Optional[list[str]] = None,
        decision_store: Optional[Any] = None,
        snapshot_store: Optional[Any] = None,
        portfolio_store: Optional[Any] = None,
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
        
        # Portfolio context
        self.portfolio_id = portfolio_id
        self.portfolio_directives = portfolio_directives or []
        self.decision_store = decision_store
        self.snapshot_store = snapshot_store
        self.portfolio_store = portfolio_store
        
        # State
        self.state = SystemState()
        self._running = False
        self._shutdown_requested = False
        
        # Broker abstraction (set externally via set_trading_client)
        self._broker: Optional[BrokerProvider] = None
        self._data_provider: Optional[MarketDataProvider] = None
        
        # Context builder (set externally)
        self._ctx_builder = None
        
        # Protocol-based data utilities (set externally or via set_providers)
        self._screener: Optional[ScreenerProvider] = None
        self._news_provider: Optional[NewsProvider] = None

    # ------------------------------------------------------------------
    # Decision logging
    # ------------------------------------------------------------------

    def _log_decision(
        self,
        decision_type: str,
        action: str,
        symbol: Optional[str] = None,
        thesis_id: Optional[str] = None,
        dd_report_id: Optional[str] = None,
        position_id: Optional[str] = None,
        reasoning: Optional[str] = None,
        confidence: Optional[float] = None,
        amount: Optional[Decimal] = None,
        shares: Optional[Decimal] = None,
        price: Optional[Decimal] = None,
    ) -> None:
        """Log a decision to the audit trail (no-op if stores not wired)."""
        if not self.decision_store or not self.portfolio_id:
            return
        try:
            from beavr.models.portfolio_record import DecisionType, PortfolioDecision

            decision = PortfolioDecision(
                portfolio_id=self.portfolio_id,
                phase=self.state.current_phase.value,
                decision_type=DecisionType(decision_type),
                symbol=symbol,
                thesis_id=thesis_id,
                dd_report_id=dd_report_id,
                position_id=position_id,
                action=action,
                reasoning=reasoning,
                confidence=confidence,
                amount=amount,
                shares=shares,
                price=price,
            )
            self.decision_store.log_decision(decision)
        except Exception as e:
            logger.warning(f"Failed to log decision: {e}")

    # ------------------------------------------------------------------
    # Daily snapshot capture
    # ------------------------------------------------------------------

    def _capture_daily_snapshot(self) -> None:
        """Capture a point-in-time portfolio snapshot.

        Called once per day during the transition to AFTER_HOURS.
        No-op if snapshot_store or portfolio_id are not configured.
        """
        if not self.snapshot_store or not self.portfolio_id:
            return
        try:
            from beavr.models.portfolio_record import PortfolioSnapshot

            # Compute position market values from broker
            positions = self._broker.get_positions() if self._broker else []
            positions_value = Decimal("0")
            for pos in positions:
                qty = getattr(pos, "qty", None) or Decimal("0")
                price = getattr(pos, "current_price", None) or getattr(pos, "market_value", None) or Decimal("0")
                if qty and price:
                    positions_value += Decimal(str(qty)) * Decimal(str(price))

            cash = Decimal("0")
            if self._broker:
                try:
                    account = self._broker.get_account()
                    cash = Decimal(str(getattr(account, "cash", "0")))
                except Exception:
                    pass

            portfolio_value = cash + positions_value

            # Compute P&L from portfolio store
            cumulative_pnl = Decimal("0")
            cumulative_pnl_pct = 0.0
            initial_capital = Decimal("0")
            if self.portfolio_store:
                try:
                    record = self.portfolio_store.get_portfolio(self.portfolio_id)
                    if record:
                        cumulative_pnl = record.realized_pnl
                        initial_capital = record.initial_capital
                        if initial_capital > 0:
                            cumulative_pnl_pct = float(cumulative_pnl / initial_capital * 100)
                except Exception:
                    pass

            # Daily P&L: diff from previous snapshot
            daily_pnl = Decimal("0")
            daily_pnl_pct = 0.0
            try:
                prev_snapshots = self.snapshot_store.get_snapshots(self.portfolio_id)
                if prev_snapshots:
                    prev = prev_snapshots[-1]
                    daily_pnl = portfolio_value - prev.portfolio_value
                    if prev.portfolio_value > 0:
                        daily_pnl_pct = float(daily_pnl / prev.portfolio_value * 100)
                elif initial_capital > 0:
                    daily_pnl = portfolio_value - initial_capital
                    daily_pnl_pct = float(daily_pnl / initial_capital * 100)
            except Exception:
                pass

            snapshot = PortfolioSnapshot(
                portfolio_id=self.portfolio_id,
                snapshot_date=date.today(),
                portfolio_value=portfolio_value,
                cash=cash,
                positions_value=positions_value,
                daily_pnl=daily_pnl,
                daily_pnl_pct=daily_pnl_pct,
                cumulative_pnl=cumulative_pnl,
                cumulative_pnl_pct=cumulative_pnl_pct,
                open_positions=len(positions),
                trades_today=self.state.trades_today,
            )
            self.snapshot_store.take_snapshot(snapshot)
            logger.info(
                f"📸 Daily snapshot: value=${portfolio_value:.2f}, "
                f"daily P&L=${daily_pnl:.2f}, positions={len(positions)}"
            )
        except Exception as e:
            logger.warning(f"Failed to capture daily snapshot: {e}")

    # Protocol-based data utilities (set externally or via set_providers)

    def set_trading_client(
        self,
        broker: BrokerProvider,
        data_provider: MarketDataProvider,
        screener: Optional[ScreenerProvider] = None,
        news_provider: Optional[NewsProvider] = None,
    ) -> None:
        """Set the broker, data, screener, and news providers."""
        self._broker = broker
        self._data_provider = data_provider
        if screener is not None:
            self._screener = screener
        if news_provider is not None:
            self._news_provider = news_provider
    
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
        self._check_daily_reset()
    
    def _check_daily_reset(self) -> None:
        """Reset daily counters when the date rolls over.
        
        Called at startup (via _load_state) and at the top of every
        main-loop iteration so that an orchestrator running continuously
        across midnight correctly resets trades_today, daily_pnl, etc.
        """
        today = date.today()
        if self.state.current_date != today:
            logger.info(f"New day: {today}, resetting daily state")
            self.state.current_date = today
            self.state.trades_today = 0
            self.state.daily_pnl = Decimal("0")
            self.state.invested_today = False
            self.state.active_day_trades = []
            self.state.dd_completed_tonight = []
            self.state.dd_runs_today = {}
            self.state.last_research_run = None
            self._save_state()
    
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
                self._log_decision(
                    decision_type="circuit_breaker_reset",
                    action="resume_trading",
                    reasoning="Cooldown period expired",
                )
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
        self._log_decision(
            decision_type="circuit_breaker_triggered",
            action="halt_trading",
            reasoning=reason,
        )
        self._save_state()
    
    def _has_related_position(self, symbol: str) -> bool:
        """
        Check if we already have a position in this symbol or a related symbol.
        
        For example, GOOG and GOOGL are both Alphabet - we should only hold one.
        Uses company name cache to dynamically detect related symbols.
        """
        # Check active swing trades
        for held in self.state.active_swing_trades:
            if symbols_are_related(symbol, held):
                return True
        
        # Check active day trades
        return any(symbols_are_related(symbol, held) for held in self.state.active_day_trades)
    
    def _is_related_to_any(self, symbol: str, symbols: set[str]) -> Optional[str]:
        """
        Check if symbol is related to any symbol in the set.
        
        Returns the related symbol if found, None otherwise.
        """
        for s in symbols:
            if symbols_are_related(symbol, s):
                return s
        return None
    
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

    def _get_market_screener(self) -> Optional[ScreenerProvider]:
        """Return the configured screener provider, if any."""
        return self._screener

    def _get_news_scanner(self) -> Optional[NewsProvider]:
        """Return the configured news provider, if any."""
        return self._news_provider

    def _fetch_market_mover_events(self) -> list[MarketEvent]:
        """Fetch market mover symbols and convert to synthetic events."""
        screener = self._get_market_screener()
        if not screener:
            return []

        max_retries = 3
        movers: Optional[list[dict]] = None
        for attempt in range(max_retries):
            try:
                movers = screener.get_market_movers(top=self.config.market_movers_limit)
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

        for mover in movers:
            symbol = mover.get("symbol", "")
            change_pct = float(mover.get("change_pct", mover.get("percent_change", 0)))
            if not symbol:
                continue
            if change_pct >= 0:
                events.append(
                    MarketEvent(
                        event_type=EventType.NEWS_CATALYST,
                        symbol=symbol,
                        headline=f"Top gainer: {symbol}",
                        summary=f"{symbol} up {change_pct:+.1f}% as a top gainer",
                        source="market_movers",
                        timestamp=datetime.now(),
                        importance=EventImportance.MEDIUM,
                    )
                )
            else:
                events.append(
                    MarketEvent(
                        event_type=EventType.NEWS_CATALYST,
                        symbol=symbol,
                        headline=f"Top loser: {symbol}",
                        summary=f"{symbol} down {change_pct:+.1f}% as a top loser",
                        source="market_movers",
                        timestamp=datetime.now(),
                        importance=EventImportance.MEDIUM,
                    )
                )

        # Fetch most actives separately via protocol
        try:
            actives = screener.get_most_actives(top=self.config.market_movers_limit)
            for active in actives:
                active_symbol = active.get("symbol", "")
                if active_symbol:
                    events.append(
                        MarketEvent(
                            event_type=EventType.OTHER,
                            symbol=active_symbol,
                            headline=f"Most active: {active_symbol}",
                            summary=f"{active_symbol} is among the most active by volume",
                            source="market_movers",
                            timestamp=datetime.now(),
                            importance=EventImportance.MEDIUM,
                        )
                    )
        except Exception as e:
            logger.warning(f"Most actives fetch failed: {e}")

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
        news_provider = self._get_news_scanner()
        if not news_provider:
            return []

        max_retries = 3
        for attempt in range(max_retries):
            try:
                return news_provider.get_news(
                    symbols=symbols if symbols else [],
                    limit=self.config.news_limit,
                )
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
        if not self.news_monitor:
            logger.warning("News monitor not configured - skipping classification")
            return []
        if not news_items:
            return []

        # Log raw news for debugging
        for item in news_items[:5]:  # Log first 5
            headline = item.get("headline", item.get("title", ""))
            summary = item.get("summary", "")[:100]
            symbols = item.get("symbols", [])
            logger.info(f"  📰 News: {headline or '(no headline)'}")
            if summary:
                logger.info(f"      Summary: {summary}...")
            logger.info(f"      Symbols: {symbols or 'none'}")

        try:
            events = self.news_monitor.monitor_cycle(news_items)
            logger.info(f"  ✅ Classified {len(events)} actionable events from {len(news_items)} news items")
            return events
        except Exception as e:
            logger.warning(f"News classification failed: {e}")
            return []

    def _scan_breaking_news(self) -> None:
        """
        Scan for breaking news alerts during off-hours.
        
        This runs continuously to catch major market-moving events that
        may require immediate thesis generation or position adjustments.
        Only processes HIGH importance events to avoid noise.
        """
        try:
            # Fetch general market news (no symbol filter)
            news_items = self._fetch_news_items([])
            if not news_items:
                return
            
            # Classify into events
            events = self._classify_news_events(news_items)
            if not events:
                return
            
            # Filter for HIGH importance only
            high_importance_events = [
                e for e in events 
                if e.importance == EventImportance.HIGH
            ]
            
            if not high_importance_events:
                logger.info("  📰 No high-importance breaking news")
                return
            
            logger.info(f"  🚨 Found {len(high_importance_events)} HIGH importance events!")
            
            # Store events
            if self.events_repo:
                for event in high_importance_events:
                    try:
                        self.events_repo.create(event)
                        logger.info(f"     📌 {event.symbol or 'MARKET'}: {event.headline[:60]}...")
                    except Exception as e:
                        logger.warning(f"Failed to store event: {e}")
            
            # Generate theses from breaking events
            created_theses = self._generate_theses_from_events(high_importance_events)
            if created_theses:
                logger.info(f"  ✅ Created {len(created_theses)} theses from breaking news")
                
        except Exception as e:
            logger.warning(f"Breaking news scan failed: {e}")

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

            self._log_decision(
                decision_type="thesis_created",
                action="create",
                symbol=thesis.symbol,
                thesis_id=thesis.id,
                reasoning=thesis.entry_rationale,
                confidence=thesis.confidence,
            )

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

    def _should_run_dd(self, symbol: str, has_major_event: bool = False) -> tuple[bool, str]:
        """
        Check if DD should run for a symbol.
        
        Rules:
        1. Max 3 DD runs per symbol per day
        2. At least 2 hours between DD reruns (unless major event)
        3. First DD always runs
        4. Subsequent DD only if major event or cooldown passed
        
        Args:
            symbol: The stock symbol
            has_major_event: Whether there's a major event for this symbol
            
        Returns:
            Tuple of (should_run, reason)
        """
        dd_info = self.state.dd_runs_today.get(symbol, {})
        dd_count = dd_info.get("count", 0)
        last_run_str = dd_info.get("last_run")
        
        # First DD for this symbol today - always run
        if dd_count == 0:
            return True, "first DD of day"
        
        # Check max DD limit
        if dd_count >= self.config.max_dd_per_symbol_daily:
            return False, f"max {self.config.max_dd_per_symbol_daily} DD/day reached"
        
        # Check cooldown
        if last_run_str:
            try:
                last_run = datetime.fromisoformat(last_run_str)
                elapsed_minutes = (datetime.now() - last_run).total_seconds() / 60
                
                # Major event bypasses cooldown
                if has_major_event:
                    return True, f"major event (run #{dd_count + 1})"
                
                # Check cooldown
                if elapsed_minutes < self.config.dd_rerun_cooldown_minutes:
                    remaining = int(self.config.dd_rerun_cooldown_minutes - elapsed_minutes)
                    return False, f"cooldown ({remaining}m remaining)"
                    
            except (ValueError, TypeError):
                pass  # Invalid date format, allow DD
        
        # Cooldown passed but no major event - still allow if explicitly requested
        if has_major_event:
            return True, f"major event (run #{dd_count + 1})"
        
        # No major event and not first run - be conservative
        return False, "no major event for re-DD"

    def _record_dd_run(self, symbol: str, has_major_event: bool = False) -> None:
        """Record that DD was run for a symbol."""
        dd_info = self.state.dd_runs_today.get(symbol, {"count": 0})
        dd_info["count"] = dd_info.get("count", 0) + 1
        dd_info["last_run"] = datetime.now().isoformat()
        dd_info["has_major_event"] = has_major_event
        self.state.dd_runs_today[symbol] = dd_info
        
        # Also maintain legacy list for backward compatibility
        if symbol not in self.state.dd_completed_tonight:
            self.state.dd_completed_tonight.append(symbol)

    def _has_major_event_for_symbol(self, symbol: str) -> bool:
        """Check if there's a major/high importance unprocessed event for symbol."""
        if not self.events_repo:
            return False
        
        try:
            from beavr.models.market_event import EventImportance
            unprocessed = self.events_repo.get_unprocessed()
            for event in unprocessed:
                if event.symbol == symbol and event.importance == EventImportance.HIGH:
                    return True
        except Exception:
            pass
        
        return False
    
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
        
        # Track stats for this cycle
        dd_run_count = 0
        dd_skipped_count = 0

        for thesis in candidates:
            symbol = thesis.symbol
            
            # Check for major event for this symbol
            has_major_event = self._has_major_event_for_symbol(symbol)
            
            # Check if we should run DD
            should_run, reason = self._should_run_dd(symbol, has_major_event)
            
            if not should_run:
                logger.info(f"  ⏭️  Skipping {symbol}: {reason}")
                dd_skipped_count += 1
                continue

            logger.info(f"\n🔬 Researching {symbol}... ({reason})")
            logger.info(f"   Trade Type: {thesis.trade_type.value}")
            logger.info(f"   Catalyst: {thesis.catalyst[:80]}...")

            try:
                ctx = self._build_context([symbol])

                dd_report = self.dd_agent.analyze_thesis(thesis, ctx)

                if dd_report:
                    # Save report
                    if self.dd_repo:
                        self.dd_repo.create(dd_report)

                    # Process recommendation
                    if dd_report.recommendation == DDRecommendation.APPROVE:
                        logger.info(f"   ✅ APPROVED (confidence: {dd_report.confidence:.0%})")
                        thesis.dd_approved = True
                        thesis.dd_report_id = dd_report.id
                        thesis.status = ThesisStatus.ACTIVE
                        thesis.entry_price_target = dd_report.recommended_entry
                        thesis.profit_target = dd_report.recommended_target
                        thesis.stop_loss = dd_report.recommended_stop
                        self._log_decision(
                            decision_type="dd_approved",
                            action="approve",
                            symbol=symbol,
                            thesis_id=thesis.id,
                            dd_report_id=dd_report.id,
                            confidence=dd_report.confidence,
                            reasoning=f"DD approved: {dd_report.recommendation.value}",
                        )

                    elif dd_report.recommendation == DDRecommendation.CONDITIONAL:
                        logger.info(f"   ⚠️  CONDITIONAL (confidence: {dd_report.confidence:.0%})")
                        thesis.dd_report_id = dd_report.id
                        self._log_decision(
                            decision_type="dd_conditional",
                            action="conditional",
                            symbol=symbol,
                            thesis_id=thesis.id,
                            dd_report_id=dd_report.id,
                            confidence=dd_report.confidence,
                        )

                    else:
                        reason = dd_report.rejection_rationale or "No reason provided"
                        logger.info(f"   ❌ REJECTED: {reason}")
                        thesis.status = ThesisStatus.INVALIDATED
                        thesis.dd_report_id = dd_report.id
                        self._log_decision(
                            decision_type="dd_rejected",
                            action="reject",
                            symbol=symbol,
                            thesis_id=thesis.id,
                            dd_report_id=dd_report.id,
                            reasoning=reason,
                        )

                    # Update thesis in DB
                    try:
                        self.thesis_repo.update(thesis)
                    except Exception as update_err:
                        logger.error(f"   Failed to update thesis: {update_err}")

                # Record DD run (even if thesis update failed)
                self._record_dd_run(symbol, has_major_event)
                dd_run_count += 1

            except Exception as e:
                logger.error(f"   Error running DD for {symbol}: {e}")
                # Still record the attempt to prevent infinite retries
                self._record_dd_run(symbol, has_major_event)

            time.sleep(2)

        self._save_state()
        logger.info(f"\n✅ DD cycle complete: {dd_run_count} run, {dd_skipped_count} skipped")

    def _run_overnight_dd_cycle(self) -> None:
        """
        Run the overnight DD research cycle.

        This is the deep research phase where we:
        1. Scan earnings calendar (if configured)
        2. Get pending theses that need DD
        3. Run DD agent on each
        4. Save DD reports
        5. Mark theses as approved/rejected
        """
        # Step 1: Earnings calendar scan
        self._scan_earnings_calendar()

        # Step 2-5: Regular DD cycle
        candidates = self._get_pending_dd_candidates()
        self._run_dd_cycle(candidates, "🌙 OVERNIGHT DD RESEARCH CYCLE")

    def _scan_earnings_calendar(self) -> None:
        """Daily earnings calendar scan — runs once during OVERNIGHT_DD phase.

        Fetches upcoming earnings, generates theses via EarningsPlayAgent,
        and queues them for DD (standard pipeline).
        """
        if not hasattr(self, "_earnings_fetcher") or not self._earnings_fetcher:
            return
        if not hasattr(self, "_earnings_agent") or not self._earnings_agent:
            return

        try:
            events = self._earnings_fetcher.fetch_upcoming_earnings(horizon_days=14)
            if not events:
                return

            logger.info(f"📅 Earnings scan found {len(events)} upcoming events")
            self._log_decision(
                decision_type="earnings_scan",
                action=f"found {len(events)} upcoming earnings",
            )

            # Filter to events within 5 days and build context
            today = date.today()
            near_events = [
                e for e in events
                if e.earnings_date and 0 <= (e.earnings_date - today).days <= 5
            ]

            if not near_events:
                logger.info("📅 No earnings within 5-day window")
                return

            for event in near_events:
                if not event.symbol:
                    continue

                try:
                    ctx = self._build_context([event.symbol])
                    thesis = self._earnings_agent.analyze_earnings_opportunity(event, ctx)
                    if thesis and self.thesis_repo:
                        self.thesis_repo.save_thesis(thesis)
                        logger.info(f"📅 Generated earnings thesis for {event.symbol}")
                        self._log_decision(
                            decision_type="thesis_created",
                            action="earnings_play",
                            symbol=event.symbol,
                            reasoning=thesis.entry_rationale,
                            confidence=thesis.confidence,
                        )
                except Exception as exc:
                    logger.warning(f"Earnings analysis failed for {event.symbol}: {exc}")

        except Exception as exc:
            logger.warning(f"Earnings calendar scan failed: {exc}")
    
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
        
        # Filter: only day trades, and skip if already holding related symbol
        day_trades = []
        for t in approved:
            if t.trade_type != TradeType.DAY_TRADE:
                continue
            if self._has_related_position(t.symbol):
                continue
            day_trades.append(t)
        
        if not day_trades:
            logger.info("No approved day trades for today")
            return
        
        logger.info(f"📋 {len(day_trades)} approved day trades to execute")
        
        # Track symbols we're about to trade this cycle
        traded_this_cycle: set[str] = set()
        
        for thesis in day_trades:
            if self.state.trades_today >= self.config.daily_trade_limit:
                logger.info("Daily trade limit reached")
                break
            
            # Skip if we already traded a related symbol this cycle
            related_symbol = self._is_related_to_any(thesis.symbol, traded_this_cycle)
            if related_symbol:
                logger.info(f"   ⏭️  Skipping {thesis.symbol}: already trading related symbol {related_symbol}")
                continue
            
            try:
                self._execute_trade(thesis, is_day_trade=True)
                traded_this_cycle.add(thesis.symbol)
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
        
        # Filter: skip if already holding this symbol OR a related symbol
        swing_trades = []
        for t in approved:
            if t.trade_type == TradeType.DAY_TRADE:
                continue
            # Check if already holding this symbol or related symbol (e.g., GOOG/GOOGL)
            if self._has_related_position(t.symbol):
                continue
            swing_trades.append(t)
        
        if not swing_trades:
            return  # No need to log - this is continuous
        
        logger.info("=" * 40)
        logger.info("📊 SWING TRADE EXECUTION")
        logger.info("=" * 40)
        logger.info(f"📋 {len(swing_trades)} approved swing trades to execute")
        
        # Track symbols we're about to trade this cycle to avoid duplicates
        traded_this_cycle: set[str] = set()
        
        for thesis in swing_trades:
            if self.state.trades_today >= self.config.daily_trade_limit:
                logger.info("Daily trade limit reached")
                break
            
            # Skip if we already traded a related symbol this cycle
            related_symbol = self._is_related_to_any(thesis.symbol, traded_this_cycle)
            if related_symbol:
                logger.info(f"   ⏭️  Skipping {thesis.symbol}: already trading related symbol {related_symbol}")
                continue
            
            try:
                self._execute_trade(thesis, is_day_trade=False)
                traded_this_cycle.add(thesis.symbol)
            except Exception as e:
                logger.error(f"Error executing swing trade {thesis.symbol}: {e}")
    
    def _execute_trade(self, thesis: TradeThesis, is_day_trade: bool = False) -> bool:
        """Execute a trade based on an approved thesis."""
        if not self._broker:
            logger.warning("Broker not configured")
            return False
        
        logger.info(f"\n💰 Executing {'DAY TRADE' if is_day_trade else 'SWING'}: {thesis.symbol}")
        
        try:
            # Get current portfolio value
            account = self._broker.get_account()
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
            
            # Execute order via broker abstraction
            order_request = OrderRequest(
                symbol=thesis.symbol,
                notional=Decimal(str(round(float(position_value), 2))),
                side="buy",
                order_type="market",
                tif="day",
            )
            
            order = self._broker.submit_order(order_request)
            
            logger.info(f"   ✅ Order submitted: {order.order_id}")
            
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
            
            self._log_decision(
                decision_type="trade_entered",
                action="buy",
                symbol=thesis.symbol,
                thesis_id=thesis.id,
                dd_report_id=thesis.dd_report_id,
                reasoning=thesis.entry_rationale[:200],
                confidence=thesis.confidence,
                amount=position_value,
                shares=shares,
                price=current_price,
            )

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
        if not self._broker:
            return
        
        try:
            positions = self._broker.get_positions()
            
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
                # Compute unrealized P&L percentage from BrokerPosition fields
                cost_basis = pos.avg_cost * pos.qty
                pnl_pct = (
                    float(pos.unrealized_pl / cost_basis) * 100
                    if cost_basis > 0
                    else 0.0
                )
                
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
        """Close a position by selling all shares."""
        if not self._broker:
            return
        
        try:
            # Find position and compute exit price before selling
            positions = self._broker.get_positions()
            pos = next((p for p in positions if p.symbol == symbol), None)
            exit_price = (
                float(pos.market_value / pos.qty) if pos and pos.qty > 0 else 0.0
            )
            
            if pos and pos.qty > 0:
                self._broker.submit_order(
                    OrderRequest(
                        symbol=symbol,
                        quantity=pos.qty,
                        side="sell",
                        order_type="market",
                        tif="day",
                    )
                )
            
            logger.info(f"✅ Closed {symbol} ({reason}): {pnl_pct:+.1f}%")
            
            # Map reason to decision type
            _reason_to_type = {
                "target_hit": "position_exit_target",
                "stop_loss": "position_exit_stop",
                "day_trade_deadline": "position_exit_time",
                "invalidated": "position_exit_invalidated",
                "manual": "position_exit_manual",
            }
            exit_decision_type = _reason_to_type.get(reason, "position_exit_manual")

            is_win = pnl_pct > 0
            trade_pnl = Decimal(str(round(pnl_pct, 2)))
            self._log_decision(
                decision_type=exit_decision_type,
                action="sell",
                symbol=symbol,
                reasoning=f"Exit: {reason} ({pnl_pct:+.1f}%)",
                price=Decimal(str(exit_price)) if exit_price else None,
            )
            # Update portfolio stats
            if self.portfolio_store and self.portfolio_id:
                try:
                    self.portfolio_store.update_portfolio_stats(
                        self.portfolio_id, trade_pnl, is_win=is_win
                    )
                except Exception as stats_err:
                    logger.warning(f"Failed to update portfolio stats: {stats_err}")
            
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
                # Reset daily counters on date rollover (critical for
                # continuous operation across midnight)
                self._check_daily_reset()
                
                now = datetime.now(ET)
                current_phase = self._get_current_phase()
                
                # Log phase changes
                if current_phase != self.state.current_phase:
                    logger.info(f"\n📍 Phase change: {self.state.current_phase.value} → {current_phase.value}")
                    self._log_decision(
                        decision_type="phase_transition",
                        action=f"{self.state.current_phase.value} -> {current_phase.value}",
                    )
                    # Capture daily snapshot when leaving MARKET_HOURS
                    if self.state.current_phase == OrchestratorPhase.MARKET_HOURS:
                        self._capture_daily_snapshot()
                    self.state.current_phase = current_phase
                    self._save_state()
                
                # Run phase-specific logic
                if current_phase == OrchestratorPhase.OVERNIGHT_DD:
                    # Get pending DD candidates
                    pending = self._get_pending_dd_candidates()
                    logger.info(f"🌙 Overnight DD | Pending Candidates: {len(pending)}")
                    
                    # Run DD cycle if there are pending candidates
                    dd_was_run = False
                    if pending:
                        # Run the DD cycle - it tracks what was actually processed
                        self._run_overnight_dd_cycle()
                        
                        # Re-check pending to see if any work remains
                        remaining_pending = self._get_pending_dd_candidates()
                        # If we still have the same pending (all were skipped), no real work was done
                        dd_was_run = len(remaining_pending) < len(pending)
                    
                    # Decide sleep duration
                    if dd_was_run:
                        # We actually did DD work - short sleep to continue processing
                        logger.info(f"💤 Sleeping {self.config.position_check_interval}s between DD cycles...")
                        time.sleep(self.config.position_check_interval)
                    else:
                        # No DD work done - check for news or sleep long
                        time_since_news = (datetime.now(ET) - last_news_check).total_seconds()
                        if time_since_news >= self.config.news_alert_interval:
                            logger.info("📰 Scanning for breaking news...")
                            self._scan_breaking_news()
                            # Set last_news_check to NOW (after scan completes) to account for scan duration
                            last_news_check = datetime.now(ET)
                            
                            # Check if news created new theses
                            new_pending = self._get_pending_dd_candidates()
                            if new_pending and len(new_pending) > len(pending):
                                logger.info(f"  📝 News created {len(new_pending) - len(pending)} new thesis candidates")
                                # Short sleep to process them next iteration
                                time.sleep(60)
                            else:
                                # No new work - sleep until next news scan
                                logger.info(f"💤 No work. Sleeping {self.config.news_alert_interval // 60}m until next news scan...")
                                time.sleep(self.config.news_alert_interval)
                        else:
                            # No news needed yet - sleep until next news scan
                            remaining = max(60, int(self.config.news_alert_interval - time_since_news))
                            logger.info(f"💤 No work. Sleeping {remaining // 60}m until next news scan...")
                            time.sleep(remaining)
                    
                elif current_phase == OrchestratorPhase.PRE_MARKET:
                    # Heartbeat log
                    approved = self._get_approved_theses()
                    logger.info(f"🌅 Pre-Market | Approved Theses: {len(approved)} | Candidates: {len(candidates_today)}")
                    
                    # Run morning scan once
                    if not candidates_today:
                        candidates_today = self._run_pre_market_scan()
                    
                    # Continuous news scanning for breaking alerts
                    if (now - last_news_check).total_seconds() > self.config.news_alert_interval:
                        logger.info("📰 Scanning for breaking news...")
                        self._scan_breaking_news()
                        last_news_check = now
                    
                    logger.info(f"💤 Sleeping {self.config.position_check_interval}s...")
                    time.sleep(self.config.position_check_interval)
                    
                elif current_phase == OrchestratorPhase.POWER_HOUR:
                    # Heartbeat log
                    approved = self._get_approved_theses()
                    day_trades = [t for t in approved if t.trade_type == TradeType.DAY_TRADE]
                    positions = self._broker.get_positions() if self._broker else []
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
                    positions = self._broker.get_positions() if self._broker else []
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
                    # Reset for next day
                    candidates_today = []

                    # Check for pending DD work (theses from market hours)
                    pending = self._get_pending_dd_candidates()
                    if pending:
                        logger.info(
                            f"🌆 After Hours | {len(pending)} pending DD candidates — running research..."
                        )
                        self._run_dd_cycle(pending, "🌆 AFTER-HOURS DD CYCLE")
                        # Short sleep then re-check
                        time.sleep(self.config.position_check_interval)
                    else:
                        # No DD work — scan for breaking news
                        time_since_news = (datetime.now(ET) - last_news_check).total_seconds()
                        if time_since_news >= self.config.news_alert_interval:
                            logger.info("🌆 After Hours | Scanning for breaking news...")
                            self._scan_breaking_news()
                            last_news_check = datetime.now(ET)

                            # Check if news created new theses
                            new_pending = self._get_pending_dd_candidates()
                            if new_pending:
                                logger.info(
                                    f"  📝 News created {len(new_pending)} new thesis candidates"
                                )
                                time.sleep(60)
                            else:
                                logger.info(
                                    f"💤 No work. Sleeping {self.config.news_alert_interval // 60}m until next news scan..."
                                )
                                time.sleep(self.config.news_alert_interval)
                        else:
                            remaining = max(
                                60,
                                int(self.config.news_alert_interval - time_since_news),
                            )
                            logger.info(
                                f"🌆 After Hours | Sleeping {remaining // 60}m until next news scan..."
                            )
                            time.sleep(remaining)
                
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
