# Spec: Auto Consolidation, Portfolio Sessions & Earnings Integration

**Date:** 2026-02-15  
**Updated:** 2026-02-16  
**Status:** Draft v3  
**Branch:** `ai_investor_redo`

---

## 1. Problem Statement

The codebase has two autonomous trading commands (`bvr ai auto` and `bvr ai auto-v2`) with overlapping intent but divergent architectures. The V1 `auto` is a flat loop with no thesis pipeline, while V2 is a multi-phase, thesis-driven orchestrator. V1 is effectively dead code. Additionally, V2 persists ephemeral state to a JSON file but does not create a durable portfolio record in SQLite — making audit, replay, and historical analysis impossible. Finally, the platform has models and schema for earnings events but no actual data source to populate them.

Beyond persistence, there is no concept of a **portfolio as a first-class session**. The user may want to run multiple `bvr ai` sessions simultaneously — one paper-trading, one live — each with its own configuration, risk parameters, and personality. Every session must be bound to a portfolio, and paper/live data must **never** mix.

### Goals

1. **Deprecate & remove V1 `auto`** — eliminate dead code, rename `auto-v2` → `auto`
2. **Portfolio-bound sessions** — every `bvr ai auto` run is tied to a named portfolio with its own config, mode (paper/live), and personality
3. **Repository abstraction layer** — Protocol-based interfaces so SQLite can be swapped for DynamoDB/CosmosDB/PostgreSQL without re-architecture
4. **Full audit trail** — every decision (thesis → DD → trade → exit) persisted via repository interfaces, viewable via `bvr ai history`
5. **Clean slate command** — ability to wipe all data and start fresh
6. **Earnings calendar integration** — fetch upcoming earnings and surface them as actionable events

---

## 2. Requirement 1: Deprecate `auto`, Promote `auto-v2`

### Current State

| Command | Function | Location | Lines |
|---------|----------|----------|-------|
| `bvr ai auto` | `auto()` | `src/beavr/cli/ai.py` | ~1017–1300 |
| `bvr ai auto-v2` | `auto_v2()` | `src/beavr/cli/ai.py` | ~1782–1984 |

V1 `auto` uses `AIInvestor.analyze_opportunities()` directly, tracks positions in `ai_positions` (V1 table), and has no thesis/DD pipeline. It is superseded by V2 in every way.

### Changes Required

#### 2.1 CLI Layer (`src/beavr/cli/ai.py`)

| Action | Detail |
|--------|--------|
| Delete `auto()` function | Remove lines ~1017–1300 (the entire V1 `auto` command) |
| Rename `auto_v2()` → `auto()` | Change function name, update Typer decorator from `"auto-v2"` to `"auto"` |
| Update help text | Remove any "V2" qualifier — this is now *the* auto command |
| Preserve all V2 options | `--target`, `--max-dd`, `--dt-target`, `--dt-stop`, `--daily-limit`, `--capital`, `--research-interval`, `--test`, `--once` |

#### 2.2 Dead Code Cleanup

| File | Action |
|------|--------|
| `src/beavr/cli/ai.py` | Remove V1-only helper functions used exclusively by old `auto()` (e.g., `_log_state()` for V1 state file, V1 position monitoring loop code) |
| `logs/ai_investor/auto_state.json` | Add to `.gitignore` / note for cleanup |
| `src/beavr/db/ai_positions.py` | Keep `AIPositionsRepository` — still used by `invest`, `watch`, `sell`, `history` commands |
| `src/beavr/db/schema.py` | Keep `ai_positions` + `ai_trades` tables — still used by V1 commands that remain active |

#### 2.3 V1 Commands That Stay

These commands use V1 infrastructure (`AIInvestor`, `AIPositionsRepository`) and are **not** being removed:

- `bvr ai invest` — single investment
- `bvr ai watch` — position monitor
- `bvr ai sell` — sell positions
- `bvr ai status` — portfolio status
- `bvr ai analyze` — market analysis
- `bvr ai history` — trade history

These can be migrated to V2 infrastructure in a future iteration.

#### 2.4 Risk Assessment

| Risk | Mitigation |
|------|------------|
| Users referencing `auto-v2` in scripts | Low risk — internal tool, single user |
| V1 `ai_positions` table orphaned | Keep table; `history` command still reads it |

---

## 3. Requirement 2: Portfolio Sessions — The Core Concept

### Design Philosophy

A **portfolio** is the fundamental unit of operation in Beavr AI. Every `bvr ai auto` session is bound to exactly one portfolio. A portfolio encapsulates:

- **Identity** — name, creation date, trading mode (paper vs live)
- **Configuration** — risk parameters, aggressiveness, capital allocation, model preferences
- **Personality** — user-provided directives that steer how the AI trades (e.g., "focus on tech sector", "be conservative", "avoid meme stocks")
- **Audit trail** — every thesis, DD report, trade, and decision logged against this portfolio
- **State** — runtime state (circuit breakers, daily counters) scoped to this portfolio

Paper and live portfolios are **strictly isolated** — they never share data, positions, or state.

### Session Lifecycle

```
┌──────────────────────────────────────────────────────────┐
│  bvr ai auto                                             │
│  ┌─────────────────────────────────────────┐             │
│  │  Portfolio Selection                     │             │
│  │  ┌───────────────┐ ┌──────────────────┐ │             │
│  │  │ Resume existing│ │ Create new       │ │             │
│  │  │ portfolio      │ │ portfolio        │ │             │
│  │  └───────┬───────┘ └────────┬─────────┘ │             │
│  │          │                  │            │             │
│  │          │           Setup Wizard:       │             │
│  │          │           • Name              │             │
│  │          │           • Mode (paper/live) │             │
│  │          │           • Aggressiveness    │             │
│  │          │           • Custom directives │             │
│  │          │           • Capital allocation│             │
│  │          ▼                  ▼            │             │
│  │    ┌──────────────────────────┐          │             │
│  │    │  Orchestrator runs with  │          │             │
│  │    │  portfolio context       │          │             │
│  │    └──────────────────────────┘          │             │
│  └─────────────────────────────────────────┘             │
└──────────────────────────────────────────────────────────┘
```

### Current State

V2 persists runtime state to `logs/ai_investor/v2_state.json` (a `SystemState` Pydantic model). This tracks ephemeral session data (trades today, circuit breaker status, active trades list) but does **not** durably record:

- Portfolio creation / lifecycle
- Which capital was allocated and when
- Decision audit trail linking thesis → DD → trade → exit with timestamps
- Portfolio-level P&L over time
- Configuration snapshots at time of run
- User directives / personality
- Whether this is paper or live trading

The existing V2 schema has `trade_theses`, `dd_reports`, `ai_positions_v2`, and `position_reviews` tables — these capture per-trade decisions but lack a portfolio container.

### New Schema Additions

#### 3.1 `portfolios` Table

