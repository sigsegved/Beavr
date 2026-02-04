# Beavr AI Investor v2 Architecture

## Intelligent Multi-Agent Trading System

**Version:** 2.0  
**Date:** February 4, 2026  
**Status:** Design Specification

---

## Abstract

This document presents a redesigned architecture for the Beavr AI Investor system. The current implementation suffers from several limitations: idle periods during market closures when valuable analysis could occur, an over-reliance on oversold conditions that may lead to "catching falling knives," and a lack of structured due diligence before trade execution. The proposed v2 architecture introduces a continuous research pipeline, momentum-based opportunity discovery, mandatory due diligence workflows, and explicit trade thesis management with expected exit dates.

The core innovation is treating the trading system as a research-first operation where hypotheses are formed before capital is deployed. Each position carries a documented thesis including entry rationale, expected catalyst, target exit date, and conditions that would invalidate the trade.

---

## 1. Problem Analysis

### 1.1 Current System Limitations

The existing system operates on a simple cycle: analyze during pre-market, execute at open, monitor for stop/target hits, sleep when markets close. This approach leaves significant value on the table.

**Idle Time Waste.** When markets close, the system enters a passive sleep state. However, overnight and weekend periods are when earnings announcements occur, macroeconomic data releases happen, and geopolitical events unfold. Professional traders use these periods to reassess positions, formulate new hypotheses, and prepare action plans. Our current system does none of this.

**Oversold Bias Problem.** The swing trader agent's prompt explicitly prioritizes "RSI < 30" and "near lower Bollinger Band" conditions. While mean reversion can work in range-bound markets, this bias causes the system to buy stocks in downtrends—the classic "catching a falling knife" pattern. A stock at RSI 25 can easily go to RSI 15 before any bounce occurs. The system lacks the ability to distinguish between healthy pullbacks and broken stocks.

**Missing Momentum Perspective.** Retail traders with small accounts often benefit more from momentum strategies than value plays. A stock gapping up 5% on news at market open frequently continues another 5-10% before fading. The current system has no mechanism to identify pre-market gaps, volume surges, or catalyst-driven momentum plays.

**No Due Diligence Layer.** The current flow is: screener finds candidates → analyst sets regime → trader picks from candidates → execute. There is no step where we deeply analyze an individual stock's fundamentals, recent news, insider activity, or competitive position. This leads to trades based purely on technical patterns without understanding the underlying business.

**Undefined Exit Strategy.** Positions are held until they hit arbitrary stop/target percentages. There is no concept of "I expect this stock to reach $X by earnings on February 15th" or "This is a three-day momentum trade, exit regardless of P/L by Friday close." Without explicit time horizons, positions can drift indefinitely.

### 1.2 Design Goals for v2

The redesigned system should address each limitation while maintaining simplicity and explainability. The core philosophy shifts from "find oversold stocks and buy them" to "develop investment theses and execute when evidence supports them."

Specific goals:

1. **Continuous Operation**: The system should always be working—researching, monitoring news, updating theses—even when markets are closed.

2. **Thesis-Driven Trading**: Every position must have a documented thesis including entry rationale, expected catalyst, target price, exit date, and invalidation conditions.

3. **Momentum + Quality**: Shift focus from oversold screens to momentum screens with quality filters. Look for stocks with positive catalysts and institutional support.

4. **Due Diligence Gate**: Before any trade executes, a Due Diligence agent must approve or reject based on deeper analysis than the initial screen.

5. **Time-Bound Positions**: Each trade should specify whether it's a day trade, swing trade (2-10 days), or position trade (weeks), with automatic review triggers.

---

## 2. Architecture Overview

### 2.1 System Topology

