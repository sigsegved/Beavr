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

The v2 architecture introduces a research pipeline that operates independently of market hours, feeding into a trade execution system that operates during market hours. Critically, the **Due Diligence Agent runs during non-market hours** to allow for deep research without time pressure.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                                                                              │
│                        BEAVR AI INVESTOR v2                                  │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐  │
│  │                     CONTINUOUS RESEARCH PIPELINE                       │  │
│  │                     (Runs 24/7 - Market Hours Agnostic)                │  │
│  │                                                                        │  │
│  │   ┌──────────────┐    ┌──────────────┐    ┌──────────────┐             │  │
│  │   │    News      │    │   Thesis     │    │   Watchlist  │             │  │
│  │   │   Monitor    │───▶│   Generator  │───▶│   Manager    │             │  │
│  │   │              │    │              │    │              │             │  │
│  │   │  Earnings,   │    │  Formulate   │    │  Rank and    │             │  │
│  │   │  Filings,    │    │  hypotheses  │    │  prioritize  │             │  │
│  │   │  Macro data  │    │  about moves │    │  candidates  │             │  │
│  │   └──────────────┘    └──────────────┘    └──────────────┘             │  │
│  │                                                    │                   │  │
│  │                                                    ▼                   │  │
│  │                                           ┌──────────────┐             │  │
│  │                                           │     Due      │             │  │
│  │                                           │  Diligence   │             │  │
│  │                                           │    Agent     │             │  │
│  │                                           │              │             │  │
│  │                                           │ Deep research│             │  │
│  │                                           │ overnight    │             │  │
│  │                                           └──────┬───────┘             │  │
│  │                                                  │                     │  │
│  └──────────────────────────────────────────────────┼─────────────────────┘  │
│                                                     │                        │
│                                                     ▼                        │
│                                            ┌──────────────────┐              │
│                                            │   THESIS STORE   │              │
│                                            │   + DD REPORTS   │              │
│                                            │                  │              │
│                                            │  Approved theses │              │
│                                            │  with DD reports │              │
│                                            │  ready to trade  │              │
│                                            └────────┬─────────┘              │
│                                                     │                        │
│  ┌──────────────────────────────────────────────────┼─────────────────────┐  │
│  │                    MARKET HOURS EXECUTION                   │          │  │
│  │                    (9:30 AM - 4:00 PM ET)                   │          │  │
│  │                                                             ▼          │  │
│  │   ┌──────────────┐    ┌──────────────┐    ┌──────────────────────┐     │  │
│  │   │   Morning    │    │   Opening    │    │      Trade           │     │  │
│  │   │   Scanner    │───▶│   Range      │───▶│    Execution         │     │  │
│  │   │              │    │   Analyzer   │    │                      │     │  │
│  │   │  Pre-market  │    │              │    │  Position sizing,    │     │  │
│  │   │  gaps, volume│    │  Wait 5 mins │    │  order placement,    │     │  │
│  │   │  surges      │    │  assess move │    │  thesis attachment   │     │  │
│  │   └──────────────┘    └──────────────┘    └──────────────────────┘     │  │
│  │                                                                        │  │
│  └────────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐  │
│  │                      POSITION MANAGEMENT                               │  │
│  │                      (Continuous During Market)                        │  │
│  │                                                                        │  │
│  │   ┌──────────────┐    ┌──────────────┐    ┌──────────────┐             │  │
│  │   │   Position   │    │    Thesis    │    │    Exit      │             │  │
│  │   │   Monitor    │───▶│   Validator  │───▶│   Executor   │             │  │
│  │   │              │    │              │    │              │             │  │
│  │   │  P/L, dates, │    │  Is thesis   │    │  Stop, target│             │  │
│  │   │  catalysts   │    │  still valid?│    │  or scheduled│             │  │
│  │   └──────────────┘    └──────────────┘    └──────────────┘             │  │
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

**Due Diligence Agent.** This is the quality gate before execution, and critically, **it runs during non-market hours** to allow for thorough research without time pressure. When a stock is identified as a trading candidate (from Watchlist or Thesis Generator), the DD Agent performs deep-dive analysis overnight. It examines recent price action, volume profile, institutional ownership, recent insider transactions, analyst ratings, earnings history, and competitive positioning. The DD Agent outputs a "proceed" or "reject" recommendation with detailed reasoning, categorizing each opportunity as either a **day trade** (for the opening power hour) or a **swing trade** (1 week to 1 year hold). All DD reports are persisted to disk in both structured JSON and human-readable markdown formats for user consumption. No trade executes without DD approval.

**Trade Executor Agent.** Once DD approves a trade, the Executor handles position sizing based on Kelly criterion or fixed fractional methods, order type selection (market vs. limit), and actual order placement via Alpaca API. For day trades, execution waits until 5 minutes after market open to assess the opening range before committing. It also attaches the thesis and DD report to the position record so we always know why we entered.

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

The system categorizes trades into two primary types, with swing trades further subdivided by time horizon. The DD Agent is responsible for classifying each opportunity into the appropriate category based on the catalyst timing, technical setup, and expected move duration.

#### 3.2.1 Day Trade (Power Hour Strategy)

**Philosophy:** The first hour of trading (9:30 AM - 10:30 AM ET) accounts for approximately 30-40% of daily volume. This liquidity creates the best opportunities for quick entries and exits. The strategy exploits the fact that overnight news and pre-market activity create imbalances that resolve quickly in the opening hour.