```sql
CREATE TABLE IF NOT EXISTS portfolios (
    id TEXT PRIMARY KEY,                    -- UUID
    name TEXT NOT NULL UNIQUE,              -- User-friendly name (e.g., "Paper - Aggressive Tech")
    created_at TEXT NOT NULL,               -- ISO timestamp
    closed_at TEXT,                         -- NULL = active
    status TEXT NOT NULL DEFAULT 'active',  -- active | paused | closed
    
    -- Trading mode (NEVER mix paper and live)
    mode TEXT NOT NULL,                     -- 'paper' | 'live'
    
    -- Capital allocation
    initial_capital TEXT NOT NULL,          -- Decimal as string
    allocated_capital TEXT NOT NULL,        -- Decimal (capital_pct of portfolio)
    current_cash TEXT NOT NULL,             -- Remaining uninvested cash
    
    -- Configuration snapshot (full config at creation time)
    config_snapshot TEXT NOT NULL,          -- JSON dump of V2Config at creation time
    
    -- AI Personality / Directives
    aggressiveness TEXT NOT NULL DEFAULT 'moderate',  -- conservative | moderate | aggressive
    directives TEXT,                        -- JSON array of user-provided directives
                                            -- e.g., ["Focus on tech and AI sectors",
                                            --        "Avoid penny stocks",
                                            --        "Prefer high-volume names"]
    
    -- Running totals (updated on each trade)
    total_invested TEXT NOT NULL DEFAULT '0',
    total_returned TEXT NOT NULL DEFAULT '0',
    realized_pnl TEXT NOT NULL DEFAULT '0',
    total_trades INTEGER NOT NULL DEFAULT 0,
    winning_trades INTEGER NOT NULL DEFAULT 0,
    losing_trades INTEGER NOT NULL DEFAULT 0,
    
    -- Risk state
    peak_value TEXT NOT NULL DEFAULT '0',
    max_drawdown_pct REAL NOT NULL DEFAULT 0.0,
    
    -- Metadata
    notes TEXT
);
```

#### 3.2 `portfolio_decisions` Table (Audit Log)

Every significant decision gets logged — this is the core audit trail.

```sql
CREATE TABLE IF NOT EXISTS portfolio_decisions (
    id TEXT PRIMARY KEY,                    -- UUID
    portfolio_id TEXT NOT NULL,             -- FK → portfolios
    timestamp TEXT NOT NULL,                -- ISO timestamp
    phase TEXT NOT NULL,                    -- orchestrator phase when decision was made
    decision_type TEXT NOT NULL,            -- See enum below
    symbol TEXT,                            -- Relevant symbol (nullable for portfolio-level decisions)
    
    -- Linked entities (nullable — not all decisions have all links)
    thesis_id TEXT,                         -- FK → trade_theses
    dd_report_id TEXT,                      -- FK → dd_reports
    position_id TEXT,                       -- FK → ai_positions_v2
    event_id TEXT,                          -- FK → market_events
    
    -- Decision data
    action TEXT NOT NULL,                   -- What was decided (buy, sell, skip, hold, etc.)
    reasoning TEXT,                         -- LLM or rule-based reasoning
    confidence REAL,                        -- 0.0–1.0
    
    -- Financial impact
    amount TEXT,                            -- Decimal — dollar amount involved
    shares TEXT,                            -- Decimal — shares involved
    price TEXT,                             -- Decimal — price at decision time
    
    -- Outcome (filled in later)
    outcome TEXT,                           -- success | failure | pending
    outcome_details TEXT,                   -- JSON with actual results
    
    FOREIGN KEY (portfolio_id) REFERENCES portfolios(id)
);
```

**`decision_type` Enum:**

| Value | When Logged |
|-------|-------------|
| `thesis_created` | New thesis generated from event |
| `thesis_rejected` | Thesis below confidence threshold |
| `dd_approved` | DD agent approves trade |
| `dd_rejected` | DD agent rejects trade |
| `dd_conditional` | DD agent conditionally approves |
| `trade_entered` | Position opened |
| `trade_skipped` | Approved trade skipped (sizing, risk, circuit breaker) |
| `position_hold` | Position review decided to hold |
| `position_partial_exit` | Partial profit taking |
| `position_exit_target` | Exited at profit target |
| `position_exit_stop` | Exited at stop loss |
| `position_exit_time` | Exited due to time limit |
| `position_exit_invalidated` | Exited — thesis invalidated |
| `position_exit_manual` | Manual exit |
| `circuit_breaker_triggered` | Trading halted by risk limits |
| `circuit_breaker_reset` | Trading re-enabled |
| `phase_transition` | Orchestrator changed phase |
| `research_cycle` | Research cycle completed |
| `portfolio_paused` | Portfolio paused |
| `portfolio_resumed` | Portfolio resumed |

#### 3.3 `portfolio_snapshots` Table (Daily P&L Tracking)

```sql
CREATE TABLE IF NOT EXISTS portfolio_snapshots (
    id TEXT PRIMARY KEY,                   -- UUID
    portfolio_id TEXT NOT NULL,            -- FK → portfolios
    snapshot_date TEXT NOT NULL,            -- Date (YYYY-MM-DD)
    timestamp TEXT NOT NULL,               -- ISO timestamp
    
    -- Values
    portfolio_value TEXT NOT NULL,          -- Total value (cash + positions)
    cash TEXT NOT NULL,
    positions_value TEXT NOT NULL,          -- Market value of open positions
    
    -- Daily P&L
    daily_pnl TEXT NOT NULL DEFAULT '0',
    daily_pnl_pct REAL NOT NULL DEFAULT 0.0,
    
    -- Cumulative
    cumulative_pnl TEXT NOT NULL DEFAULT '0',
    cumulative_pnl_pct REAL NOT NULL DEFAULT 0.0,
    
    -- Positions count
    open_positions INTEGER NOT NULL DEFAULT 0,
    trades_today INTEGER NOT NULL DEFAULT 0,
    
    FOREIGN KEY (portfolio_id) REFERENCES portfolios(id),
    UNIQUE(portfolio_id, snapshot_date)
);
```

#### 3.4 Link Existing V2 Tables to Portfolio

Add `portfolio_id` column to existing tables:

| Table | Change |
|-------|--------|
| `trade_theses` | Add `portfolio_id TEXT` column |
| `dd_reports` | No change needed (linked via thesis) |
| `ai_positions_v2` | Add `portfolio_id TEXT` column |
| `position_reviews` | No change needed (linked via position) |
| `market_events` | No change needed (portfolio-independent) |

#### 3.5 Per-Portfolio State File

Currently state is stored in a single `v2_state.json`. With multiple portfolios, each gets its own state file:

```
logs/ai_investor/state_{portfolio_id}.json
```

This ensures two concurrent `bvr ai auto` sessions (one paper, one live) don't clobber each other's state.

### New Repository: `SQLitePortfolioStore`

**File:** `src/beavr/db/sqlite/portfolio_store.py`

Implements `PortfolioStore`, `DecisionStore`, and `SnapshotStore` Protocols from `src/beavr/db/protocols.py`. See **Section 4** for the full Protocol definitions.