The v2 architecture introduces a research pipeline that operates independently of market hours, feeding into a trade execution system that operates during market hours.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                                                                              │
│                        BEAVR AI INVESTOR v2                                  │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐  │
│  │                     CONTINUOUS RESEARCH PIPELINE                       │  │
│  │                     (Runs 24/7 - Market Hours Agnostic)                │  │
│  │                                                                        │  │
│  │   ┌──────────────┐    ┌──────────────┐    ┌──────────────┐            │  │
│  │   │    News      │    │   Thesis     │    │   Watchlist  │            │  │
│  │   │   Monitor    │───▶│   Generator  │───▶│   Manager    │            │  │
│  │   │              │    │              │    │              │            │  │
│  │   │  Earnings,   │    │  Formulate   │    │  Rank and    │            │  │
│  │   │  Filings,    │    │  hypotheses  │    │  prioritize  │            │  │
│  │   │  Macro data  │    │  about moves │    │  candidates  │            │  │
│  │   └──────────────┘    └──────────────┘    └──────────────┘            │  │
│  │                                                    │                   │  │
│  └────────────────────────────────────────────────────┼───────────────────┘  │
│                                                       │                      │
│                                                       ▼                      │
│                                            ┌──────────────────┐              │
│                                            │   THESIS STORE   │              │
│                                            │                  │              │
│                                            │  Active theses   │              │
│                                            │  with catalysts, │              │
│                                            │  targets, dates  │              │
│                                            └────────┬─────────┘              │
│                                                     │                        │
│  ┌──────────────────────────────────────────────────┼─────────────────────┐  │
│  │                    MARKET HOURS EXECUTION                   │          │  │
│  │                    (Runs During Trading Hours)              │          │  │
│  │                                                             ▼          │  │
│  │   ┌──────────────┐    ┌──────────────┐    ┌──────────────────────┐    │  │
│  │   │   Morning    │    │     Due      │    │      Trade           │    │  │
│  │   │   Scanner    │───▶│  Diligence   │───▶│    Execution         │    │  │
│  │   │              │    │    Agent     │    │                      │    │  │
│  │   │  Pre-market  │    │              │    │  Position sizing,    │    │  │
│  │   │  gaps, volume│    │  Deep dive   │    │  order placement,    │    │  │
│  │   │  surges      │    │  on finalists│    │  thesis attachment   │    │  │
│  │   └──────────────┘    └──────────────┘    └──────────────────────┘    │  │
│  │                                                                        │  │
│  └────────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐  │
│  │                      POSITION MANAGEMENT                               │  │
│  │                      (Continuous During Market)                        │  │
│  │                                                                        │  │
│  │   ┌──────────────┐    ┌──────────────┐    ┌──────────────┐            │  │
│  │   │   Position   │    │    Thesis    │    │    Exit      │            │  │
│  │   │   Monitor    │───▶│   Validator  │───▶│   Executor   │            │  │
│  │   │              │    │              │    │              │            │  │
│  │   │  P/L, dates, │    │  Is thesis   │    │  Stop, target│            │  │
│  │   │  catalysts   │    │  still valid?│    │  or scheduled│            │  │
│  │   └──────────────┘    └──────────────┘    └──────────────┘            │  │
│  │                                                                        │  │
│  └────────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Agent Roles

The v2 system employs six specialized agents, each with clearly defined responsibilities. Unlike the current system where agents are loosely coordinated, v2 agents operate in a formal pipeline with explicit handoffs.

**News Monitor Agent.** This agent operates continuously, scanning for market-moving events. It monitors earnings calendars, SEC filings (8-K, 10-K/Q), macro economic releases (jobs report, CPI, Fed decisions), and financial news APIs. When it detects a potentially actionable event, it creates an event record that the Thesis Generator can act upon. The News Monitor does not make trading decisions—it surfaces information.

**Thesis Generator Agent.** Operating on events from the News Monitor and on a scheduled basis (e.g., nightly review), this agent formulates investment theses. A thesis is a structured hypothesis: "Stock X will move to price Y by date Z because of catalyst C. The thesis is invalidated if condition I occurs." The Thesis Generator uses LLM reasoning to connect news events to potential price movements, drawing on its training knowledge of market patterns.

**Morning Scanner Agent.** Running during pre-market (4:00 AM - 9:30 AM ET), this agent identifies the day's momentum opportunities. It looks for pre-market gaps, unusual volume, stocks breaking out of consolidation, and catalyst-driven moves. Unlike the current system's focus on oversold bounce candidates, the Morning Scanner prioritizes strength and momentum. Its output is a ranked list of "today's opportunities" that feeds into Due Diligence.

**Due Diligence Agent.** This is the quality gate before execution. When a stock is identified as a trading candidate (either from the Morning Scanner or from a mature thesis), the DD Agent performs a deep-dive analysis. It examines recent price action, volume profile, institutional ownership, recent insider transactions, analyst ratings, earnings history, and competitive positioning. The DD Agent outputs a "proceed" or "reject" recommendation with detailed reasoning. No trade executes without DD approval.

**Trade Executor Agent.** Once DD approves a trade, the Executor handles position sizing based on Kelly criterion or fixed fractional methods, order type selection (market vs. limit), and actual order placement via Alpaca API. It also attaches the thesis to the position record so we always know why we entered.

**Position Manager Agent.** This agent monitors open positions against their theses. It tracks P/L, checks if thesis conditions have changed, monitors for exit dates, and triggers exits when appropriate. If a catalyst fails to materialize or a thesis is invalidated, it recommends exit regardless of P/L.

---

## 3. Core Concepts

### 3.1 The Trade Thesis

The central innovation of v2 is the Trade Thesis—a structured document that must exist for every position. This replaces the current approach of "buy because RSI is low, sell when target/stop hit."

```python
class TradeThesis(BaseModel):
    """Structured investment hypothesis for a position."""
    
    # Identification
    id: str = Field(description="Unique thesis identifier")
    symbol: str = Field(description="Trading symbol")
    created_at: datetime
    
    # Classification
    trade_type: Literal["day_trade", "swing", "position"] = Field(
        description="Expected holding period category"
    )
    
    # Core Hypothesis
    direction: Literal["long", "short"] = Field(description="Trade direction")
    entry_rationale: str = Field(
        description="Why we are entering this trade (2-3 sentences)"
    )
    catalyst: str = Field(
        description="Specific event/condition expected to drive the move"
    )
    catalyst_date: Optional[date] = Field(
        description="When the catalyst is expected (earnings date, etc.)"
    )
    
    # Price Targets
    entry_price_target: Decimal = Field(description="Ideal entry price")
    profit_target: Decimal = Field(description="Price target for taking profits")
    stop_loss: Decimal = Field(description="Price level to cut losses")
    
    # Time Management
    expected_exit_date: date = Field(
        description="When we expect to exit, regardless of price"
    )
    max_hold_date: date = Field(
        description="Latest date to hold—must exit by this date"
    )
    
    # Invalidation
    invalidation_conditions: list[str] = Field(
        description="Conditions that would invalidate the thesis"
    )
    
    # Status Tracking
    status: Literal["draft", "active", "executed", "closed", "invalidated"]
    confidence: float = Field(ge=0.0, le=1.0)
    dd_approved: bool = Field(default=False)
    dd_report: Optional[str] = Field(default=None)
```