**Opening Range Strategy:**
1. **Do NOT trade at 9:30 AM** - Wait exactly 5 minutes after market open (9:35 AM)
2. **Observe the opening range** - Track high/low of first 5 minutes
3. **Assess momentum direction** - Is price confirming or reversing pre-market move?
4. **Enter on confirmation** - If DD thesis aligns with opening direction, enter between 9:35-9:45 AM
5. **Target exit by 10:30 AM** - Close position within the power hour regardless of P/L

**Day Trade Characteristics:**
- Entry window: 9:35 AM - 9:45 AM ET (after opening range established)
- Exit deadline: 10:30 AM ET (end of power hour)
- Maximum hold: Never past 4:00 PM same day
- Target profit: 1-3% (tight because time is short)
- Stop loss: 0.5-1% (must be disciplined)
- Position size: Smaller (higher frequency, lower conviction per trade)

**Ideal Day Trade Candidates:**
- Stocks gapping 3-8% on news/earnings
- High pre-market volume (2x+ average)
- Clear catalyst driving the move
- Liquid enough for quick exit (avg volume > 1M)

#### 3.2.2 Swing Trade (1 Week to 1 Year)

Swing trades are the core strategy for building wealth over time. Unlike day trades that exploit short-term volatility, swing trades capture larger moves driven by fundamental catalysts. The DD Agent categorizes swing trades into three time horizons:

**Short-Term Swing (1-2 weeks)**
- Catalyst: Earnings, product launches, FDA decisions
- Entry: Technical breakout or pullback to support
- Target profit: 5-10%
- Stop loss: 3-5%
- Example thesis: "AMD will rally 8% post-earnings on strong data center demand. Enter $165, target $178, stop $157, exit within 5 trading days."

**Medium-Term Swing (1-3 months)**
- Catalyst: Sector rotation, macro themes, analyst upgrades
- Entry: Technical trend following with fundamental support
- Target profit: 10-20%
- Stop loss: 5-8%
- Example thesis: "COST will benefit from consumer shift to value. Enter on pullback to $900, target $1050 by Q2 earnings, stop $850."

**Long-Term Swing (3-12 months)**
- Catalyst: Structural business transformation, industry disruption
- Entry: Value accumulation during market weakness
- Target profit: 20-50%
- Stop loss: 10-15%
- Example thesis: "META's AI investments will drive 30% revenue growth over 12 months. Accumulate at $550, target $750 by year-end, stop $475."

#### 3.2.3 Trade Type Selection Theory

The DD Agent uses the following framework to classify opportunities:

| Factor | Day Trade | Short Swing | Medium Swing | Long Swing |
|--------|-----------|-------------|--------------|------------|
| Catalyst timing | Today | 1-2 weeks | 1-3 months | 3-12 months |
| Price move expected | 1-3% | 5-10% | 10-20% | 20-50% |
| Conviction required | Medium | Medium-High | High | Very High |
| Position size | 2-5% portfolio | 5-10% portfolio | 10-15% portfolio | 15-25% portfolio |
| DD depth required | Rapid (30 min) | Standard (2 hrs) | Deep (4+ hrs) | Comprehensive |
| News sensitivity | High | Medium | Low | Very Low |

**Decision Tree for Trade Type:**
```
Is catalyst happening TODAY?
├── Yes → Day Trade (if pre-market gap > 3%)
└── No → When is catalyst?
    ├── 1-2 weeks → Short-Term Swing
    ├── 1-3 months → Medium-Term Swing
    └── 3+ months → Long-Term Swing (higher bar for entry)
```

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

The DD Agent is the critical quality gate and **runs during non-market hours** (typically overnight) to allow for thorough research without the pressure of trading decisions. This timing is intentional—deep research should not be rushed.

#### 4.4.1 Operating Schedule

```
OVERNIGHT DD CYCLE (runs 8:00 PM - 6:00 AM ET)
├── 8:00 PM: Collect day's candidates from Thesis Generator
├── 8:30 PM: Begin deep research cycle
│   ├── For each candidate:
│   │   ├── Fundamental analysis (30-60 min per stock)
│   │   ├── Technical analysis (15-30 min per stock)
│   │   ├── News/catalyst verification (15 min per stock)
│   │   └── Generate and save DD report
│   └── Prioritize by catalyst urgency
├── 6:00 AM: All DD reports complete and saved
└── Reports ready for Morning Scanner to consume
```

#### 4.4.2 DD Analysis Framework

1. **Fundamental Check**: Is this a real company with real revenue? What's the valuation (P/E, P/S)? Is it reasonable for the sector? How does it compare to peers?

2. **Technical Analysis**: Beyond the immediate setup, what does the longer-term picture show? Are we buying into resistance or support? What's the trend on multiple timeframes?

3. **Catalyst Verification**: Is the catalyst real and still upcoming? Has anything changed since the thesis was formed? What's the historical price reaction to similar catalysts?

4. **Risk Assessment**: What's the maximum realistic downside? Are there known risks (upcoming lockup expiry, secondary offering, regulatory issues, earnings whisper numbers)?

5. **Trade Type Classification**: Based on catalyst timing and expected move duration, classify as day trade or swing trade (short/medium/long term).

6. **Position Sizing Input**: Based on volatility, conviction, and trade type, what's the appropriate position size?