```python
class SQLitePortfolioStore:
    """SQLite implementation of PortfolioStore + DecisionStore + SnapshotStore.
    
    Satisfies the Protocol interfaces via structural typing.
    Can be swapped for DynamoDBPortfolioStore, etc. without changing business logic.
    """
    
    def __init__(self, db: Database) -> None:
        self.db = db
    
    # PortfolioStore methods
    def create_portfolio(
        self,
        name: str, 
        mode: str, 
        initial_capital: Decimal, 
        config_snapshot: dict,
        aggressiveness: str,
        directives: list[str],
    ) -> str: ...
    def get_portfolio(self, portfolio_id: str) -> Optional[PortfolioRecord]: ...
    def get_portfolio_by_name(self, name: str) -> Optional[PortfolioRecord]: ...
    def list_portfolios(self, status: Optional[str] = None, mode: Optional[str] = None) -> list[PortfolioRecord]: ...
    def close_portfolio(self, portfolio_id: str) -> None: ...
    def pause_portfolio(self, portfolio_id: str) -> None: ...
    def resume_portfolio(self, portfolio_id: str) -> None: ...
    def update_portfolio_stats(self, portfolio_id: str, trade_pnl: Decimal, is_win: bool) -> None: ...
    def delete_portfolio(self, portfolio_id: str) -> None: ...
    def delete_all_data(self) -> None: ...
    
    # DecisionStore methods
    def log_decision(self, decision: PortfolioDecision) -> str: ...
    def get_decisions(
        self,
        portfolio_id: str, 
        decision_type: Optional[str] = None, 
        symbol: Optional[str] = None, 
        limit: int = 100,
        offset: int = 0,
    ) -> list[PortfolioDecision]: ...
    def get_full_audit_trail(
        self,
        portfolio_id: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> list[PortfolioDecision]: ...
    
    # SnapshotStore methods
    def take_snapshot(self, snapshot: PortfolioSnapshot) -> str: ...
    def get_snapshots(self, portfolio_id: str, start_date: Optional[date] = None,
                      end_date: Optional[date] = None) -> list[PortfolioSnapshot]: ...
```

### New Pydantic Models

**File:** `src/beavr/models/portfolio_record.py`

```python
class TradingMode(str, Enum):
    PAPER = "paper"
    LIVE = "live"

class Aggressiveness(str, Enum):
    CONSERVATIVE = "conservative"   # Lower risk, tighter stops, higher confidence thresholds
    MODERATE = "moderate"           # Default — balanced risk/reward
    AGGRESSIVE = "aggressive"       # Higher risk tolerance, wider stops, lower confidence thresholds

class PortfolioRecord(BaseModel):
    """Persisted portfolio with configuration and audit trail."""
    id: str
    name: str
    created_at: datetime
    closed_at: Optional[datetime]
    status: PortfolioStatus  # active | paused | closed
    mode: TradingMode        # paper | live — NEVER mix
    initial_capital: Decimal
    allocated_capital: Decimal
    current_cash: Decimal
    config_snapshot: dict
    aggressiveness: Aggressiveness
    directives: list[str]    # User-provided AI personality directives
    total_invested: Decimal
    total_returned: Decimal
    realized_pnl: Decimal
    total_trades: int
    winning_trades: int
    losing_trades: int
    peak_value: Decimal
    max_drawdown_pct: float
    notes: Optional[str]

class DecisionType(str, Enum):
    THESIS_CREATED = "thesis_created"
    THESIS_REJECTED = "thesis_rejected"
    DD_APPROVED = "dd_approved"
    DD_REJECTED = "dd_rejected"
    DD_CONDITIONAL = "dd_conditional"
    TRADE_ENTERED = "trade_entered"
    TRADE_SKIPPED = "trade_skipped"
    POSITION_HOLD = "position_hold"
    POSITION_PARTIAL_EXIT = "position_partial_exit"
    POSITION_EXIT_TARGET = "position_exit_target"
    POSITION_EXIT_STOP = "position_exit_stop"
    POSITION_EXIT_TIME = "position_exit_time"
    POSITION_EXIT_INVALIDATED = "position_exit_invalidated"
    POSITION_EXIT_MANUAL = "position_exit_manual"
    CIRCUIT_BREAKER_TRIGGERED = "circuit_breaker_triggered"
    CIRCUIT_BREAKER_RESET = "circuit_breaker_reset"
    PHASE_TRANSITION = "phase_transition"
    RESEARCH_CYCLE = "research_cycle"
    PORTFOLIO_PAUSED = "portfolio_paused"
    PORTFOLIO_RESUMED = "portfolio_resumed"

class PortfolioDecision(BaseModel):
    """Single auditable decision within a portfolio."""
    id: str
    portfolio_id: str
    timestamp: datetime
    phase: str
    decision_type: DecisionType
    symbol: Optional[str]
    thesis_id: Optional[str]
    dd_report_id: Optional[str]
    position_id: Optional[str]
    event_id: Optional[str]
    action: str
    reasoning: Optional[str]
    confidence: Optional[float]
    amount: Optional[Decimal]
    shares: Optional[Decimal]
    price: Optional[Decimal]
    outcome: Optional[str]
    outcome_details: Optional[dict]

class PortfolioSnapshot(BaseModel):
    """Daily portfolio value snapshot."""
    id: str
    portfolio_id: str
    snapshot_date: date
    timestamp: datetime
    portfolio_value: Decimal
    cash: Decimal
    positions_value: Decimal
    daily_pnl: Decimal
    daily_pnl_pct: float
    cumulative_pnl: Decimal
    cumulative_pnl_pct: float
    open_positions: int
    trades_today: int
```

### Portfolio Setup Wizard (Interactive CLI)

When `bvr ai auto` is run, the CLI presents a portfolio selection flow:

```
$ bvr ai auto

🦫 Beavr AI — Portfolio Setup
─────────────────────────────

Existing portfolios:
  [1] Paper - Aggressive Tech (paper, active, +$1,240.50)
  [2] Live - Conservative (live, paused, -$89.20)
  [N] Create new portfolio

Select portfolio [1/2/N]: N

── New Portfolio Setup ──

Portfolio name: Paper - Earnings Plays
Trading mode:
  [1] Paper (simulated trades)
  [2] Live (real money)
Select [1/2]: 1

Aggressiveness:
  [1] Conservative — tighter stops, higher confidence bar, fewer trades
  [2] Moderate — balanced risk/reward (default)
  [3] Aggressive — wider stops, lower confidence bar, more trades
Select [1/2/3]: 3

Custom directives (shape how the AI trades, one per line, empty line to finish):
> Focus on earnings plays and catalyst-driven trades
> Prefer large-cap tech and semiconductor stocks
> Avoid biotech and penny stocks
>

Capital allocation: $5,000.00
Capital % to use [80]: 90

── Summary ──
  Name:           Paper - Earnings Plays
  Mode:           paper
  Aggressiveness: aggressive
  Capital:        $5,000.00 (90% = $4,500.00 available)
  Directives:     3 custom rules

Confirm and start? [Y/n]: Y

🚀 Starting autonomous trading for "Paper - Earnings Plays"...
```

#### Non-Interactive Mode

For scripted/cron usage, skip the wizard:

```bash
# Resume existing portfolio by name
bvr ai auto --portfolio "Paper - Aggressive Tech"

# Create new with flags (no prompts)
bvr ai auto --portfolio "New Paper" --mode paper --aggressiveness aggressive \
  --directive "Focus on tech" --directive "Avoid biotech" \
  --capital 5000 --capital-pct 90
```

### How Aggressiveness Affects Behavior

The `aggressiveness` setting modulates V2Config parameters:

| Parameter | Conservative | Moderate | Aggressive |
|-----------|-------------|----------|------------|
| `min_confidence` (thesis) | 0.75 | 0.60 | 0.45 |
| `dd_min_approval_confidence` | 0.80 | 0.65 | 0.50 |
| `max_daily_loss` | 2% | 3% | 5% |
| `max_drawdown` | 7% | 10% | 15% |
| `daily_trade_limit` | 3 | 5 | 8 |
| `position_size_pct` | 8% | 10% | 15% |
| `day_trade_target` | 3% | 5% | 8% |
| `day_trade_stop` | 2% | 3% | 4% |
| `swing_target` | 10% | 15% | 25% |
| `swing_stop` | 5% | 7% | 10% |