A sample thesis might read: "NVDA will rise to $950 by February 20th following their earnings report on February 21st. The thesis is based on expected strong data center revenue growth and AI chip demand. Entry target: $880. Target: $950. Stop: $840. Invalidation: If earnings miss estimates or if guidance is weak."

### 3.2 Trade Types and Time Horizons

The system explicitly categorizes trades into three types, each with different management rules:

**Day Trade (exit same day).** These are momentum plays on intraday moves. Typically entered within the first 30-60 minutes of market open on high-conviction setups. The position must close by end of day. Target profit: 2-5%. Stop loss: 1-2%. Risk management is tight because time horizon is short.

**Swing Trade (2-10 trading days).** These are multi-day trend continuation or mean reversion plays. The thesis includes a specific catalyst (earnings, product launch, technical breakout). Target profit: 5-15%. Stop loss: 3-7%. The position has both price-based and time-based exit conditions.

**Position Trade (2-6 weeks).** These are higher-conviction plays on longer-term themes. Requires stronger due diligence and larger expected moves to justify the hold period. Target profit: 10-25%. Stop loss: 5-10%. These trades might ride through a catalyst event like earnings.

### 3.3 Opportunity Discovery

The v2 system uses two complementary approaches to find trading candidates:

**Top-Down: Thesis Pipeline.** The continuous research pipeline identifies potential opportunities based on events and market analysis. A thesis might develop over days: Monday we see a catalyst approaching, Tuesday we research the company, Wednesday we add it to the watchlist, Thursday pre-market we see the setup and execute.

**Bottom-Up: Morning Scan.** The Morning Scanner looks for opportunities arising from overnight developments. A stock gaps up 8% on unexpected news. The scanner identifies it, DD Agent rapidly assesses it, and if approved, we catch the momentum.

Both pipelines converge at the Due Diligence gate. No distinction is made between how an opportunity was found—all candidates face the same DD scrutiny.

### 3.4 Quality Filters

To avoid penny stocks, pump-and-dumps, and illiquid names, the system enforces quality filters:

```python
class QualityFilter:
    """Quality criteria for tradeable stocks."""
    
    # Liquidity
    min_avg_volume: int = 500_000        # Minimum average daily volume
    min_dollar_volume: Decimal = Decimal("10_000_000")  # Min $ traded/day
    
    # Price
    min_price: Decimal = Decimal("10")   # No penny stocks
    max_price: Decimal = Decimal("1000") # Avoid stocks too expensive for sizing
    
    # Market Cap
    min_market_cap: Decimal = Decimal("500_000_000")  # $500M minimum
    
    # Tradability
    require_fractional: bool = False     # Fractional share support
    require_options: bool = False        # Has liquid options market
    
    # Exclusions
    excluded_sectors: list[str] = []     # e.g., ["biotech", "spac"]
```

---

## 4. Detailed Component Design

### 4.1 News Monitor Agent

The News Monitor runs on a 15-minute polling cycle during all hours. It aggregates events from multiple sources and creates structured event records.

```python
class MarketEvent(BaseModel):
    """A market-moving event detected by News Monitor."""
    
    event_type: Literal[
        "earnings_announced",
        "earnings_upcoming",
        "guidance_change",
        "analyst_upgrade",
        "analyst_downgrade",
        "insider_buy",
        "insider_sell",
        "sec_filing",
        "macro_release",
        "news_catalyst",
    ]
    symbol: Optional[str]  # None for macro events
    headline: str
    summary: str
    source: str
    timestamp: datetime
    importance: Literal["high", "medium", "low"]
    
    # Structured data when available
    earnings_date: Optional[date] = None
    estimate_eps: Optional[Decimal] = None
    actual_eps: Optional[Decimal] = None
```

Data sources for v2 include Alpaca's news API for real-time headlines, SEC EDGAR for filings, Yahoo Finance or similar for earnings calendars, and optionally premium services like Benzinga or Refinitiv for professional traders.

The News Monitor's LLM prompt focuses on classification and importance assessment:

```
You are a financial news analyst. Your job is to classify incoming news 
and events by their potential market impact.

For each event, assess:
1. Is this actionable for trading? (yes/no)
2. What is the expected direction of price impact? (positive/negative/neutral)
3. What is the expected magnitude? (high/medium/low)
4. What is the time window for the impact? (immediate/days/weeks)

Only flag events that could drive a 2%+ move in a liquid stock.
```

### 4.2 Thesis Generator Agent

The Thesis Generator operates in two modes: event-driven (responding to News Monitor events) and scheduled (nightly review of watchlist and market conditions).