#### 4.4.3 DD Report Model

```python
class DueDiligenceReport(BaseModel):
    """Comprehensive DD report for a trading candidate."""
    
    # Identification
    report_id: str = Field(description="Unique report identifier (UUID)")
    thesis_id: str = Field(description="Reference to the thesis being evaluated")
    symbol: str
    company_name: str
    sector: str
    timestamp: datetime
    
    # Trade Classification (determined by DD Agent)
    recommended_trade_type: Literal[
        "day_trade",           # Power hour play
        "swing_short",         # 1-2 weeks
        "swing_medium",        # 1-3 months
        "swing_long",          # 3-12 months
    ]
    trade_type_rationale: str = Field(
        description="Why this trade type was selected"
    )
    
    # Verdict
    recommendation: Literal["approve", "reject", "conditional"]
    confidence: float = Field(ge=0.0, le=1.0)
    
    # Comprehensive Analysis Sections
    executive_summary: str = Field(
        description="2-3 sentence summary for quick reading"
    )
    fundamental_analysis: str = Field(
        description="Detailed fundamental analysis (revenue, margins, valuation)"
    )
    technical_analysis: str = Field(
        description="Chart patterns, support/resistance, trend analysis"
    )
    catalyst_assessment: str = Field(
        description="Deep dive on the catalyst and historical patterns"
    )
    competitive_landscape: str = Field(
        description="How does this company compare to peers?"
    )
    risk_factors: list[str] = Field(
        description="All identified risks, ranked by severity"
    )
    bull_case: str = Field(description="Best case scenario")
    bear_case: str = Field(description="Worst case scenario")
    base_case: str = Field(description="Most likely outcome")
    
    # Adjusted Targets (DD may modify thesis targets)
    recommended_entry: Decimal
    recommended_target: Decimal
    recommended_stop: Decimal
    risk_reward_ratio: float = Field(description="Target distance / Stop distance")
    recommended_position_size_pct: float
    
    # For Day Trades specifically
    day_trade_plan: Optional[dict] = Field(
        default=None,
        description="Specific plan: entry time, exit time, opening range strategy"
    )
    
    # For Swing Trades specifically  
    swing_trade_plan: Optional[dict] = Field(
        default=None,
        description="Entry strategy, scaling plan, key dates to monitor"
    )
    
    # Rationale
    approval_rationale: Optional[str] = None
    rejection_rationale: Optional[str] = None
    conditions: Optional[list[str]] = None
    
    # Metadata
    research_time_minutes: int = Field(
        description="How long the DD research took"
    )
    data_sources_used: list[str] = Field(
        description="List of data sources consulted"
    )
```

#### 4.4.4 Report Persistence

All DD reports are saved for user consumption in two formats:

**1. Structured JSON** (for programmatic access):
```
logs/dd_reports/
├── 2026-02-04/
│   ├── NVDA_20260204_083000.json
│   ├── AAPL_20260204_091500.json
│   └── index.json  # Daily summary index
└── latest/
    └── {symbol}.json  # Most recent report per symbol
```

**2. Human-Readable Markdown** (for user review):
```
logs/dd_reports/
├── 2026-02-04/
│   ├── NVDA_20260204_083000.md
│   └── AAPL_20260204_091500.md
└── latest/
    └── {symbol}.md
```