These are applied as overrides on top of the base `ai_investor_v2.toml` config.

### How Directives Affect Behavior

Directives are injected into LLM prompts at key decision points:

1. **Thesis generation** — directives appended to the thesis generator system prompt
2. **DD analysis** — directives included in DD agent context
3. **Trade execution** — directives checked before entry (e.g., sector filters)
4. **Morning scan** — directives shape which movers are considered

Example system prompt injection:
```
You are analyzing trading opportunities. The user has provided these directives:
- Focus on earnings plays and catalyst-driven trades
- Prefer large-cap tech and semiconductor stocks  
- Avoid biotech and penny stocks

Factor these preferences into your analysis.
```

### Orchestrator Integration

The `V2AutonomousOrchestrator` needs these changes:

| Area | Change |
|------|--------|
| `__init__` | Accept `PortfolioRepository` + `portfolio_id` — always bound to a specific portfolio |
| `run()` | Load portfolio config, directives, and aggressiveness-adjusted parameters on startup |
| State file | Use `state_{portfolio_id}.json` instead of shared `v2_state.json` |
| All LLM calls | Inject portfolio directives into agent prompts |
| Research pipeline | Log `thesis_created` / `thesis_rejected` decisions |
| DD pipeline | Log `dd_approved` / `dd_rejected` / `dd_conditional` decisions |
| Trade execution | Log `trade_entered` / `trade_skipped` decisions, update portfolio stats |
| Position monitoring | Log `position_hold` / `position_*_exit` decisions |
| Circuit breaker | Log `circuit_breaker_triggered` / `circuit_breaker_reset` |
| Phase transitions | Log `phase_transition` decisions |
| End of day | Take daily `portfolio_snapshot` |
| Shutdown | Final snapshot, save state |

**Decision logging pattern** (added throughout orchestrator):

```python
self.portfolio_repo.log_decision(
    portfolio_id=self.portfolio_id,
    decision=PortfolioDecision(
        id=str(uuid4()),
        portfolio_id=self.portfolio_id,
        timestamp=datetime.now(timezone.utc),
        phase=self.state.current_phase.value,
        decision_type=DecisionType.TRADE_ENTERED,
        symbol="AAPL",
        thesis_id=thesis.id,
        dd_report_id=dd_report.id,
        action="buy",
        reasoning="DD approved with 0.82 confidence, power hour entry confirmed",
        confidence=Decimal("0.82"),
        amount=Decimal("500.00"),
        shares=Decimal("2.5"),
        price=Decimal("198.50"),
    )
)
```

---

## 4. Requirement 3: Repository Abstraction Layer

### Problem

The current DB layer has **good dependency injection** — every repository accepts `db: Database` via its constructor. However, there are two gaps that would force a big re-architecture if we ever move to a cloud datastore:

1. **No interface contracts** — repositories are concrete classes with no Protocol or ABC. Consumers import `ThesisRepository` directly, coupling to the SQLite implementation.
2. **Raw SQL in repository methods** — repos use `sqlite3.Connection` and raw SQL strings. Swapping to DynamoDB/CosmosDB would require rewriting every method.

The broker layer already solves this problem well: `BrokerProvider`, `MarketDataProvider`, etc. are `@runtime_checkable Protocol` classes. Alpaca and Webull implement them. We follow the same pattern for repositories.

### Design: Protocol-Based Repository Interfaces

**File:** `src/beavr/db/protocols.py`

Define one Protocol per repository interface. All business logic depends on the Protocol, never on the concrete implementation. SQLite implementations live alongside as the default. Future DynamoDB/CosmosDB implementations can be added without touching any business logic.

```python
from typing import Protocol, Optional, runtime_checkable
from decimal import Decimal
from datetime import date, datetime


@runtime_checkable
class PortfolioStore(Protocol):
    """Interface for portfolio persistence.
    
    Implementations: SQLitePortfolioStore, (future) DynamoDBPortfolioStore, etc.
    """
    
    # Portfolio lifecycle
    def create_portfolio(
        self,
        name: str,
        mode: str,
        initial_capital: Decimal,
        config_snapshot: dict,
        aggressiveness: str,
        directives: list[str],
    ) -> str: ...
    
    def get_portfolio(self, portfolio_id: str) -> Optional["PortfolioRecord"]: ...
    def get_portfolio_by_name(self, name: str) -> Optional["PortfolioRecord"]: ...
    def list_portfolios(
        self, status: Optional[str] = None, mode: Optional[str] = None
    ) -> list["PortfolioRecord"]: ...
    def close_portfolio(self, portfolio_id: str) -> None: ...
    def pause_portfolio(self, portfolio_id: str) -> None: ...
    def resume_portfolio(self, portfolio_id: str) -> None: ...
    def update_portfolio_stats(self, portfolio_id: str, trade_pnl: Decimal, is_win: bool) -> None: ...
    
    # Cleanup
    def delete_portfolio(self, portfolio_id: str) -> None: ...
    def delete_all_data(self) -> None: ...


@runtime_checkable
class DecisionStore(Protocol):
    """Interface for audit trail / decision logging."""
    
    def log_decision(self, decision: "PortfolioDecision") -> str: ...
    def get_decisions(
        self,
        portfolio_id: str,
        decision_type: Optional[str] = None,
        symbol: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list["PortfolioDecision"]: ...
    def get_full_audit_trail(
        self,
        portfolio_id: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> list["PortfolioDecision"]: ...


@runtime_checkable
class SnapshotStore(Protocol):
    """Interface for portfolio snapshots (equity curve data)."""
    
    def take_snapshot(self, snapshot: "PortfolioSnapshot") -> str: ...
    def get_snapshots(
        self,
        portfolio_id: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> list["PortfolioSnapshot"]: ...


@runtime_checkable
class ThesisStore(Protocol):
    """Interface for trade thesis persistence."""
    
    def save_thesis(self, thesis: "TradeThesis") -> str: ...
    def get_thesis(self, thesis_id: str) -> Optional["TradeThesis"]: ...
    def get_active_theses(self, portfolio_id: str) -> list["TradeThesis"]: ...
    def get_pending_dd(self, portfolio_id: str) -> list["TradeThesis"]: ...
    def update_thesis_status(self, thesis_id: str, status: str) -> None: ...
    def approve_dd(self, thesis_id: str, dd_report_id: str) -> None: ...


@runtime_checkable
class DDReportStore(Protocol):
    """Interface for due diligence report persistence."""
    
    def save_report(self, report: "DueDiligenceReport") -> str: ...
    def get_report(self, report_id: str) -> Optional["DueDiligenceReport"]: ...
    def get_reports_for_thesis(self, thesis_id: str) -> list["DueDiligenceReport"]: ...


@runtime_checkable
class EventStore(Protocol):
    """Interface for market event persistence."""
    
    def save_event(self, event: "MarketEvent") -> str: ...
    def get_unprocessed_events(self, limit: int = 50) -> list["MarketEvent"]: ...
    def mark_processed(self, event_id: str, thesis_id: Optional[str] = None) -> None: ...
    def get_upcoming_earnings(self, days_ahead: int = 7) -> list["MarketEvent"]: ...


@runtime_checkable
class PositionStore(Protocol):
    """Interface for AI position persistence."""
    
    def open_position(self, position: "PositionRecord") -> str: ...
    def close_position(self, position_id: str, exit_price: Decimal, exit_type: str) -> None: ...
    def get_open_positions(self, portfolio_id: str) -> list["PositionRecord"]: ...
    def get_position(self, position_id: str) -> Optional["PositionRecord"]: ...


@runtime_checkable 
class BarCacheStore(Protocol):
    """Interface for OHLCV bar caching."""
    
    def get_bars(
        self, symbol: str, start: date, end: date, timeframe: str
    ) -> Optional["pd.DataFrame"]: ...
    def save_bars(
        self, symbol: str, bars: "pd.DataFrame", timeframe: str
    ) -> None: ...
```