When processing an event, the Thesis Generator evaluates whether a tradeable thesis can be formed. Not every event leads to a thesis—most are noise. The agent's prompt emphasizes selectivity:

```
You are a senior portfolio manager formulating trade ideas.

Given the following market event, determine if a tradeable thesis exists.

A good thesis requires:
1. A clear catalyst with a known date or timeframe
2. An asymmetric risk/reward (target > 2x stop distance)
3. Technical support for the direction (trend, support level, etc.)
4. Reasonable confidence the catalyst will drive the expected move

If you cannot articulate a specific price target and exit date, 
there is no thesis—pass on the opportunity.

Output a complete thesis or "NO THESIS" with explanation.
```

### 4.3 Morning Scanner Agent

The Morning Scanner runs from 4:00 AM to 9:30 AM ET, with peak activity right before market open. It focuses on identifying the day's best momentum opportunities.

Screening criteria for momentum plays:

1. **Gap Ups > 3%**: Stocks gapping significantly higher on pre-market volume indicate strong buyer interest. Filter for quality (not penny stocks, not earnings miss bounces).

2. **Volume Surge**: Pre-market volume 2x+ average indicates institutional interest.

3. **Breaking Resistance**: Stocks approaching or breaking through technical resistance levels.

4. **Sector Rotation**: If a sector ETF is surging, identify the best individual names in that sector.

5. **Catalyst Alignment**: Cross-reference with active theses—if a stock we've been watching finally shows the setup, prioritize it.

The scanner output is a ranked list of 3-5 candidates with preliminary thesis outlines:

```python
class MorningCandidate(BaseModel):
    """A trading candidate from the morning scan."""
    
    symbol: str
    scan_type: Literal[
        "gap_up", "volume_surge", "breakout", 
        "sector_leader", "thesis_setup"
    ]
    pre_market_price: Decimal
    pre_market_change_pct: float
    pre_market_volume: int
    avg_volume: int
    
    # Quick technicals
    key_resistance: Optional[Decimal]
    key_support: Optional[Decimal]
    rsi_14: Optional[float]
    
    # Preliminary assessment
    catalyst_summary: str
    preliminary_direction: Literal["long", "short"]
    preliminary_target_pct: float
    preliminary_stop_pct: float
    
    # Ranking
    conviction_score: float = Field(ge=0.0, le=1.0)
    priority_rank: int = Field(ge=1)
```

### 4.4 Due Diligence Agent

The DD Agent is the critical quality gate. When a candidate reaches this stage, the DD Agent performs a comprehensive analysis before approving or rejecting the trade.

DD Analysis Framework:

1. **Fundamental Check**: Is this a real company with real revenue? What's the valuation (P/E, P/S)? Is it reasonable for the sector?

2. **Technical Analysis**: Beyond the immediate setup, what does the longer-term picture show? Are we buying into resistance or support?

3. **Catalyst Verification**: Is the catalyst real and still upcoming? Has anything changed since the thesis was formed?

4. **Risk Assessment**: What's the maximum realistic downside? Are there known risks (upcoming lockup expiry, secondary offering, regulatory issues)?

5. **Position Sizing Input**: Based on volatility and conviction, what's the appropriate position size?

The DD Agent outputs a structured report:

```python
class DueDiligenceReport(BaseModel):
    """Comprehensive DD report for a trading candidate."""
    
    symbol: str
    analyst_name: Literal["DD Agent"]
    timestamp: datetime
    
    # Verdict
    recommendation: Literal["approve", "reject", "conditional"]
    confidence: float = Field(ge=0.0, le=1.0)
    
    # Analysis Sections
    fundamental_summary: str      # 2-3 sentences on fundamentals
    technical_summary: str        # 2-3 sentences on technicals  
    catalyst_assessment: str      # Assessment of the catalyst
    risk_factors: list[str]       # Key risks identified
    
    # Adjusted Targets (DD may modify thesis targets)
    recommended_entry: Decimal
    recommended_target: Decimal
    recommended_stop: Decimal
    recommended_position_size_pct: float
    
    # Rationale
    approval_rationale: Optional[str] = None  # Why approve
    rejection_rationale: Optional[str] = None  # Why reject
    conditions: Optional[list[str]] = None    # Conditions for conditional approval
```

When the DD Agent rejects a candidate, the rejection reason is logged and can be used to improve the upstream scanning and thesis generation.

### 4.5 Trade Executor Agent

The Executor is relatively simple—it translates approved trades into Alpaca orders. Its responsibilities:

1. **Position Sizing**: Calculate shares based on portfolio value, risk budget, and DD recommendations.

2. **Order Type Selection**: Market orders for urgent momentum plays, limit orders for thesis-based entries where we can wait.

3. **Order Placement**: Submit to Alpaca API with proper time-in-force.

4. **Record Keeping**: Create position record with attached thesis and DD report.

```python
class ExecutionPlan(BaseModel):
    """Plan for executing a trade."""
    
    thesis_id: str
    symbol: str
    direction: Literal["buy", "sell"]
    
    # Sizing
    position_value: Decimal
    shares: Decimal
    
    # Order Details
    order_type: Literal["market", "limit"]
    limit_price: Optional[Decimal] = None
    time_in_force: Literal["day", "gtc", "ioc"]
    
    # Risk Levels (attached to position)
    stop_loss_price: Decimal
    target_price: Decimal
    max_hold_until: date
```