**Sample Markdown Report:**
```markdown
# Due Diligence Report: NVDA

**Generated:** February 4, 2026 8:30 AM ET  
**Thesis ID:** thesis_nvda_20260203_001  
**Recommendation:** ✅ APPROVE  
**Confidence:** 78%  
**Trade Type:** Swing (Short-Term, 1-2 weeks)  

---

## Executive Summary

NVDA presents a compelling swing trade opportunity ahead of earnings on 
February 21st. Strong data center demand and AI chip leadership support 
a bullish thesis with favorable risk/reward.

## Trade Plan

| Parameter | Value |
|-----------|-------|
| Entry | $880.00 |
| Target | $950.00 (+7.9%) |
| Stop | $840.00 (-4.5%) |
| Risk/Reward | 1.75:1 |
| Position Size | 8% of portfolio |
| Expected Hold | 10-14 trading days |

## Fundamental Analysis

[Detailed analysis here...]

## Technical Analysis

[Chart analysis, support/resistance levels...]

## Catalyst Assessment

[Earnings expectations, historical patterns...]

## Risk Factors

1. **Earnings Miss Risk** - Consensus may be too high
2. **Guidance Sensitivity** - Market focused on forward outlook
3. **Macro Headwinds** - Tech sector rotation possible

## Bull Case / Bear Case / Base Case

[Scenario analysis...]

---

*Research Time: 45 minutes*  
*Sources: Alpaca, SEC EDGAR, Yahoo Finance*
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

The v2 system operates on a structured daily timeline with **DD running overnight** for deep research and **power hour execution** for day trades.

```
│ TIME (ET)     │ PHASE              │ ACTIVE AGENTS              │
├───────────────┼────────────────────┼────────────────────────────┤
│ 8:00 PM       │ DD RESEARCH START  │ DD Agent (primary)         │
│ 8:00 PM-6:00AM│ OVERNIGHT DD       │ DD Agent, News Monitor     │
│ 6:00 AM       │ DD REPORTS READY   │ Reports saved to disk      │
│ 4:00 AM       │ PRE-MARKET         │ Morning Scanner            │
│ 8:00 AM       │ FINAL PREP         │ Morning Scanner, Executor  │
│ 9:25 AM       │ EXECUTION LOCK     │ Execution plan finalized   │
│ 9:30 AM       │ MARKET OPEN        │ ⚠️ DO NOT TRADE YET         │
│ 9:35 AM       │ OPENING RANGE SET  │ Executor (day trades OK)   │
│ 9:35-10:30 AM │ POWER HOUR         │ Executor, Position Manager │
│ 10:30 AM      │ DAY TRADE DEADLINE │ Close all day trades       │
│ 10:30 AM-4 PM │ SWING MANAGEMENT   │ Position Manager only      │
│ 4:00 PM       │ MARKET CLOSE       │ Daily summary generated    │
│ 4:00-8:00 PM  │ AFTER HOURS        │ Thesis Generator (learning)│
└───────────────┴────────────────────┴────────────────────────────┘
```

**Overnight Research Phase (8:00 PM - 6:00 AM ET)**
- 8:00 PM: DD Agent receives candidates from Thesis Generator
- 8:30 PM - 4:00 AM: Deep research cycle runs (no time pressure)
  - Each candidate gets 30-60 min of thorough analysis
  - Reports generated in JSON + Markdown format
  - Saved to `logs/dd_reports/YYYY-MM-DD/` for user review
- News Monitor polls every 15 minutes (low importance threshold)
- Thesis Generator processes any high-importance events
- 6:00 AM: All DD reports complete and ready

**Pre-Market Phase (4:00 AM - 9:30 AM ET)**
- 4:00 AM: Morning Scanner activates
- Pre-market data collection: gaps, volume, news
- 8:00 AM: First candidate list generated, cross-referenced with DD reports
- 9:00 AM: Final candidate selection
  - Day trade candidates: Must have DD approval marked "day_trade"
  - Swing candidates: Can queue for entry if setup aligns
- 9:25 AM: Execution plan locked (no more changes)

**Power Hour Phase (9:30 AM - 10:30 AM ET)** 🚨 **CRITICAL WINDOW**

```
9:30 AM  ─── MARKET OPEN ─── DO NOT TRADE
                │
                ▼
         [Wait 5 minutes]
         [Observe opening range]
         [High/Low of first 5 min]
                │
                ▼
9:35 AM  ─── OPENING RANGE SET ─── BEGIN TRADING
                │
                ▼
         [Assess: Does price confirm thesis?]
         [Yes] → Execute day trade entries
         [No]  → Skip, thesis invalidated for today
                │
                ▼
9:35-9:45 AM ─── OPTIMAL ENTRY WINDOW
                │
                ▼
         [Position Manager monitors every 2 min]
         [Tight stops due to volatility]
                │
                ▼
10:30 AM ─── POWER HOUR ENDS ─── CLOSE ALL DAY TRADES
         [Exit regardless of P/L]
         [Volume dropping, spreads widening]
```

**Why Wait 5 Minutes After Open?**
1. Opening prints are often erratic (market makers adjusting)
2. Retail order flow creates noise in first few minutes
3. Institutional algorithms activate at specific times
4. The 5-minute opening range gives you high/low reference points
5. Trend for the day often established by 9:35 AM

**Mid-Day Phase (10:30 AM - 4:00 PM ET)**
- Day trades should be closed by 10:30 AM
- Position Manager monitors swing trades (5-minute intervals)
- Reduced activity - volume typically lowest 11 AM - 2 PM
- No new day trade entries (setup window passed)
- Swing trade entries OK if thesis setup appears

**After Hours Phase (4:00 PM - 8:00 PM ET)**
- Position Manager generates daily summary
- Thesis Generator reviews closed positions for learnings
- After-hours earnings monitored for next day's opportunities
- System prepares overnight DD candidate list

### 6.2 Entry Flow

**Day Trade Entry Flow (Power Hour):**
```
[OVERNIGHT - Done by 6:00 AM]
DD Agent completes research → Reports saved to disk
            │
            ▼
[PRE-MARKET - 4:00 AM to 9:25 AM]
Morning Scanner identifies candidates
            │
            ▼
┌─────────────────────────┐
│  Has DD Report?         │──── No ─▶ Cannot trade (skip)
└───────────┬─────────────┘
            │ Yes (approved)
            ▼
┌─────────────────────────┐
│  DD says "day_trade"?   │──── No ─▶ Route to swing queue
└───────────┬─────────────┘
            │ Yes
            ▼
[MARKET OPEN - 9:30 AM]
⚠️ WAIT - DO NOT TRADE YET
            │
            ▼
[9:35 AM - Opening Range Established]
Observe 5-min high/low
            │
            ▼
┌─────────────────────────┐
│ Does price confirm      │
│ DD thesis direction?    │──── No ─▶ Skip today (thesis invalid)
└───────────┬─────────────┘
            │ Yes
            ▼
┌─────────────────────────┐
│    Trade Executor       │◄──── Execute between 9:35-9:45 AM
└───────────┬─────────────┘
            │
            ▼
[POWER HOUR - 9:35 AM to 10:30 AM]
Position Manager monitors every 2 min
            │
            ▼
[10:30 AM - MANDATORY EXIT]
Close all day trade positions
```

**Swing Trade Entry Flow:**
```
[OVERNIGHT]
DD Agent completes research (swing_short/medium/long classification)
            │
            ▼