### SQLite Implementations

Existing repository classes become the **SQLite implementations** of these Protocols:

| Protocol | SQLite Implementation | File |
|----------|----------------------|------|
| `PortfolioStore` | `SQLitePortfolioStore` | `src/beavr/db/sqlite/portfolio_store.py` |
| `DecisionStore` | `SQLiteDecisionStore` | `src/beavr/db/sqlite/decision_store.py` |
| `SnapshotStore` | `SQLiteSnapshotStore` | `src/beavr/db/sqlite/snapshot_store.py` |
| `ThesisStore` | `SQLiteThesisStore` | `src/beavr/db/sqlite/thesis_store.py` (refactored from `thesis_repo.py`) |
| `DDReportStore` | `SQLiteDDReportStore` | `src/beavr/db/sqlite/dd_report_store.py` (refactored from `dd_reports_repo.py`) |
| `EventStore` | `SQLiteEventStore` | `src/beavr/db/sqlite/event_store.py` (refactored from `events_repo.py`) |
| `PositionStore` | `SQLitePositionStore` | `src/beavr/db/sqlite/position_store.py` (refactored from `ai_positions.py`) |
| `BarCacheStore` | `SQLiteBarCacheStore` | `src/beavr/db/sqlite/bar_cache_store.py` (refactored from `cache.py`) |

#### Directory Structure

```
src/beavr/db/
├── protocols.py              # Protocol interfaces (the contracts)
├── sqlite/                   # SQLite implementations
│   ├── __init__.py
│   ├── connection.py          # SQLite Database class (moved from db/connection.py)
│   ├── schema.py              # V1 schema (moved)
│   ├── schema_v2.py           # V2 schema (moved)
│   ├── portfolio_store.py     # NEW — PortfolioStore + DecisionStore + SnapshotStore
│   ├── thesis_store.py        # Refactored from thesis_repo.py
│   ├── dd_report_store.py     # Refactored from dd_reports_repo.py
│   ├── event_store.py         # Refactored from events_repo.py
│   ├── position_store.py      # Refactored from ai_positions.py
│   └── bar_cache_store.py     # Refactored from cache.py
├── __init__.py                # Re-exports Protocols + SQLite defaults
└── (legacy files kept temporarily for backward compat)
```

### How Consumers Use Protocols

Business logic (orchestrator, agents, CLI) depends on the Protocol, not the implementation:

```python
# In V2AutonomousOrchestrator — depends on Protocols only
class V2AutonomousOrchestrator:
    def __init__(
        self,
        portfolio_store: PortfolioStore,
        decision_store: DecisionStore,
        snapshot_store: SnapshotStore,
        thesis_store: ThesisStore,
        dd_report_store: DDReportStore,
        event_store: EventStore,
        position_store: PositionStore,
        # ... agents, config, etc.
    ) -> None: ...


# In CLI — composition root wires SQLite implementations
def auto() -> None:
    db = Database()  # SQLite
    orchestrator = V2AutonomousOrchestrator(
        portfolio_store=SQLitePortfolioStore(db),
        decision_store=SQLiteDecisionStore(db),
        snapshot_store=SQLiteSnapshotStore(db),
        thesis_store=SQLiteThesisStore(db),
        dd_report_store=SQLiteDDReportStore(db),
        event_store=SQLiteEventStore(db),
        position_store=SQLitePositionStore(db),
        # ...
    )
```

### Factory for Store Creation

To simplify wiring, provide a factory that creates all stores for a given backend:

**File:** `src/beavr/db/factory.py`

```python
from dataclasses import dataclass

@dataclass
class StoreBundle:
    """All stores wired to the same backend."""
    portfolio: PortfolioStore
    decisions: DecisionStore
    snapshots: SnapshotStore
    theses: ThesisStore
    dd_reports: DDReportStore
    events: EventStore
    positions: PositionStore
    bar_cache: BarCacheStore


def create_sqlite_stores(db_path: Optional[str] = None) -> StoreBundle:
    """Create all stores backed by SQLite."""
    from beavr.db.sqlite.connection import Database
    db = Database(db_path)
    return StoreBundle(
        portfolio=SQLitePortfolioStore(db),
        decisions=SQLiteDecisionStore(db),
        snapshots=SQLiteSnapshotStore(db),
        theses=SQLiteThesisStore(db),
        dd_reports=SQLiteDDReportStore(db),
        events=SQLiteEventStore(db),
        positions=SQLitePositionStore(db),
        bar_cache=SQLiteBarCacheStore(db),
    )


# Future:
# def create_dynamodb_stores(table_prefix: str, region: str) -> StoreBundle: ...
# def create_cosmosdb_stores(connection_string: str) -> StoreBundle: ...
```

CLI becomes a one-liner:

```python
stores = create_sqlite_stores()
orchestrator = V2AutonomousOrchestrator(
    portfolio_store=stores.portfolio,
    decision_store=stores.decisions,
    # ...
)
```

### Migration Strategy

This is a **refactor**, not a rewrite. Steps:

1. Create `src/beavr/db/protocols.py` with all Protocol interfaces
2. Create `src/beavr/db/sqlite/` directory
3. Move existing repos into `sqlite/` and rename classes to `SQLite*Store`
4. Make each implement its Protocol (structural typing — just match method signatures)
5. Update imports in orchestrator/CLI to use Protocol types in signatures, SQLite types at composition root
6. Keep old files as thin re-exports during transition (backward compat)
7. Add `factory.py` with `create_sqlite_stores()`

**What we are NOT doing:** Implementing DynamoDB/CosmosDB/PostgreSQL stores. We're only laying the interface boundary so future implementations slot in without touching business logic.

### Why This Works for Cloud Datastores

| Concern | How Protocols Handle It |
|---------|-----------------------|
| Different query patterns | Each Protocol method is a logical operation ("get open positions"), not a SQL query. DynamoDB implementation can use GSIs, scans, etc. |
| Different connection models | Connection management is internal to each implementation. SQLite uses `sqlite3.Connection`; DynamoDB would use `boto3.resource('dynamodb')`. |
| Different consistency models | Protocols don't expose transactions. Each method call is self-contained. Implementations handle consistency internally. |
| Schema-less stores | Pydantic models define the data contract at the Protocol boundary. Implementations serialize however they want (JSON for Dynamo, columns for SQL). |
| Testing | Mock any Protocol in tests without touching SQLite at all. |

---

## 5. Requirement 4: Clean Slate — Reset All Data

### New CLI Command: `bvr ai reset`

```
bvr ai reset [--confirm] [--keep-events] [--portfolio NAME]
```

| Flag | Behavior |
|------|----------|
| (no flags) | Interactive prompt: choose portfolio to delete or "ALL" |
| `--confirm` | Skip interactive prompt |
| `--keep-events` | Preserve `market_events` table (re-usable research data) |
| `--portfolio NAME` | Only delete a specific portfolio and its linked data |