### 4.6 Position Manager Agent

The Position Manager reviews all open positions on a regular interval (every 5 minutes during market hours) and determines if any action is required.

Position review checklist:

1. **Price-Based Exits**: Has the position hit stop loss or profit target?

2. **Time-Based Review**: Is this position approaching or past its expected exit date? If past max hold date, force exit.

3. **Thesis Validation**: Is the original thesis still intact? Has the catalyst occurred? Did it play out as expected?

4. **Invalidation Check**: Have any invalidation conditions triggered?

5. **Partial Profit Taking**: For positions up significantly but below target, consider taking partial profits.

```python
class PositionReview(BaseModel):
    """Daily review of a position against its thesis."""
    
    position_id: str
    symbol: str
    review_date: date
    
    # Current State
    entry_price: Decimal
    current_price: Decimal
    unrealized_pnl: Decimal
    unrealized_pnl_pct: float
    days_held: int
    
    # Thesis Check
    thesis_status: Literal["intact", "weakening", "invalidated"]
    catalyst_status: Literal["pending", "occurred", "missed"]
    
    # Recommendation
    action: Literal["hold", "exit_full", "exit_partial", "adjust_stop"]
    action_rationale: str
    
    # If exit recommended
    exit_type: Optional[Literal[
        "target_hit", "stop_hit", "thesis_invalidated",
        "time_exit", "manual"
    ]] = None
```

---

## 5. Data Architecture

### 5.1 Database Schema

The v2 system requires additional tables beyond the current AI positions table:

```sql
-- Market events from News Monitor
CREATE TABLE market_events (
    id INTEGER PRIMARY KEY,
    event_type TEXT NOT NULL,
    symbol TEXT,
    headline TEXT NOT NULL,
    summary TEXT,
    source TEXT NOT NULL,
    timestamp DATETIME NOT NULL,
    importance TEXT NOT NULL,
    raw_data JSON,
    processed_at DATETIME
);

-- Trade theses
CREATE TABLE trade_theses (
    id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    created_at DATETIME NOT NULL,
    trade_type TEXT NOT NULL,
    direction TEXT NOT NULL,
    entry_rationale TEXT NOT NULL,
    catalyst TEXT NOT NULL,
    catalyst_date DATE,
    entry_price_target DECIMAL(18, 4),
    profit_target DECIMAL(18, 4),
    stop_loss DECIMAL(18, 4),
    expected_exit_date DATE NOT NULL,
    max_hold_date DATE NOT NULL,
    invalidation_conditions JSON,
    status TEXT NOT NULL,
    confidence REAL,
    dd_approved INTEGER DEFAULT 0,
    dd_report TEXT,
    
    FOREIGN KEY (symbol) REFERENCES watchlist(symbol)
);

-- DD reports
CREATE TABLE dd_reports (
    id INTEGER PRIMARY KEY,
    thesis_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    timestamp DATETIME NOT NULL,
    recommendation TEXT NOT NULL,
    confidence REAL,
    fundamental_summary TEXT,
    technical_summary TEXT,
    catalyst_assessment TEXT,
    risk_factors JSON,
    recommended_entry DECIMAL(18, 4),
    recommended_target DECIMAL(18, 4),
    recommended_stop DECIMAL(18, 4),
    recommended_position_size_pct REAL,
    approval_rationale TEXT,
    rejection_rationale TEXT,
    
    FOREIGN KEY (thesis_id) REFERENCES trade_theses(id)
);

-- Enhanced positions (extends current ai_positions)
CREATE TABLE ai_positions_v2 (
    id INTEGER PRIMARY KEY,
    thesis_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    quantity DECIMAL(18, 8) NOT NULL,
    entry_price DECIMAL(18, 4) NOT NULL,
    entry_timestamp DATETIME NOT NULL,
    
    -- Price targets (from thesis, may be adjusted)
    stop_loss_price DECIMAL(18, 4) NOT NULL,
    target_price DECIMAL(18, 4) NOT NULL,
    
    -- Time management
    expected_exit_date DATE NOT NULL,
    max_hold_date DATE NOT NULL,
    
    -- Status tracking
    status TEXT NOT NULL DEFAULT 'open',
    exit_price DECIMAL(18, 4),
    exit_timestamp DATETIME,
    exit_type TEXT,
    
    -- Performance
    realized_pnl DECIMAL(18, 4),
    realized_pnl_pct REAL,
    
    FOREIGN KEY (thesis_id) REFERENCES trade_theses(id)
);

-- Position reviews (audit trail)
CREATE TABLE position_reviews (
    id INTEGER PRIMARY KEY,
    position_id INTEGER NOT NULL,
    review_date DATE NOT NULL,
    thesis_status TEXT,
    catalyst_status TEXT,
    action TEXT,
    action_rationale TEXT,
    
    FOREIGN KEY (position_id) REFERENCES ai_positions_v2(id)
);
```

### 5.2 State Management

The system maintains state across restarts using the SQLite database and a JSON state file for runtime information:

```python
class SystemState(BaseModel):
    """Runtime state persisted between restarts."""
    
    # Last run times
    last_news_scan: datetime
    last_thesis_review: datetime
    last_morning_scan: datetime
    
    # Active session
    session_start: datetime
    trades_today: int
    capital_deployed_today: Decimal
    
    # Pipeline state
    pending_theses: list[str]  # Thesis IDs awaiting DD
    watchlist: list[str]       # Symbols on active watch
    
    # Circuit breakers
    daily_loss: Decimal
    consecutive_losses: int
    trading_enabled: bool
```

---

## 6. Operational Workflow

### 6.1 Daily Timeline

The v2 system operates on a structured daily timeline:

**Overnight (8:00 PM - 4:00 AM ET)**
- News Monitor polls every 15 minutes
- Thesis Generator processes any high-importance events
- System prepares watchlist for next day based on active theses

**Pre-Market (4:00 AM - 9:30 AM ET)**
- Morning Scanner activates at 4:00 AM
- Pre-market data collection begins
- At 8:00 AM, first candidate list generated
- At 9:00 AM, DD Agent begins processing top candidates
- At 9:25 AM, final execution plan locked

**Market Hours (9:30 AM - 4:00 PM ET)**
- At 9:30 AM, Trade Executor submits approved orders
- Position Manager begins monitoring (5-minute intervals)
- Continuous P/L and thesis validation
- Exit orders triggered as conditions hit

**After Hours (4:00 PM - 8:00 PM ET)**
- Position Manager generates daily summary
- Thesis Generator reviews closed positions for learnings
- System prepares overnight monitoring priorities

### 6.2 Entry Flow

```
Morning Scan Result OR Mature Thesis
            │
            ▼
┌─────────────────────────┐
│  Quality Filter Check   │◄──── Reject low-quality candidates
└───────────┬─────────────┘
            │ Pass
            ▼
┌─────────────────────────┐
│   Due Diligence Agent   │◄──── Deep analysis
└───────────┬─────────────┘
            │ Approve
            ▼
┌─────────────────────────┐
│  Capital Availability   │◄──── Check cash, daily limits
└───────────┬─────────────┘
            │ OK
            ▼
┌─────────────────────────┐
│    Trade Executor       │◄──── Position sizing, order placement
└───────────┬─────────────┘
            │
            ▼
    Position Created with
    Thesis + DD Attached
```

### 6.3 Exit Flow

```
Position Monitor Tick (every 5 min)
            │
            ▼
┌─────────────────────────┐
│   Price Check           │
│   Stop hit? Target hit? │───── Yes ──▶ Execute Exit
└───────────┬─────────────┘
            │ No
            ▼
┌─────────────────────────┐
│   Time Check            │
│   Past max_hold_date?   │───── Yes ──▶ Execute Exit
└───────────┬─────────────┘
            │ No
            ▼
┌─────────────────────────┐
│   Thesis Validation     │
│   Still valid?          │───── No ──▶ Flag for Review
└───────────┬─────────────┘
            │ Yes
            ▼
      Continue Holding
```

---

## 7. Configuration

### 7.1 Agent Configuration

Each agent has configurable parameters that can be tuned without code changes:

```toml
# config/ai_investor_v2.toml

[system]
mode = "live"  # "paper" | "live"
capital_allocation = 0.80  # Max % of portfolio for AI trading
daily_trade_limit = 5
max_position_pct = 0.25  # Max single position size

[quality_filter]
min_avg_volume = 500_000
min_price = 10.0
max_price = 1000.0
min_market_cap = 500_000_000

[news_monitor]
poll_interval_minutes = 15
sources = ["alpaca", "sec_edgar"]
importance_threshold = "medium"  # Only process medium+ importance

[thesis_generator]
min_confidence = 0.6
max_active_theses = 20
review_interval_hours = 12

[morning_scanner]
scan_start_time = "04:00"  # ET
gap_threshold_pct = 3.0
volume_surge_multiple = 2.0
max_candidates = 5

[due_diligence]
min_approval_confidence = 0.65
require_fundamental_check = true
require_technical_check = true
max_risk_score = 0.7

[trade_executor]
default_order_type = "market"
position_sizing_method = "fixed_fractional"  # or "kelly"
fixed_fraction_pct = 0.10

[position_manager]
check_interval_minutes = 5
enable_partial_profits = true
partial_profit_threshold_pct = 10.0
partial_profit_pct = 0.50  # Sell 50% at partial profit threshold

[risk]
max_daily_loss_pct = 3.0
max_consecutive_losses = 3
circuit_breaker_cooldown_hours = 24
```

### 7.2 Trade Type Profiles

```toml
[trade_types.day_trade]
default_target_pct = 3.0
default_stop_pct = 1.5
max_hold_hours = 6
min_conviction = 0.70

[trade_types.swing]
default_target_pct = 8.0
default_stop_pct = 4.0
max_hold_days = 10
min_conviction = 0.60

[trade_types.position]
default_target_pct = 15.0
default_stop_pct = 7.0
max_hold_days = 30
min_conviction = 0.75
```

---

## 8. Risk Management

### 8.1 Position-Level Risk