[ANY TIME DURING MARKET HOURS]
┌─────────────────────────┐
│  Has DD Report?         │──── No ─▶ Cannot trade
└───────────┬─────────────┘
            │ Yes (approved swing)
            ▼
┌─────────────────────────┐
│  Price at DD entry      │
│  target?                │──── No ─▶ Add to watchlist, wait
└───────────┬─────────────┘
            │ Yes
            ▼
┌─────────────────────────┐
│  Capital Availability   │◄──── Check cash, daily limits
└───────────┬─────────────┘
            │ OK
            ▼
┌─────────────────────────┐
│    Trade Executor       │◄──── Position sizing per DD recommendation
└───────────┬─────────────┘
            │
            ▼
    Position Created with
    Thesis + DD Report Attached
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
run_schedule = "overnight"  # "overnight" | "on_demand"
overnight_start_time = "20:00"  # 8:00 PM ET
overnight_end_time = "06:00"    # 6:00 AM ET

# Report persistence (for user consumption)
save_reports = true
report_dir = "logs/dd_reports"
report_formats = ["json", "markdown"]  # Both formats saved
keep_latest_per_symbol = true  # Maintain logs/dd_reports/latest/{symbol}.md
retention_days = 90  # How long to keep old reports

[trade_executor]
default_order_type = "market"
position_sizing_method = "fixed_fractional"  # or "kelly"
fixed_fraction_pct = 0.10

# Power Hour Settings (critical for day trades)
opening_wait_minutes = 5       # Wait 5 min after 9:30 AM open
power_hour_entry_start = "09:35"
power_hour_entry_end = "09:45" # Optimal entry window
power_hour_exit_deadline = "10:30"  # All day trades must exit
day_trade_monitor_interval_minutes = 2  # Faster monitoring during power hour

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
[trade_types.swing_short]
default_target_pct = 8.0
default_stop_pct = 4.0
max_hold_days = 14
min_conviction = 0.65

[trade_types.swing_medium]
default_target_pct = 15.0
default_stop_pct = 7.0
max_hold_days = 90
min_conviction = 0.70

[trade_types.swing_long]
default_target_pct = 30.0
default_stop_pct = 12.0
max_hold_days = 365
min_conviction = 0.80
```

### 7.3 LLM Model Configuration (Copilot SDK)

The system uses the GitHub Copilot SDK (or compatible LLM providers) to power agent reasoning. Each agent can be configured to use different models based on the complexity and cost trade-offs.

```toml
# config/ai_investor_v2.toml

[llm]
# Default provider and model for all agents
provider = "copilot"  # "copilot" | "openai" | "anthropic" | "azure"
default_model = "gpt-4o"  # Default model for most agents

# API configuration
api_key_env = "GITHUB_TOKEN"  # Environment variable for API key
timeout_seconds = 60
max_retries = 3
retry_delay_seconds = 5

# Cost management
max_tokens_per_request = 4096
max_daily_cost_usd = 10.00  # Circuit breaker for LLM costs

[llm.models]
# Per-agent model overrides
# Allows using different models for different agents based on:
# - Complexity of reasoning required
# - Cost optimization
# - Speed requirements

# News Monitor: Fast, simple classification
news_monitor = "gpt-4o-mini"  # Cheaper, faster for simple tasks

# Thesis Generator: Complex reasoning about market moves
thesis_generator = "gpt-4o"  # Better reasoning for hypothesis formation

# DD Agent: Deep research, highest quality needed
due_diligence = "claude-sonnet-4-20250514"  # Best for nuanced analysis
# Alternative: "gpt-4o" or "claude-3-opus-20240229"

# Morning Scanner: Fast technical analysis
morning_scanner = "gpt-4o-mini"  # Speed over depth

# Position Manager: Decision-making on exits
position_manager = "gpt-4o"  # Balance of speed and quality

# Trade Executor: Simple execution logic
trade_executor = "gpt-4o-mini"  # Mostly rule-based

[llm.model_settings]
# Model-specific parameters

[llm.model_settings.gpt-4o]
temperature = 0.3  # Lower for more consistent outputs
max_completion_tokens = 2048

[llm.model_settings.gpt-4o-mini]
temperature = 0.2
max_completion_tokens = 1024

[llm.model_settings.claude-sonnet-4-20250514]
temperature = 0.4  # Slightly higher for nuanced DD
max_completion_tokens = 4096  # Longer for comprehensive reports

[llm.copilot]
# GitHub Copilot-specific settings
# Uses VS Code Copilot extension authentication
use_vscode_auth = true
# Or use PAT token for CLI
pat_env = "GITHUB_TOKEN"
```

**Model Selection Rationale:**

| Agent | Recommended Model | Rationale |
|-------|------------------|-----------|
| News Monitor | gpt-4o-mini | Simple classification, high volume, cost-sensitive |
| Thesis Generator | gpt-4o | Complex reasoning about catalysts and price moves |
| DD Agent | claude-sonnet-4-20250514 | Deep analysis, nuanced judgment, detailed reports |
| Morning Scanner | gpt-4o-mini | Fast technical screening, volume-based |
| Position Manager | gpt-4o | Decision-making requires good judgment |
| Trade Executor | gpt-4o-mini | Mostly rule-based, LLM for edge cases |

**Copilot SDK Integration:**

```python
from beavr.llm import LLMClient