### What Gets Deleted

| Scope | Tables Cleared | Files Deleted |
|-------|---------------|---------------|
| Full reset | `portfolios`, `portfolio_decisions`, `portfolio_snapshots`, `trade_theses`, `dd_reports`, `ai_positions_v2`, `position_reviews`, `watchlist`, `market_events` (unless `--keep-events`) | `logs/ai_investor/state_*.json`, `logs/dd_reports/**` |
| Portfolio-only | Filter by `portfolio_id` on `portfolios`, `portfolio_decisions`, `portfolio_snapshots`, `trade_theses`, `ai_positions_v2`, `position_reviews` (via position) | `logs/ai_investor/state_{portfolio_id}.json` |

### Interactive Flow

```
$ bvr ai reset

⚠️  Beavr AI — Data Reset
─────────────────────────

Portfolios found:
  [1] Paper - Aggressive Tech (3 trades, +$1,240.50)
  [2] Live - Conservative (1 trade, -$89.20)
  [A] Delete ALL data

Select [1/2/A]: A

This will permanently delete:
  • 2 portfolios
  • 47 decisions
  • 4 trades  
  • 12 theses
  • 8 DD reports
  • All state files

Type 'DELETE' to confirm: DELETE

✓ All data deleted. Starting fresh.
```

### Implementation

```python
@ai_app.command("reset")
def reset(
    confirm: bool = typer.Option(False, "--confirm", "-y", help="Skip confirmation prompt"),
    keep_events: bool = typer.Option(False, "--keep-events", help="Preserve market events data"),
    portfolio: Optional[str] = typer.Option(None, "--portfolio", "-p", help="Reset specific portfolio by name"),
) -> None:
    """Clear trading data and start fresh."""
```

The `PortfolioRepository.delete_all_data()` method handles the SQL transaction. DD report files in `logs/dd_reports/` and per-portfolio state files are also cleaned up.

---

## 6. Requirement 5: Earnings Calendar Integration

### Current State

- `EventType.EARNINGS_UPCOMING` and `EventType.EARNINGS_ANNOUNCED` exist in the model
- `MarketEvent` has fields for EPS estimates/actuals and revenue estimates/actuals
- `EventsRepository.get_upcoming_earnings()` exists but has a date arithmetic bug
- **No data source** actually populates these — the News Monitor agent classifies news articles but doesn't proactively fetch an earnings calendar
- Neither Alpaca nor Webull SDKs provide a dedicated earnings calendar API

### Proposed Solution: Multi-Source Earnings Fetcher

#### 5.1 Data Sources (ranked by reliability)

| Source | API | Cost | Data Quality | Rate Limits |
|--------|-----|------|-------------|-------------|
| **Alpha Vantage** | `EARNINGS_CALENDAR` endpoint | Free (25 req/day) or $50/mo | Comprehensive — next 3 months, EPS estimates | 25/day free, 75/min paid |
| **Yahoo Finance** | `yfinance` Python package | Free (unofficial) | Good — earnings dates, EPS estimates/actuals | Unofficial, may break |
| **Finnhub** | `/calendar/earnings` | Free (60 req/min) | Good — earnings for date range, EPS estimates | 60/min |
| **SEC EDGAR** | XBRL filings | Free (official) | Authoritative for actuals, no future dates | 10 req/sec |

**Recommendation:** Use **Alpha Vantage** as primary (reliable, structured, free tier sufficient for daily fetch) with **yfinance** as fallback (no API key needed). Both are lightweight dependencies.

**Alpha Vantage API access:** Alpha Vantage provides a free REST API — no official Python SDK needed. We call the endpoint directly via `requests` (already a transitive dependency). Sign up at https://www.alphavantage.co/support/#api-key for a free API key. The key is configured via `ALPHA_VANTAGE_API_KEY` env var or in the TOML config.

```
GET https://www.alphavantage.co/query?function=EARNINGS_CALENDAR&horizon=3month&apikey=DEMO

Response (CSV):
symbol,name,reportDate,fiscalDateEnding,estimate,currency
MSFT,Microsoft Corp,2026-01-28,2025-12-31,3.13,USD
AAPL,Apple Inc,2026-01-30,2025-12-31,2.36,USD
...
```

25 requests/day is sufficient — we make 1 bulk calendar fetch per day during the overnight phase. Symbol-specific lookups for watchlist items use ~5-10 additional calls. Well within limits.

#### 5.2 New Component: `EarningsCalendarFetcher`

**File:** `src/beavr/data/earnings.py`

```python
class EarningsCalendarFetcher:
    """Fetches upcoming earnings dates from external APIs."""
    
    def __init__(self, events_repo: EventsRepository, api_key: Optional[str] = None) -> None:
        self.events_repo = events_repo
        self.api_key = api_key  # Alpha Vantage key (optional)
    
    def fetch_upcoming_earnings(self, horizon_days: int = 14) -> list[MarketEvent]:
        """Fetch earnings calendar and store as MarketEvent records.
        
        Strategy:
        1. Try Alpha Vantage EARNINGS_CALENDAR (if API key configured)
        2. Fall back to yfinance
        3. Deduplicate against existing events in DB
        4. Store new events as EARNINGS_UPCOMING type
        """
        ...
    
    def fetch_earnings_for_symbols(self, symbols: list[str]) -> list[MarketEvent]:
        """Fetch next earnings date for specific symbols (e.g., watchlist)."""
        ...
    
    def enrich_with_estimates(self, event: MarketEvent) -> MarketEvent:
        """Add consensus EPS/revenue estimates to an earnings event."""
        ...
```

#### 5.3 Alpha Vantage Integration

```python
# Free endpoint: https://www.alphavantage.co/query?function=EARNINGS_CALENDAR&horizon=3month&apikey=KEY
# Returns CSV with columns: symbol, name, reportDate, fiscalDateEnding, estimate, currency

def _fetch_alpha_vantage(self, horizon: str = "3month") -> list[dict]:
    """Fetch earnings calendar from Alpha Vantage."""
    url = "https://www.alphavantage.co/query"
    params = {
        "function": "EARNINGS_CALENDAR",
        "horizon": horizon,
        "apikey": self.api_key,
    }
    response = requests.get(url, params=params)
    reader = csv.DictReader(io.StringIO(response.text))
    return [row for row in reader]
```

#### 5.4 yfinance Fallback

```python
# pip install yfinance

def _fetch_yfinance(self, symbols: list[str]) -> list[dict]:
    """Fetch next earnings date per symbol via yfinance."""
    import yfinance as yf
    results = []
    for symbol in symbols:
        ticker = yf.Ticker(symbol)
        cal = ticker.calendar  # Returns dict with 'Earnings Date', 'EPS Estimate', etc.
        if cal:
            results.append({
                "symbol": symbol,
                "earnings_date": cal.get("Earnings Date"),
                "eps_estimate": cal.get("EPS Estimate"),
                "revenue_estimate": cal.get("Revenue Estimate"),
            })
    return results
```

#### 5.5 Earnings Agent: `EarningsPlayAgent`

**File:** `src/beavr/agents/earnings_agent.py`

A new agent that specifically handles earnings-driven trades:

```python
class EarningsPlayAgent(BaseAgent):
    """Generates earnings play theses from upcoming earnings events.
    
    Earnings plays are high-conviction, short-duration trades around 
    earnings announcements. Strategies include:
    - Pre-earnings drift (buy 3-5 days before, sell before announcement)
    - Post-earnings momentum (trade the gap after results)
    - IV crush plays (if options supported in future)
    """
    
    agent_name: str = "EarningsPlay"
    
    def analyze_earnings_opportunity(
        self, event: MarketEvent, context: AgentContext
    ) -> Optional[TradeThesis]:
        """Evaluate if an upcoming earnings event is tradeable.
        
        Considers:
        - Historical earnings surprise pattern (last 4 quarters)
        - Pre-earnings price drift direction
        - Analyst consensus vs whisper numbers
        - Sector momentum going into earnings
        - IV expansion (implied volatility, for future options support)
        - Whether stock typically gaps or drifts post-earnings
        """
        ...
    
    def classify_earnings_play(
        self, event: MarketEvent, bars: pd.DataFrame
    ) -> EarningsPlayType:
        """Determine the best earnings play strategy.
        
        Returns: PRE_EARNINGS_DRIFT | POST_EARNINGS_MOMENTUM | SKIP
        """
        ...
```

**`EarningsPlayType` Enum:**

| Type | Description | Entry | Exit |
|------|-------------|-------|------|
| `PRE_EARNINGS_DRIFT` | Buy 3–5 days before, sell day before | T-5 to T-3 | T-1 (before close) |
| `POST_EARNINGS_MOMENTUM` | Trade the gap after results | T+0 (after open) | T+1 to T+3 |
| `SKIP` | Too risky or no edge | — | — |

#### 5.6 Orchestrator Integration

Earnings events go through the **full thesis → DD pipeline** like every other trade. No shortcuts.

Add earnings scanning to the **OVERNIGHT_DD** phase:

```python
# In V2AutonomousOrchestrator

def _scan_earnings_calendar(self) -> None:
    """Daily earnings calendar scan — runs once during OVERNIGHT_DD phase."""
    # 1. Fetch next 14 days of earnings
    events = self.earnings_fetcher.fetch_upcoming_earnings(horizon_days=14)
    
    # 2. Filter to symbols matching quality criteria AND portfolio directives
    qualified = [e for e in events 
                 if self._passes_quality_filter(e.symbol)
                 and self._passes_directive_filter(e.symbol)]
    
    # 3. For each qualified earnings event in next 5 days:
    #    - Run EarningsPlayAgent.analyze_earnings_opportunity()
    #    - If play identified → generate thesis (logs thesis_created decision)
    #    - Queue thesis for DD (standard DD pipeline, logs dd_approved/rejected)
    #    - If DD approved → queue for trade execution
    
    # 4. All decisions logged to portfolio audit trail automatically
```

**Important:** Earnings plays are NOT exempt from DD. The DD agent evaluates them like any other thesis. The `EarningsPlayAgent` produces a thesis; the `DueDiligenceAgent` approves or rejects it. This ensures every portfolio action is either thesis-driven or human-driven.

#### 5.7 Configuration

Add to `config/ai_investor_v2.toml`:

```toml
[earnings]
enabled = true
scan_horizon_days = 14          # How far ahead to look
play_entry_days_before = 5      # Earliest entry for pre-earnings plays
min_market_cap = 2_000_000_000  # $2B minimum for earnings plays (higher bar)
min_avg_volume = 1_000_000      # Higher volume requirement for earnings
max_plays_per_week = 3          # Limit earnings exposure
alpha_vantage_api_key = ""      # Set via ALPHA_VANTAGE_API_KEY env var

[earnings.pre_earnings_drift]
enabled = true
target_pct = 5.0
stop_pct = 3.0
min_historical_beat_rate = 0.6  # Stock must beat estimates 60%+ of last 4 quarters

[earnings.post_earnings_momentum]  
enabled = true
target_pct = 8.0
stop_pct = 4.0
min_gap_pct = 3.0              # Minimum gap to enter post-earnings
```

#### 5.8 New Dependencies

| Package | Purpose | Install Extra |
|---------|---------|---------------|
| `alpha-vantage` or raw `requests` | Earnings calendar API | `[earnings]` |
| `yfinance` | Fallback earnings data | `[earnings]` |

Add to `pyproject.toml`:

```toml
[project.optional-dependencies]
earnings = ["yfinance>=0.2.0", "requests>=2.28"]
```

Note: `requests` is likely already a transitive dependency. `yfinance` is the main new addition.

---

## 7. Implementation Plan

### Phase 1: Auto Consolidation (Estimated: 1–2 hours)

| Step | Task | Files |
|------|------|-------|
| 1.1 | Delete `auto()` function and V1-only helpers | `src/beavr/cli/ai.py` |
| 1.2 | Rename `auto_v2()` → `auto()`, update decorator | `src/beavr/cli/ai.py` |
| 1.3 | Update/remove tests referencing old `auto` | `tests/` |
| 1.4 | Verify `bvr ai auto --help` works | Manual |

### Phase 2: Repository Abstraction Layer (Estimated: 4–6 hours)

| Step | Task | Files |
|------|------|-------|
| 2.1 | Create Protocol interfaces | `src/beavr/db/protocols.py` |
| 2.2 | Create `src/beavr/db/sqlite/` directory structure | `src/beavr/db/sqlite/` |
| 2.3 | Move `Database` + schemas into `sqlite/` | `src/beavr/db/sqlite/connection.py`, `schema.py`, `schema_v2.py` |
| 2.4 | Refactor `ThesisRepository` → `SQLiteThesisStore` implementing `ThesisStore` | `src/beavr/db/sqlite/thesis_store.py` |
| 2.5 | Refactor `DDReportsRepository` → `SQLiteDDReportStore` implementing `DDReportStore` | `src/beavr/db/sqlite/dd_report_store.py` |
| 2.6 | Refactor `EventsRepository` → `SQLiteEventStore` implementing `EventStore` | `src/beavr/db/sqlite/event_store.py` |
| 2.7 | Refactor `AIPositionsRepository` → `SQLitePositionStore` implementing `PositionStore` | `src/beavr/db/sqlite/position_store.py` |
| 2.8 | Refactor `BarCache` → `SQLiteBarCacheStore` implementing `BarCacheStore` | `src/beavr/db/sqlite/bar_cache_store.py` |
| 2.9 | Create `StoreBundle` + `create_sqlite_stores()` factory | `src/beavr/db/factory.py` |
| 2.10 | Add backward-compat re-exports in old file locations | `src/beavr/db/__init__.py` |
| 2.11 | Update all imports in CLI, orchestrator, agents | Multiple |
| 2.12 | Write tests verifying Protocol conformance | `tests/unit/test_store_protocols.py` |

### Phase 3: Portfolio Models & Schema (Estimated: 3–4 hours)

| Step | Task | Files |
|------|------|-------|
| 3.1 | Create `TradingMode`, `Aggressiveness`, `PortfolioRecord`, `PortfolioDecision`, `PortfolioSnapshot` models | `src/beavr/models/portfolio_record.py` |
| 3.2 | Add new tables to V2 schema (bump version to 4) | `src/beavr/db/sqlite/schema_v2.py` |
| 3.3 | Add `portfolio_id` to existing V2 tables | `src/beavr/db/sqlite/schema_v2.py` |
| 3.4 | Create `SQLitePortfolioStore`, `SQLiteDecisionStore`, `SQLiteSnapshotStore` | `src/beavr/db/sqlite/portfolio_store.py` |
| 3.5 | Write unit tests for stores | `tests/unit/test_portfolio_store.py` |