Each position has explicit stop losses attached to the thesis. Unlike the current percentage-based stops, v2 stops are price-based and derived from technical analysis:

- Support levels
- Average true range (ATR) multiples
- Maximum acceptable loss for position size

### 8.2 Portfolio-Level Risk

The system enforces portfolio-wide risk limits:

**Daily Loss Limit**: If the portfolio loses more than 3% in a single day, all trading halts and circuit breaker activates. Existing positions are monitored but no new positions are opened.

**Consecutive Loss Limit**: After 3 consecutive losing trades, the system pauses new entries for 24 hours and Thesis Generator review is triggered to assess if market conditions have changed.

**Capital Guard**: A minimum 10% cash buffer is always maintained. The system cannot deploy more than the configured capital allocation.

### 8.3 Sizing Rules

Position sizing follows conservative rules to ensure no single trade can significantly damage the portfolio:

```python
def calculate_position_size(
    portfolio_value: Decimal,
    risk_budget: Decimal,
    entry_price: Decimal,
    stop_price: Decimal,
    max_position_pct: float = 0.25,
) -> Decimal:
    """
    Calculate position size based on risk parameters.
    
    Uses the risk-based formula:
    shares = (risk_budget * portfolio_value) / (entry_price - stop_price)
    
    Capped at max_position_pct of portfolio.
    """
    risk_per_share = abs(entry_price - stop_price)
    risk_amount = risk_budget * portfolio_value
    
    position_value = risk_amount / risk_per_share * entry_price
    max_position_value = portfolio_value * Decimal(str(max_position_pct))
    
    return min(position_value, max_position_value)
```

---

## 9. Integration with Existing Beavr

### 9.1 Code Organization

The v2 system builds on existing Beavr infrastructure while introducing new modules:

```
src/beavr/
├── agents/
│   ├── base.py              # Existing - updated with v2 interfaces
│   ├── market_analyst.py    # Existing - retained for regime detection
│   ├── swing_trader.py      # Deprecated in v2
│   ├── dd_agent.py          # NEW - Due Diligence agent
│   ├── news_monitor.py      # NEW - Continuous news monitoring
│   ├── thesis_generator.py  # NEW - Hypothesis formation
│   ├── morning_scanner.py   # NEW - Pre-market opportunity scanner
│   ├── position_manager.py  # NEW - Active position management
│   └── trade_executor.py    # NEW - Order execution
│
├── orchestrator/
│   ├── engine.py            # Major update - continuous operation
│   ├── blackboard.py        # Existing - extended with thesis storage
│   └── scheduler.py         # NEW - Task scheduling across market hours
│
├── models/
│   ├── thesis.py            # NEW - Trade thesis model
│   ├── dd_report.py         # NEW - DD report model
│   ├── market_event.py      # NEW - News/event model
│   └── ...                  # Existing models
│
├── db/
│   ├── thesis_repo.py       # NEW - Thesis CRUD operations
│   ├── events_repo.py       # NEW - Event storage
│   ├── positions_v2_repo.py # NEW - Enhanced positions
│   └── ...                  # Existing
│
└── cli/
    ├── ai.py                # Major update - new commands
    └── ...
```

### 9.2 CLI Commands

The v2 CLI extends the current `bvr ai` interface:

```bash
# Existing commands (retained)
bvr ai status        # Portfolio and system status
bvr ai invest        # Manual investment (uses v2 pipeline)
bvr ai watch         # Monitor positions (enhanced with thesis info)
bvr ai history       # Trade history (shows thesis outcomes)

# New commands
bvr ai auto          # Autonomous loop (major rework for v2)
bvr ai thesis        # Manage theses
bvr ai thesis list   # List active theses
bvr ai thesis show   # Show thesis details
bvr ai thesis create # Manually create a thesis
bvr ai news          # View recent market events
bvr ai dd            # Trigger manual DD for a symbol
bvr ai scan          # Run morning scan manually
```

### 9.3 Migration Path

Since v2 represents a significant change, the migration approach is:

1. **Parallel Implementation**: Build v2 agents alongside existing code
2. **Feature Flag**: Use configuration to enable v2 vs v1 mode
3. **Data Migration**: Write script to convert existing ai_positions to v2 format
4. **Gradual Rollout**: Run v2 in paper trading mode while v1 handles live

---

## 10. Success Metrics

### 10.1 System Performance

The v2 system should be measured against the following targets:

| Metric | Target | Measurement |
|--------|--------|-------------|
| Win Rate | > 50% | Percentage of trades closed at profit |
| Profit Factor | > 1.5 | Gross profit / gross loss |
| Max Drawdown | < 15% | Largest peak-to-trough decline |
| Sharpe Ratio | > 1.0 | Risk-adjusted returns |
| DD Rejection Rate | 20-40% | Indicates proper filtering |
| Avg Days Held | < 5 | For swing trades |
| Thesis Accuracy | > 60% | Catalyst outcome matches prediction |

### 10.2 Operational Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| System Uptime | > 99% | During market hours |
| Order Fill Rate | > 95% | Orders successfully executed |
| Latency (scan to order) | < 60s | Morning scan to order submission |
| News Processing Delay | < 15 min | Event occurrence to thesis consideration |

---

## 11. Future Enhancements