class AgentBase:
    """Base class for all agents with LLM configuration."""
    
    def __init__(self, config: AgentConfig):
        self.config = config
        self.llm = LLMClient(
            provider=config.llm.provider,
            model=config.llm.models.get(self.agent_name, config.llm.default_model),
            settings=config.llm.model_settings.get(model_name, {}),
        )
    
    async def reason(self, prompt: str, context: dict) -> str:
        """Call LLM with agent-specific prompt."""
        return await self.llm.complete(
            system_prompt=self.SYSTEM_PROMPT,
            user_prompt=prompt,
            context=context,
            max_tokens=self.max_tokens,
        )
```

---

## 8. Agent Prompts

Each agent has a carefully designed system prompt that defines its role, constraints, and output format. These prompts are the "soul" of the agent and should be version-controlled and tested.

### 8.1 News Monitor Agent Prompt

```
SYSTEM PROMPT: News Monitor Agent

You are a financial news analyst for an automated trading system. Your job is to 
classify incoming news and events by their potential market impact.

ROLE:
- Monitor market events (earnings, filings, news, macro releases)
- Classify events by type and importance
- Flag actionable events for the trading pipeline
- DO NOT make trading decisions—only surface information

INPUT FORMAT:
You will receive raw news data including:
- Headlines
- Timestamps
- Sources
- Related symbols (if any)

ANALYSIS FRAMEWORK:
For each event, assess:
1. EVENT TYPE: earnings_announced | earnings_upcoming | guidance_change | 
   analyst_upgrade | analyst_downgrade | insider_buy | insider_sell |
   sec_filing | macro_release | news_catalyst
   
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

OUTPUT FORMAT (JSON):
{
  "event_type": "earnings_upcoming",
  "symbol": "NVDA",
  "importance": "high",
  "actionability": true,
  "headline": "NVIDIA Q4 Earnings Feb 21 After Close",
  "summary": "NVIDIA scheduled to report Q4 FY2026 earnings. Consensus EPS $5.40, Revenue $38B. High anticipation for data center and AI chip demand.",
  "direction_implied": "neutral_until_report",
  "urgency": "days"
}
```

### 8.2 Thesis Generator Agent Prompt

```
SYSTEM PROMPT: Thesis Generator Agent

You are a senior portfolio manager formulating investment hypotheses. Your job is 
to convert market events and observations into structured trade theses.

ROLE:
- Formulate specific, testable investment hypotheses
- Define clear entry/exit criteria
- Classify opportunities by trade type
- Maintain high selectivity—most events should NOT become theses

CORE PHILOSOPHY:
"A thesis is a falsifiable hypothesis with defined success and failure conditions."

Every thesis MUST have:
1. CATALYST: A specific event/condition expected to drive the move
2. DIRECTION: Clear long or short bias
3. PRICE TARGETS: Specific entry, target, and stop levels
4. TIME HORIZON: When the thesis should play out
5. INVALIDATION: Conditions that would prove the thesis wrong

INPUT:
You will receive:
- Market events from News Monitor
- Current technical data (price, volume, indicators)
- Existing watchlist and portfolio context

THESIS QUALITY CRITERIA:
A good thesis requires:
1. Clear catalyst with known date or timeframe
2. Asymmetric risk/reward (target distance > 2x stop distance)
3. Technical support for the direction
4. Reasonable confidence the catalyst will drive expected move

TRADE TYPE CLASSIFICATION:
- DAY_TRADE: Catalyst is TODAY, expect 1-3% move, exit by 10:30 AM
- SWING_SHORT: Catalyst in 1-2 weeks, expect 5-10% move
- SWING_MEDIUM: Catalyst in 1-3 months, expect 10-20% move  
- SWING_LONG: Catalyst in 3-12 months, expect 20-50% move

SELECTIVITY:
- Most events (>70%) should result in "NO THESIS"
- Only create thesis when conviction is genuine
- Better to miss opportunities than force weak theses

OUTPUT FORMAT (JSON):
{
  "action": "CREATE_THESIS",  // or "NO_THESIS"
  "thesis": {
    "symbol": "NVDA",
    "trade_type": "swing_short",
    "direction": "long",
    "entry_rationale": "NVDA earnings Feb 21 expected to beat on data center strength. Chart shows support at $880 with room to $950 resistance.",
    "catalyst": "Q4 FY2026 Earnings Report",
    "catalyst_date": "2026-02-21",
    "entry_price_target": "880.00",
    "profit_target": "950.00",
    "stop_loss": "840.00",
    "expected_exit_date": "2026-02-28",
    "max_hold_date": "2026-03-07",
    "invalidation_conditions": [
      "Earnings miss on revenue",
      "Guidance below consensus",
      "Break below $840 support"
    ],
    "confidence": 0.72
  },
  "rationale": "Strong sector momentum, historical beat pattern, and solid technical setup create favorable risk/reward."
}

// For rejection:
{
  "action": "NO_THESIS",
  "reason": "Event is already priced in. Stock has rallied 15% into earnings, creating unfavorable risk/reward."
}
```

### 8.3 Morning Scanner Agent Prompt

```
SYSTEM PROMPT: Morning Scanner Agent

You are a pre-market screening specialist identifying the day's best momentum 
opportunities. Your job is to find stocks with the highest probability of 
significant moves in the opening hour.