### Phase 4: Portfolio Setup Wizard & CLI (Estimated: 3–4 hours)

| Step | Task | Files |
|------|------|-------|
| 4.1 | Build interactive portfolio selection flow | `src/beavr/cli/ai.py` |
| 4.2 | Build new portfolio creation wizard | `src/beavr/cli/ai.py` |
| 4.3 | Add `--portfolio`, `--mode`, `--aggressiveness`, `--directive` flags | `src/beavr/cli/ai.py` |
| 4.4 | Implement aggressiveness → config override mapping | `src/beavr/orchestrator/v2_engine.py` |
| 4.5 | Implement directive injection into agent prompts | `src/beavr/agents/` (multiple) |
| 4.6 | Wire per-portfolio state files (`state_{id}.json`) | `src/beavr/orchestrator/v2_engine.py` |
| 4.7 | Update `auto` command to use `StoreBundle` factory | `src/beavr/cli/ai.py` |

### Phase 5: Audit Trail & Decision Logging (Estimated: 4–6 hours)

| Step | Task | Files |
|------|------|-------|
| 5.1 | Wire stores into `V2AutonomousOrchestrator.__init__` (Protocol types) | `src/beavr/orchestrator/v2_engine.py` |
| 5.2 | Add decision logging at every decision point in orchestrator | `src/beavr/orchestrator/v2_engine.py` |
| 5.3 | Add daily snapshot capture (end of `MARKET_HOURS` phase) | `src/beavr/orchestrator/v2_engine.py` |
| 5.4 | Update portfolio stats on each trade | `src/beavr/orchestrator/v2_engine.py` |
| 5.5 | Rewrite `bvr ai history` to show full audit trail from `DecisionStore` | `src/beavr/cli/ai.py` |
| 5.6 | Write unit tests for decision logging | `tests/unit/test_audit_trail.py` |

### Phase 6: Reset Command (Estimated: 1–2 hours)

| Step | Task | Files |
|------|------|-------|
| 6.1 | Add `delete_portfolio()` and `delete_all_data()` to SQLite stores | `src/beavr/db/sqlite/portfolio_store.py` |
| 6.2 | Implement `bvr ai reset` command with interactive flow | `src/beavr/cli/ai.py` |
| 6.3 | Add DD report file + state file cleanup | `src/beavr/cli/ai.py` |
| 6.4 | Write tests | `tests/unit/test_reset.py` |

### Phase 7: Earnings Integration (Estimated: 4–6 hours)

| Step | Task | Files |
|------|------|-------|
| 7.1 | Create `EarningsCalendarFetcher` (Alpha Vantage + yfinance fallback) | `src/beavr/data/earnings.py` |
| 7.2 | Fix `get_upcoming_earnings()` date bug | `src/beavr/db/sqlite/event_store.py` |
| 7.3 | Create `EarningsPlayAgent` | `src/beavr/agents/earnings_agent.py` |
| 7.4 | Add earnings scan to orchestrator overnight phase | `src/beavr/orchestrator/v2_engine.py` |
| 7.5 | Add `[earnings]` config section | `config/ai_investor_v2.toml` |
| 7.6 | Add `bvr ai earnings` CLI command (view upcoming) | `src/beavr/cli/ai.py` |
| 7.7 | Add dependencies | `pyproject.toml` |
| 7.8 | Write tests | `tests/unit/test_earnings.py` |

### Phase 8: Integration & Validation (Estimated: 2–3 hours)

| Step | Task |
|------|------|
| 8.1 | Run full test suite: `pytest` |
| 8.2 | Lint check: `ruff check src/` |
| 8.3 | Verify all SQLite stores satisfy Protocol contracts (`isinstance` checks) |
| 8.4 | Manual test: `bvr ai auto` (interactive wizard, create new portfolio) |
| 8.5 | Manual test: `bvr ai auto --portfolio "Test"` (resume existing) |
| 8.6 | Manual test: `bvr ai history` (verify full audit trail) |
| 8.7 | Manual test: `bvr ai reset` (interactive portfolio selection) |
| 8.8 | Manual test: `bvr ai earnings` |
| 8.9 | Verify two concurrent sessions (paper + live) don't conflict |

**Total estimated effort: 22–33 hours**

---

## 8. New CLI Commands Summary (Post-Implementation)

| Command | Description |
|---------|-------------|
| `bvr ai auto` | Autonomous trading with portfolio selection wizard |
| `bvr ai auto --portfolio NAME` | Resume or create named portfolio (non-interactive) |
| `bvr ai history` | Full audit trail — all decisions, theses, DDs, trades, exits across all portfolios |
| `bvr ai history --portfolio NAME` | Audit trail filtered to specific portfolio |
| `bvr ai reset` | Interactive data reset — choose portfolio or wipe all |
| `bvr ai earnings` | View upcoming earnings calendar |

**Removed:**
| Command | Reason |
|---------|--------|
| `bvr ai auto` (old V1) | Replaced by V2 |
| `bvr ai auto-v2` | Renamed to `bvr ai auto` |

---

## 9. Database Schema Version Migration

Current: **V2 Schema Version 3**  
Target: **V2 Schema Version 4**

Migration strategy: Same as current — `CREATE TABLE IF NOT EXISTS` with `ALTER TABLE ADD COLUMN` for existing tables. The `init_v2_schema()` function in `schema_v2.py` handles idempotent table creation. Add migration logic for the `portfolio_id` column additions.

---

## 10. Resolved Questions

| # | Question | Decision |
|---|----------|----------|
| 1 | Should daily snapshots run at market close only, or also at configurable intervals? | **TBD** — Snapshots capture a point-in-time picture of portfolio value (cash + positions market value), daily P&L, cumulative P&L, and open position count. Used for charting equity curves and tracking drawdowns over time. Frequency should match how granular you want the equity curve. Market-close-only gives daily resolution; intraday snapshots give more detail but more rows. |
| 2 | Should `bvr ai history` be updated to show portfolio-level view, or add a new command? | **`bvr ai history` is the full audit trail** — shows ALL actions (thesis creation, DD decisions, trades, exits, circuit breakers, phase transitions). Filterable by `--portfolio NAME`. |
| 3 | Alpha Vantage free tier = 25 requests/day. Is that sufficient? | **Yes** — 1 bulk calendar fetch per day + ~5-10 symbol lookups. Alpha Vantage is a free REST API (no SDK needed), called directly via `requests`. API key from https://www.alphavantage.co/support/#api-key |
| 4 | Should earnings plays bypass the normal DD pipeline? | **No** — all portfolio actions must be thesis-driven or human-driven. Earnings events generate a thesis via `EarningsPlayAgent`, then go through standard DD approval. No exceptions. |
| 5 | Should we track paper vs live trades separately? | **Absolutely — NEVER mix.** Paper and live are separate `TradingMode` values on the portfolio. Separate state files, separate audit trails. |

## 11. Remaining Open Questions

| # | Question | Impact |
|---|----------|--------|
| 1 | Snapshot frequency — market close only vs configurable intraday intervals? | See Q1 above for context |
| 2 | Should there be a max concurrent portfolios limit? | Resource management |
| 3 | Should portfolio directives be editable after creation, or immutable? | Flexibility vs audit integrity |
| 4 | When migrating to a cloud store, should we support multi-device sync (same portfolio from two machines)? | Affects concurrency model in Protocol design |