The v2 architecture is designed to support future capabilities:

**Short Selling**: The thesis model already supports short direction. Adding short execution requires Alpaca margin account and short availability checking.

**Options Integration**: For higher-conviction plays, options can provide leverage with defined risk. The thesis framework naturally extends to options strategies.

**Multi-Strategy Coordination**: Multiple strategy "modes" could run simultaneously (momentum, mean-reversion, event-driven) with capital allocation between them.

**ML Enhancement**: Historical trade data can train models to predict thesis success probability, improving the DD approval process.

**Social Sentiment**: Integrating Twitter/Reddit sentiment as a signal source for the News Monitor.

---

## Acknowledgments

This architecture draws on established concepts from professional trading systems including thesis-driven investing (as practiced by hedge funds), systematic momentum strategies, and modern multi-agent AI frameworks. The design balances automation with explainability, ensuring that every trade has documented rationale that can be reviewed and improved.

---

## Appendix A: Sample Thesis Lifecycle

**Day 0 (Thursday night)**
News Monitor detects: "COST reports earnings Monday after close"
Thesis Generator creates thesis:
- Symbol: COST
- Catalyst: Q4 earnings report
- Direction: Long
- Entry target: $985 (2% pullback from current $1005)
- Target: $1050 (after positive earnings reaction)
- Stop: $960 (below support)
- Expected exit: Wednesday (2 days post earnings)
- Status: draft

**Day 1 (Friday)**
No entry—COST stays above entry target
Thesis remains draft, added to watchlist

**Day 2 (Monday)**
Pre-market: COST dips to $982
Morning Scanner: Flags COST as thesis setup
DD Agent: Examines COST fundamentals, recent data, analyst expectations
DD Verdict: Approve with adjusted entry $983, reduces target to $1035
Trade Executor: Buys COST $983, attaches thesis

**Day 3 (Tuesday)**
COST reports earnings after close—beats estimates
After hours: COST rises to $1010

**Day 4 (Wednesday)**
Position Manager: COST opens at $1028
Review: Target $1035 not yet hit, but thesis playing out
Decision: Hold per thesis

**Day 4 (Wednesday midday)**
COST touches $1037
Position Manager: Target exceeded, execute exit
Exit: Sell COST $1036
Result: +5.4% profit, thesis validated

**Post-Close**
Thesis marked "closed" with outcome "target_hit"
Statistics updated for future analysis

---

## Appendix B: Architecture Review Notes

**Reviewer**: Lead Architect  
**Date**: February 4, 2026

### Review Summary

The v2 architecture successfully addresses the core problems identified with v1. The thesis-driven approach provides the missing intentionality, the DD gate adds necessary quality control, and the continuous research pipeline eliminates wasted idle time. The following observations and refinements were made during review:

### Addressed During Review

**News Data Source Pragmatism.** The initial design mentioned multiple premium data sources (Benzinga, Refinitiv). For the initial implementation, we should focus on freely available sources: Alpaca News API (included with trading), SEC EDGAR (public), and free earnings calendar APIs. Premium sources can be added later as optional plugins.

**LLM Cost Management.** With agents running continuously, LLM costs could escalate quickly. The architecture now enforces importance thresholds—the News Monitor only forwards "medium" or higher importance events to the Thesis Generator. Additionally, the nightly thesis review should batch process rather than making per-stock LLM calls.

**Graceful Degradation.** If the LLM provider is unavailable, the system should degrade gracefully. The Morning Scanner can operate on purely technical criteria (gaps, volume) without LLM reasoning. The DD Agent is the only mandatory LLM component—if it's unavailable, no trades execute (safe default).

**Testing Strategy.** The architecture supports testing at multiple levels: unit tests for each agent in isolation, integration tests for the pipeline flow, and paper trading for full system validation. The v1 backtest engine can validate thesis generation against historical data.

**Observability.** Every agent action should be logged with structured fields (agent, action, symbol, timestamp, llm_tokens_used). This enables debugging and cost tracking. A simple dashboard showing active theses, pending DD, and position status would improve operator experience.

### Deferred to Future Versions

- Short selling support (requires margin account)
- Options integration (complex execution)
- Multi-strategy portfolio allocation (v3 feature)
- ML-based thesis scoring (requires historical data accumulation)

### Implementation Recommendation

Implement in phases:
1. Core models and database schema
2. Research pipeline (News Monitor → Thesis Generator)
3. Morning Scanner (technical only, no LLM initially)
4. DD Agent (critical path component)
5. Trade execution and position management
6. CLI integration and autonomous loop update

This phased approach allows testing each component before adding the next layer.

---

## Appendix C: Glossary

**Thesis**: A structured hypothesis about a stock's future price movement, including catalyst, targets, and invalidation conditions.

**DD (Due Diligence)**: Deep analysis of a trading candidate before execution.

**Catalyst**: The specific event expected to drive price movement.

**Invalidation**: Conditions that would prove the thesis wrong, requiring exit regardless of P/L.

**Morning Scan**: Pre-market screening for day's momentum opportunities.

**Gap**: A stock opening significantly higher (gap up) or lower (gap down) than previous close.

**Circuit Breaker**: Automatic trading halt triggered by excessive losses.