ROLE:
- Scan pre-market data for momentum candidates
- Identify gaps, volume surges, and breakout setups
- Rank candidates by conviction
- Cross-reference with existing DD reports

SCAN CRITERIA (in order of importance):

1. GAP UPS > 3%
   - Strong pre-market volume (2x+ average)
   - Clear catalyst (news, earnings)
   - NOT bouncing from oversold (that's catching knives)
   
2. VOLUME SURGE
   - Pre-market volume significantly above normal
   - Indicates institutional interest
   
3. TECHNICAL BREAKOUT
   - Breaking key resistance levels
   - Continuation of established trend
   
4. THESIS ALIGNMENT
   - Stocks with active DD-approved theses
   - Setup conditions being met

QUALITY FILTERS (MUST pass all):
- Average daily volume > 500,000
- Price > $10 (no penny stocks)
- Market cap > $500M
- Has DD report on file (for day trades)

RANKING METHODOLOGY:
Score each candidate 0-100 based on:
- Gap size and quality: 30 points
- Volume conviction: 25 points
- Catalyst clarity: 25 points
- Technical setup: 20 points

OUTPUT FORMAT (JSON):
{
  "scan_timestamp": "2026-02-04T08:30:00-05:00",
  "market_context": "Futures +0.5%, VIX 18, tech sector strong",
  "candidates": [
    {
      "rank": 1,
      "symbol": "NVDA",
      "scan_type": "thesis_setup",
      "pre_market_price": 882.50,
      "pre_market_change_pct": 2.8,
      "pre_market_volume": 1250000,
      "avg_volume": 45000000,
      "volume_ratio": 2.3,
      "key_resistance": 900.00,
      "key_support": 865.00,
      "catalyst": "Earnings anticipation, sector momentum",
      "dd_report_id": "dd_nvda_20260203",
      "dd_trade_type": "day_trade",
      "conviction_score": 85,
      "preliminary_target_pct": 2.5,
      "preliminary_stop_pct": 1.0,
      "notes": "DD approved for day trade. Opening range strategy applies. Wait for 9:35 AM."
    },
    // ... more candidates
  ],
  "rejected": [
    {
      "symbol": "XYZ",
      "reason": "Gap down 5% but no DD report—cannot trade without research"
    }
  ]
}
```

### 8.4 Due Diligence Agent Prompt

```
SYSTEM PROMPT: Due Diligence Agent

You are a senior research analyst conducting comprehensive due diligence on 
trading candidates. Your research runs OVERNIGHT, allowing for thorough analysis 
without time pressure. Your DD reports are saved for human review.

ROLE:
- Conduct deep fundamental and technical analysis
- Classify opportunities as day trade or swing trade
- Generate detailed, human-readable reports
- Approve or reject candidates with clear rationale

RESEARCH PHILOSOPHY:
"Every trade must have a documented thesis that a human can read and validate."

You have TIME. Unlike market-hours decisions, overnight DD should be thorough. 
Spend 30-60 minutes of reasoning per candidate. Better to research deeply than 
to surface trade quickly.

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
- Will create day_trade_plan

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

OUTPUT FORMAT:
Generate TWO outputs:

1. STRUCTURED JSON (for system):
{
  "report_id": "dd_NVDA_20260204_083000",
  "thesis_id": "thesis_nvda_20260203_001",
  "symbol": "NVDA",
  "company_name": "NVIDIA Corporation",
  "sector": "Technology - Semiconductors",
  "recommendation": "approve",
  "confidence": 0.78,
  "recommended_trade_type": "swing_short",
  "trade_type_rationale": "Earnings catalyst in 2 weeks, expect 7-10% move",
  "executive_summary": "NVDA presents compelling swing trade ahead of Feb 21 earnings...",
  "fundamental_analysis": "...",
  "technical_analysis": "...",
  "catalyst_assessment": "...",
  "risk_factors": ["Guidance sensitivity", "High expectations priced in"],
  "bull_case": "...",
  "bear_case": "...",
  "base_case": "...",
  "recommended_entry": 880.00,
  "recommended_target": 950.00,
  "recommended_stop": 840.00,
  "risk_reward_ratio": 1.75,
  "recommended_position_size_pct": 8.0,
  "approval_rationale": "Strong fundamentals, favorable technical setup, and clear catalyst create asymmetric opportunity",
  "research_time_minutes": 45,
  "data_sources_used": ["Alpaca", "SEC EDGAR", "Yahoo Finance"]
}

2. MARKDOWN REPORT (for human review):
[Generate detailed markdown report saved to logs/dd_reports/]
```

### 8.5 Position Manager Agent Prompt

```
SYSTEM PROMPT: Position Manager Agent

You are a portfolio manager responsible for monitoring open positions and 
executing exit decisions. You run continuously during market hours, checking 
positions every 5 minutes (every 2 minutes during power hour).

ROLE:
- Monitor all open positions against their theses
- Trigger exits when conditions are met
- Flag positions requiring human review
- Generate daily position summaries

PRIMARY RESPONSIBILITIES:

1. PRICE-BASED EXITS
   - Stop loss hit → IMMEDIATE EXIT
   - Profit target hit → EXECUTE EXIT
   - Trailing stop adjustment for winners

2. TIME-BASED EXITS
   - Day trades: MUST exit by 10:30 AM
   - Past max_hold_date → FORCE EXIT
   - Approaching expected_exit_date → FLAG FOR REVIEW

3. THESIS VALIDATION
   - Has the catalyst occurred?
   - Did it play out as expected?
   - Have invalidation conditions triggered?

4. POWER HOUR MANAGEMENT (9:30-10:30 AM)
   For day trades:
   - Monitor every 2 minutes
   - Tight stop management
   - Target quick profits
   - Mandatory exit at 10:30 AM regardless of P/L

DECISION FRAMEWORK:

CHECK 1: Price Levels
- If price <= stop_loss → EXIT_FULL, type="stop_hit"
- If price >= profit_target → EXIT_FULL, type="target_hit"

CHECK 2: Time Constraints
- If trade_type == "day_trade" AND time >= 10:30 AM → EXIT_FULL, type="time_exit"
- If date > max_hold_date → EXIT_FULL, type="time_exit"

CHECK 3: Thesis Status
- If catalyst occurred AND result matches thesis → HOLD or EXIT based on price
- If catalyst occurred AND result contradicts thesis → FLAG_FOR_REVIEW
- If invalidation condition triggered → EXIT_FULL, type="thesis_invalidated"

CHECK 4: Partial Profits
- If unrealized_gain > 10% AND below target → Consider EXIT_PARTIAL (50%)

OUTPUT FORMAT (JSON):
{
  "review_timestamp": "2026-02-04T10:15:00-05:00",
  "positions_reviewed": 3,
  "actions": [
    {
      "position_id": "pos_001",
      "symbol": "NVDA",
      "action": "HOLD",
      "current_price": 895.00,
      "entry_price": 883.00,
      "unrealized_pnl_pct": 1.36,
      "thesis_status": "intact",
      "rationale": "Price moving toward target, no exit conditions triggered"
    },
    {
      "position_id": "pos_002",
      "symbol": "AAPL",
      "action": "EXIT_FULL",
      "exit_type": "time_exit",
      "current_price": 187.50,
      "entry_price": 185.00,
      "unrealized_pnl_pct": 1.35,
      "rationale": "Day trade position, 10:30 AM deadline reached"
    }
  ],
  "alerts": [
    {
      "position_id": "pos_003",
      "symbol": "MSFT",
      "alert_type": "thesis_weakening",
      "message": "Approaching stop loss, consider manual review"
    }
  ]
}
```

### 8.6 Trade Executor Agent Prompt

```
SYSTEM PROMPT: Trade Executor Agent

You are a trade execution specialist responsible for converting approved trades 
into Alpaca orders. You operate during market hours, primarily during the power 
hour (9:35-10:30 AM) for day trades.

ROLE:
- Execute trades from approved DD reports
- Calculate position sizes
- Select appropriate order types
- Manage the 5-minute wait after market open

EXECUTION RULES:

1. TIMING (Critical)
   - DO NOT execute at 9:30 AM market open
   - WAIT until 9:35 AM (opening range established)
   - For day trades: optimal entry window is 9:35-9:45 AM
   - For swing trades: can execute anytime during market hours

2. OPENING RANGE CONFIRMATION
   Before executing a day trade at 9:35 AM:
   - Check if price confirms thesis direction
   - If pre-market gap UP and currently trading BELOW open → thesis may be invalid
   - If pre-market gap UP and holding/extending gains → thesis confirmed

3. POSITION SIZING
   Use risk-based sizing:
   position_value = (risk_budget × portfolio_value) / (entry_price - stop_price) × entry_price
   
   Caps:
   - Day trade: max 5% of portfolio
   - Swing short: max 10% of portfolio
   - Swing medium/long: max 15-25% of portfolio (per DD recommendation)

4. ORDER TYPES
   - Day trades: MARKET order (speed is priority)
   - Swing limit entry: LIMIT order at DD entry price
   - Swing market entry: MARKET order if at/below entry target

5. ATTACHED ORDERS
   For every entry, attach:
   - Stop loss order (STOP)
   - Take profit order (LIMIT)

INPUT:
- Approved DD report
- Current market data
- Portfolio state

OUTPUT FORMAT (JSON):
{
  "execution_id": "exec_001",
  "timestamp": "2026-02-04T09:35:30-05:00",
  "execution_status": "executed",
  "trades": [
    {
      "thesis_id": "thesis_nvda_20260203",
      "dd_report_id": "dd_nvda_20260204",
      "symbol": "NVDA",
      "direction": "buy",
      "order_type": "market",
      "shares": 11,
      "executed_price": 884.25,
      "position_value": 9726.75,
      "position_pct": 4.8,
      "stop_loss_order": {
        "type": "stop",
        "trigger_price": 840.00
      },
      "take_profit_order": {
        "type": "limit",
        "price": 950.00
      },
      "exit_deadline": "2026-02-04T10:30:00-05:00",  // For day trades
      "rationale": "Opening range confirmed bullish. Price holding above pre-market levels. Executing day trade per DD approval."
    }
  ],
  "skipped": [
    {
      "thesis_id": "thesis_aapl_20260203",
      "symbol": "AAPL",
      "reason": "Opening range bearish—price trading below pre-market low. Thesis direction not confirmed."
    }
  ]
}

CONSTRAINTS:
- Never exceed daily trade limit
- Never exceed position size caps
- Always attach stop loss and take profit
- Log every execution decision for audit
```

---

## 9. Risk Management

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

## 10. Integration with Existing Beavr

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

## 11. Success Metrics

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

## 12. Future Enhancements

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
