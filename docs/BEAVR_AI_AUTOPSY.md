# Beavr AI Investor: System Autopsy & Reformation Plan

**Date:** March 29, 2026
**Portfolio P/L:** ~-$506 (-4.1%) across 18 positions
**Worst Losers:** FENC (-24.7%), ETSY (-13.6%), VRT (-8.4%), DASH (-7.3%)
**Best Winners:** COGT (+4.7%), FDP (+2.0%), LW (+1.6%), AMD (+1.2%)

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Portfolio Diagnosis](#2-portfolio-diagnosis)
3. [Core Systemic Flaws](#3-core-systemic-flaws)
4. [Lessons from Institutional Systems](#4-lessons-from-institutional-systems)
5. [Proposed Architecture: Beavr v3](#5-proposed-architecture-beavr-v3)
6. [Implementation Roadmap](#6-implementation-roadmap)
7. [Appendix: Position-by-Position Analysis](#7-appendix-position-by-position-analysis)
8. [Reviewer's Critical Assessment](#8-reviewers-critical-assessment)
9. [Additional Issues](#9-additional-issues)
10. [Market Briefing System Design](#10-market-briefing-system-design)

---

## 1. Executive Summary

The Beavr AI auto investor is underperforming because of **six fundamental design flaws** that compound each other. The system was well-architected in theory (thesis-driven, DD-gated, multi-agent) but the implementation has critical gaps in **position management, risk control, market regime awareness, and exit discipline**.

The portfolio tells the story: 18 positions, 12 underwater, only 6 positive—and the winners are marginal (+1-5%) while the losers are painful (-7% to -25%). This is the signature of a system that **enters aggressively but manages passively**.

**The core problem**: Beavr is a research machine with no trading discipline. It generates theses, runs DD, enters positions—then largely abandons them. It has no effective stop-loss execution, no trailing stops, no sector/correlation awareness, no position review cycle, and no mechanism to cut losers early.

**The hidden cost problem**: The system also has no quality screening before stocks enter the LLM pipeline. It ran DD on 227 stocks, approved only 25 (11%), and 42 of those were sub-$10 penny/micro-cap names. The DD agent is essentially an expensive filter doing work that a $0 screener should handle.

---

## 2. Portfolio Diagnosis

### 2.1 The Numbers Tell the Story

| Metric | Value | Assessment |
|--------|-------|------------|
| Total Positions | 18 | **Severe over-diversification for ~$13K portfolio** |
| Avg Position Size | $724 | Too small to be meaningful |
| Win Rate | 33% (6/18) | Below the 45% target |
| Avg Winner | +1.7% | Far below 8% swing target |
| Avg Loser | -7.5% | **Exceeds 4% stop loss config** |
| Win/Loss Ratio | 0.23:1 | **Target was 1.5:1 — catastrophic** |
| Max Loss (FENC) | -24.7% | **2.5x the configured max_drawdown_pct of 10%** |
| Cash | ~$39 | **Fully deployed with no reserves** |

### 2.2 Pattern Analysis

**Every position exhibits the same failure mode:**
1. Thesis generated from news event or market mover
2. DD approved (often with reservations the system ignored)
3. Position entered at market
4. Price declines past the configured stop loss
5. **Stop loss never executed** — position held indefinitely
6. DD later runs on the same symbol and *rejects* it, noting the thesis failed
7. Position is still held

**Evidence from DD reports:**
- **DASH**: DD explicitly says "REJECT - FAILED CATALYST... price now AT THE STOP LOSS... DO NOT ENTER" — yet the position is still held at -7.3%
- **NOA**: DD says "CATASTROPHICALLY FAILED... STOP LOSS at $15.70 was OBLITERATED" — position now at -3.5% (was worse)
- **FENC**: Entered at $7.85, current $5.91 = **-24.7%** — the configured stop of 12.7% was never triggered
- **VRT**: DD says "price ALREADY EXCEEDED the profit target... should be SELLING into inclusion event" — still holding at -8.4% after the event passed
- **ETSY**: DD says "thesis dates have expired... expected exit Mar 1, max hold Mar 5 both passed" — still holding 24 days past max hold
- **ASND**: DD notes "thesis technical claims are WRONG... stock declined since catalyst" — still held

### 2.3 Root Cause Summary

The system **generates excellent analysis** but has **zero execution discipline**. The DD agent correctly identifies failed theses, expired holds, and blown stops — but nothing acts on this information.

---

## 3. Core Systemic Flaws

### Flaw #1: Stop Losses Are Not Enforced

**Severity: CRITICAL**

The `_monitor_positions()` method checks `pnl_pct <= -stop_pct` and calls `_close_position()`, but this logic has fundamental problems:

1. **Runs only during MARKET_HOURS and POWER_HOUR phases** — if markets gap down past the stop overnight, the check runs but may use stale `db_pos` data.

2. **Fallback to config defaults**: When `db_pos` is None (no position record), it falls back to `self.config.swing_short_stop_pct` (4%). But many positions were entered with different stop levels (FENC at 12.7%, NOA likely higher). The mismatch means some positions never trigger stops.

3. **No broker-level stop orders**: The system does NOT place OCO (One-Cancels-Other) or bracket orders at the broker. It relies entirely on polling every 5 minutes. Between polls, a stock can gap through the stop and the system misses it entirely.

4. **No gap protection**: There's no pre-market check. If FENC drops 15% pre-market, the system only notices at the next 5-minute poll during market hours.

**Evidence**: FENC is -24.7% with a configured stop of ~12.7%. DASH is -7.3% with a DD-recommended stop at $164. Neither was exited.

### Flaw #2: No Position Lifecycle Management

**Severity: CRITICAL**

The system has a `PositionManagerAgent` with sophisticated thesis validation logic, but **it is never called in the main run loop**. The v2 engine's `_monitor_positions()` only checks price levels — it never:

- Validates if the thesis is still intact
- Checks if max_hold_date has passed
- Checks if catalyst_date has come and gone
- Reviews if invalidation conditions have triggered
- Considers time-based exits

**Evidence**: ETSY's max_hold_date was March 5. It's March 29. Still holding. VRT's S&P inclusion event (the catalyst) passed on March 23. Still holding. Multiple positions have invalidated theses according to DD reports, yet none were exited.

The `PositionManagerAgent.review_position()` method exists and handles all these cases, but the orchestrator's run loop never invokes it.

### Flaw #3: Over-Diversification Destroys Returns

**Severity: HIGH**

18 positions in a ~$13K portfolio means ~$724 per position. This creates three problems:

1. **Winners can't move the needle**: COGT at +4.7% contributes only +$22 to the portfolio. Even a 10% winner on a $700 position adds just $70.

2. **Position sizes too small for effective risk management**: With tiny positions, brokerage costs and slippage eat into what little profit exists.

3. **Correlated exposure**: Several holdings overlap thematically:
   - Tech/Growth: AMD, AMZN, CRM, DASH, PINS, VRT
   - Biotech/Pharma: FENC, VRTX, COGT, ASND
   - The portfolio is essentially a bet on growth/tech + speculative biotech

**Institutional benchmark**: Concentrated hedge funds typically hold 8-15 positions. A small retail portfolio of $13K should hold **5-8 high-conviction positions** at most.

### Flaw #4: No Correlation or Sector Exposure Limits

**Severity: HIGH**

The system checks for duplicate symbols and related companies (GOOG/GOOGL) but has **zero awareness of**:

- Sector concentration (6 tech names = ~45% sector exposure)
- Factor exposure (all positions are long, growth-tilted)
- Correlation between holdings
- Beta-adjusted exposure
- Market regime alignment

When the market sells off, correlated positions all decline together. The portfolio has no defensive positioning, no hedging, and no uncorrelated sources of return.

### Flaw #5: Thesis-to-Execution Gap (The "Research-Action Disconnect")

**Severity: HIGH**

The DD agent consistently produces accurate analysis but the system ignores its findings:

1. **DD rejects a thesis, but the existing position isn't reviewed**: When DD analyzes DASH and says "REJECT — failed catalyst," a human would immediately review the held DASH position. Beavr doesn't.

2. **DD identifies stale theses but can't trigger exits**: VRT DD says "should SELL into inclusion event." ETSY DD says "thesis expired." No mechanism connects renewed DD analysis to position exit logic.

3. **The DD agent runs overnight but positions deteriorate during market hours**: By the time the DD agent identifies a problem (e.g., "ASND technicals contradict thesis claims"), the damage is already done. There's no intraday thesis validation.

4. **Conditional approvals are ignored**: DD sometimes says "CONDITIONAL — only enter if X happens." The system has no mechanism to verify condition X before executing.

### Flaw #6: Entry Timing and Price Sensitivity

**Severity: MEDIUM**

The system enters at market price using `thesis.entry_price_target` as the share calculation basis, not as a limit order:

```python
current_price = thesis.entry_price_target  # TODO: Get live price
```

This means:
- The system buys at whatever price the market gives, not the price the thesis analyzed
- If the stock has moved 5% above the DD entry target, it still buys
- No slippage protection for small/mid-cap names
- The "wait for opening range" logic exists but only for day trades

**Evidence**: Many DD reports note "current price above entry target" but the system entered anyway.

### Flaw #7: No Pre-DD Stock Screener (The Junk Funnel Problem)

**Severity: CRITICAL**

This is arguably the system's most wasteful flaw: **the research pipeline has virtually no quality gate before stocks reach DD**. The system hemorrhages LLM tokens analyzing sub-$5 penny stocks, micro-cap biotechs, and SPACs that should never be considered.

#### The Numbers

| Metric | Value |
|--------|-------|
| **Total DD reports generated** | **227** |
| **Approved** | 25 (11%) |
| **Rejected** | 178 (78%) |
| **Conditional** | 24 (10%) |
| **No fundamental/market_cap data** | 227 (100%) |
| **Sub-$10 stocks analyzed** | 42 (19%) |
| **Sub-$5 stocks analyzed** | 20 (9%) |

The system ran DD on **227 stocks** and approved only **25** — an **89% waste rate**. Nearly 1 in 5 DD reports was on a sub-$10 stock. Every single report lacked fundamental/market_cap data.

#### What Got Through to DD

Here are some of the stocks the system spent LLM tokens deeply researching:

| Symbol | Entry Price | What It Is |
|--------|-------------|------------|
| DVLT | $0.72 | Penny stock |
| BFRI | $0.82 | Penny stock, sub-$1 |
| BMEA | $0.95 | Sub-$1 biotech |
| PERF | $1.52 | Micro-cap |
| RXT | $1.55 | Micro-cap failed tech |
| ALUR | $1.60 | Sub-$2 SPAC |
| KOS | $1.70 | Micro-cap oil |
| ANIX | $2.80 | Micro-cap biotech |
| NRGV | $3.60 | Micro-cap energy |
| BFLY | $3.70 | Penny stock medical |
| DOMO | $3.50 | Failing SaaS |
| BMBL | $4.00 | Collapsed dating app |
| JBLU | $4.30 | Struggling airline |
| CHPT | $5.00 | Unprofitable EV charging |
| SNAP | $5.14 | Declining social media |
| NIO | $5.30 | Chinese EV (delisting risk) |

The DD agent was asked to deeply research these names — spending ~50 seconds of Claude Sonnet time per report — only to reject them. **These stocks should never have entered the pipeline.**

#### Where the Screening Breaks Down

The quality filter code exists in `cli/ai.py` (`is_quality_stock()` function and `QUALITY_UNIVERSE` whitelist), but it is **almost completely disconnected from the v2 engine's research pipeline**:

```
Market Movers API (Alpaca)
    │
    ├─── NO quality filter applied
    │
    ▼
_fetch_market_mover_events() converts ALL movers to MarketEvents
    │
    ├─── NO price/volume/market_cap check
    │
    ▼
_build_research_universe() collects movers + open positions + theses
    │
    ├─── Only limit: max 25 symbols (truncation, not filtering)
    │
    ▼
News fetched for ALL symbols in universe
    │
    ├─── NO quality pre-filter
    │
    ▼
News classified by LLM (News Monitor) — wastes tokens on junk
    │
    ├─── Only filter: MEDIUM+ importance
    │
    ▼
Thesis Generator creates thesis if confidence >= 60%
    │
    ├─── LLM can create thesis for any stock, no quality gate
    │
    ▼
DD Agent runs deep analysis (50s of Claude time per stock)
    │
    ├─── 89% REJECTION RATE
    │
    ▼
Only QUALITY_UNIVERSE is used once: morning_scanner seed list (optional path)
```

The `is_quality_stock()` function is only called in `get_quality_opportunities()` for the CLI analyze command — **not in the autonomous orchestrator pipeline**.

#### The Cost

- **227 DD reports × ~50s LLM time = ~190 minutes of Claude Sonnet compute** (wasted on 89% rejections)
- Each DD call uses ~4096 tokens of output → **~930K output tokens on DD alone**
- The News Monitor and Thesis Generator also used tokens classifying junk
- Conservative estimate: **60-70% of all LLM spend was on stocks that should have been filtered pre-pipeline**

#### What Should Happen Instead

A **hard pre-screener** before ANY symbol enters the research pipeline:

```python
# BEFORE any symbol enters the research universe:
def passes_quality_gate(symbol: str, price: float, avg_volume: int, market_cap: float) -> bool:
    """Hard quality gate. Stocks that fail never touch the LLM."""
    if price < 15:          return False  # No micro-cap / penny
    if price > 800:         return False  # Position size impractical  
    if avg_volume < 500_000: return False  # Illiquid
    if market_cap < 2_000_000_000: return False  # Sub-$2B = too speculative
    if len(symbol) > 4:     return False  # Warrants, units
    return True
```

This single gate would have eliminated ~80 of the 227 DD candidates, saving the majority of LLM costs while improving the quality of what DD actually reviews.

---

## 4. Lessons from Institutional Systems

### 4.1 How Professional Hedge Funds Operate

The following principles are extracted from documented practices at Renaissance Technologies, Two Sigma, Bridgewater, Citadel, and AQR.

#### Principle 1: Position Sizing is the #1 Risk Tool

Professional funds size positions based on:
- **Kelly Criterion** (optimal fraction of bankroll): `f* = (bp - q) / b` where b=odds, p=win prob, q=loss prob
- **Volatility targeting**: Each position targets the same dollar volatility. A volatile biotech gets a smaller position than a stable utility.
- **Risk parity**: Allocate risk, not capital. A $500 position in a 50% ATR biotech carries more risk than a $2000 position in a 5% ATR blue chip.

**What Beavr should do**: Size positions inversely proportional to their ATR/volatility. High-ATR stocks like FENC should get tiny allocations; stable names like FDX get larger ones.

#### Principle 2: Hard Stop Losses at the Broker Level

Every institutional system places stop-loss orders **at the exchange/broker level**, not in software:

- **Bracket orders** (entry + stop + target submitted simultaneously)
- **Trailing stops** that adjust automatically as price moves favorably
- **Time stops** handled by the execution management system, not the strategy

Software-based stops are unreliable — the system could crash, the API could fail, or a gap could blow through the stop between polling intervals.

#### Principle 3: Concentrated, High-Conviction Portfolios

- **Tiger Global**: 10-30 positions for multi-billion fund
- **Berkshire Hathaway**: Top 5 positions = 75% of portfolio
- **Stanley Druckenmiller**: Maximum conviction = maximum position size

For a retail portfolio: **fewer positions, larger sizes, higher conviction**. Every additional position dilutes attention and capital.

#### Principle 4: Systematic Exit Discipline

Professional funds have mechanical exit rules that cannot be overridden:

- **Time-based exits**: If thesis hasn't played out in N days, exit regardless
- **Trailing stops**: Lock in profits as price advances
- **Rebalancing**: Trim winners that exceed target allocation, cut losers that fall below threshold
- **Regime-based exits**: When market regime changes (bull→bear), reduce net exposure systematically

#### Principle 5: Portfolio-Level Risk Management

Individual position stops aren't sufficient. Portfolio-level controls include:

- **Maximum sector exposure**: No more than 25% in one sector
- **Maximum correlation**: New position must have <0.7 correlation with existing book
- **Factor balance**: Long/short exposure to factors (momentum, value, quality)
- **Drawdown-based de-risking**: At 5% DD, reduce 30% exposure. At 10%, reduce 60%.

#### Principle 6: Mean Reversion vs. Momentum — Pick One

The Beavr system tries to do both and does neither well:
- Swing Trader prompt says "RSI < 30, buy the dip" (mean reversion)
- Morning Scanner says "buy gap-ups and breakouts" (momentum)

These are **opposing philosophies**. Professional funds specialize:
- **Momentum funds** buy strength, use tight trailing stops, have high turnover
- **Mean reversion funds** buy weakness, use wider stops, wait longer for payoff

Mixing them without separate risk buckets creates confusion in the LLM reasoning.

---

## 5. Proposed Architecture: Beavr v3

### 5.1 Design Philosophy Shift

**From:** "Research everything, buy what DD approves, hope stops work"
**To:** "Research selectively, enter precisely, manage actively, exit mechanically"

### 5.2 Core Reforms

#### Reform 1: Broker-Level Stop Losses (Zero Tolerance)

```
RULE: Every position MUST have a bracket order (stop + target) at the 
broker level within 60 seconds of entry confirmation. No exceptions.
```

Implementation:
- Use Alpaca's bracket/OCO order types
- Entry order = market buy + attached stop-loss + attached take-profit
- Trailing stop activates after position reaches +3%
- The orchestrator VERIFIES bracket orders exist for every position at startup

#### Reform 2: Active Position Manager (The "Exit Machine")

Replace the simple PnL-check in `_monitor_positions()` with the full `PositionManagerAgent` loop:

```
Every 5 minutes during market hours:
  For each open position:
    1. Check broker-level stop/target (verify they exist)
    2. Check time limits:
       - Day trade past 10:30 AM? → IMMEDIATE EXIT
       - Past max_hold_date? → IMMEDIATE EXIT
       - Past expected_exit_date? → REVIEW (LLM decides)
    3. Check thesis validity:
       - Has catalyst date passed without expected move? → FLAG
       - Have invalidation conditions triggered? → EXIT
    4. Check partial profit opportunities:
       - Position up >8% but below target? → Take 50% off
    5. Trailing stop management:
       - Update trailing stop to max(entry, highest_close - 2*ATR)
```

#### Reform 3: Concentrated Portfolio (Max 8 Positions)

```
HARD LIMITS:
- Maximum 8 simultaneous positions
- Minimum position size: 8% of portfolio ($1,040 on $13K)
- Maximum position size: 20% of portfolio
- New position ONLY if an existing position is closed or portfolio < 8
```

This means:
- Each position is ~$1,300-$2,600 (meaningful)
- Winners actually move the portfolio
- The system must be **selective**, not spray-and-pray

#### Reform 4: Sector and Correlation Limits

```
SECTOR LIMITS:
- Maximum 3 positions in same sector
- Maximum 40% capital in same sector
- No position if correlation > 0.75 with existing holding

FACTOR BALANCE:
- At least 1 defensive position (low-beta, dividend)
- Maximum 60% in high-beta (>1.2) names
```

Implementation: Use simple sector classification from broker data. Compute rolling 30-day correlation matrix for held symbols.

#### Reform 5: Momentum-First Strategy (Abandon Mean Reversion)

For a small retail account with swing/position trades, **momentum systematically outperforms mean reversion**. Academic evidence (Jegadeesh & Titman, 1993; Asness et al., 2013) shows momentum is the strongest anomaly across all asset classes.

**New strategy: Trend-Following with Quality Filter**

```
BUY SIGNALS (Momentum):
✅ Price > 20-day SMA AND > 50-day SMA (confirmed uptrend)
✅ RSI between 50-70 (strong but not exhausted)
✅ Volume expanding on up days
✅ Recent catalyst with positive price reaction
✅ Sector showing relative strength

DO NOT BUY (Avoid These):
❌ RSI < 40 (downtrend, falling knife)
❌ Price below 50-day SMA (broken trend)  
❌ "Good news, bad price action" (market knows something)
❌ Low volume breakout (no institutional support)
❌ Stock down >15% in last month (momentum trap)
```

The key insight: **buy strength, not weakness**. A stock that's already going up is more likely to continue going up than a stock that's falling is to bounce.

#### Reform 6: Entry Precision

```
ENTRY RULES:
1. LIMIT ORDERS ONLY for swing trades (at or below DD entry target)
2. Order expires end-of-day if not filled
3. If stock moves >3% above DD entry target → SKIP (opportunity missed)
4. Wait for confirmation: 
   - Opening range must confirm direction
   - Volume must confirm interest (>1.2x average)
```

No more market orders that pay whatever the market asks. Use limit orders to ensure entry at the analyzed price level.

#### Reform 7: DD-to-Position Feedback Loop

```
When DD agent runs on a HELD symbol and finds:
- Thesis "CATASTROPHICALLY FAILED" → QUEUE IMMEDIATE EXIT
- "Thesis expired" or "past max hold" → QUEUE EXIT
- "Sell into event" → QUEUE EXIT  
- "Technical breakdown" → TIGHTEN STOP to -3%

This creates a closed loop where research drives exits, not just entries.
```

### 5.3 New Decision Flow

```
┌────────────────────────────────────────────────────────────────┐
│                    BEAVR v3 DECISION FLOW                      │
│                                                                │
│  RESEARCH (24/7)                                               │
│  ├─ News Monitor → Events                                     │
│  ├─ Thesis Generator → Theses (selectivity > 80% rejection)   │
│  └─ DD Agent → Approved Theses                                │
│       ├─ Also reviews HELD positions nightly                   │
│       └─ Can trigger exits, not just entries                   │
│                                                                │
│  PORTFOLIO CHECK (Before any new entry)                        │
│  ├─ Current positions < 8?                                     │
│  ├─ Sector limit not exceeded?                                 │
│  ├─ Correlation check passed?                                  │
│  ├─ Position size meets minimum 8% threshold?                  │
│  └─ Enough cash (including 10% reserve)?                       │
│                                                                │
│  ENTRY (Market Hours)                                          │
│  ├─ LIMIT ORDER at or below DD entry target                   │
│  ├─ Bracket: STOP + TARGET attached at broker level            │
│  └─ Verify bracket exists before moving on                     │
│                                                                │
│  POSITION MANAGEMENT (Continuous)                              │
│  ├─ Every 5 min: Check stops, time limits, thesis validity     │
│  ├─ Trailing stops: Ratchet up as price advances               │
│  ├─ Partial profits: 50% off at +8%                            │
│  ├─ Time stops: Exit at max_hold_date NO EXCEPTIONS            │
│  └─ Regime check: De-risk on bear/volatile regime              │
│                                                                │
│  NIGHTLY REVIEW (DD Agent)                                     │
│  ├─ Re-analyze ALL held positions                              │
│  ├─ Flag invalidated theses → queue exits                      │
│  ├─ Identify positions past time limits                        │
│  └─ Recommend stop adjustments                                 │
│                                                                │
│  EXIT EXECUTION (Next Market Open)                             │
│  ├─ Execute queued exits from nightly review                   │
│  ├─ Execute broker-triggered stops/targets                     │
│  └─ Log everything with P/L and lesson learned                 │
└────────────────────────────────────────────────────────────────┘
```

### 5.4 New Position Sizing Algorithm

Replace the current flat `max_position_pct` with volatility-adjusted sizing:

```python
def calculate_position_size(
    portfolio_value: Decimal,
    atr_pct: float,           # Stock's 14-day ATR as % of price
    stop_distance_pct: float,  # Distance to stop loss
    max_risk_per_trade: float = 0.02,  # Risk 2% of portfolio per trade
) -> Decimal:
    """
    Size position so max loss = 2% of portfolio.
    
    Volatile stocks get SMALLER positions.
    Tight-stop setups get LARGER positions.
    """
    risk_amount = portfolio_value * Decimal(str(max_risk_per_trade))
    position_value = risk_amount / Decimal(str(stop_distance_pct / 100))
    
    # Apply absolute limits
    min_position = portfolio_value * Decimal("0.08")  # At least 8%
    max_position = portfolio_value * Decimal("0.20")  # At most 20%
    
    return max(min_position, min(max_position, position_value))
```

Example:
- FENC (ATR 5%, stop 12.7%): risk $260 / 12.7% = **$2,047** (16% of $13K) — reasonable
- AMD (ATR 3%, stop 5%): risk $260 / 5% = **$5,200** → capped at 20% = **$2,600**
- This means the volatile biotech gets a smaller absolute position, aligned with risk

### 5.5 New Market Regime Integration

```python
REGIME_RULES = {
    "strong_bull": {
        "max_positions": 8,
        "position_size_multiplier": 1.0,
        "allowed_strategies": ["momentum", "breakout"],
    },
    "bull": {
        "max_positions": 6,
        "position_size_multiplier": 0.8,
        "allowed_strategies": ["momentum", "breakout"],
    },
    "sideways": {
        "max_positions": 4,
        "position_size_multiplier": 0.6,
        "allowed_strategies": ["momentum"],  # Be more selective
    },
    "bear": {
        "max_positions": 2,
        "position_size_multiplier": 0.4,
        "allowed_strategies": [],  # Cash is a position
    },
    "volatile": {
        "max_positions": 3,
        "position_size_multiplier": 0.3,
        "allowed_strategies": [],  # Sit out
    },
}
```

In bear/volatile regimes, the system should **significantly reduce exposure**, not maintain 18 positions.

---

## 6. Implementation Roadmap

### Phase 1: Emergency Fixes (Immediate)

These changes address the most critical flaws and can be implemented quickly.

1. **Broker-level bracket orders on new entries**
   - Modify `_execute_trade()` to use OCO/bracket orders via Alpaca
   - Verify bracket exists after submission

2. **Enforce time-based exits**
   - Add `max_hold_date` check to `_monitor_positions()`
   - Load thesis data for each position and check dates
   - Force exit for any position past max_hold_date

3. **Activate PositionManagerAgent in the run loop**
   - Wire `position_manager.review_position()` into the market hours loop
   - Act on EXIT_FULL recommendations immediately

4. **Nightly position review via DD**
   - Add a step in overnight DD that re-analyzes ALL held symbols
   - Queue exits for invalidated theses

5. **Hard pre-screener gate in the research pipeline**
   - Add `passes_quality_gate()` to `_fetch_market_mover_events()` and `_build_research_universe()`
   - Reject any symbol with: price < $15, avg_volume < 500K, market_cap < $2B
   - Wire the existing `is_quality_stock()` into the v2 engine (currently CLI-only)
   - This alone will eliminate ~40% of wasted LLM calls

### Phase 2: Portfolio Construction Reform (1-2 weeks)

5. **Implement max position count (8)**
   - Block new entries when at capacity
   - "One in, one out" rule

6. **Sector exposure tracking**
   - Map each symbol to sector (use broker/fundamental data)
   - Reject new entries that violate sector limits

7. **Volatility-adjusted position sizing**
   - Replace flat `max_position_pct` with ATR-based sizing
   - Ensure minimum position size of 8%

### Phase 3: Strategy Evolution (2-4 weeks)

8. **Rewrite Swing Trader prompt for momentum**
   - Remove mean-reversion signals (RSI < 30 = buy)
   - Add momentum criteria (price > SMA, RSI 50-70, volume expanding)
   
9. **Add trailing stop logic**
   - After +3%: set trailing stop at breakeven
   - After +5%: trail at 3% below highest close
   - After +8%: take 50% profit, trail remainder at 4%

10. **Implement regime-based exposure rules**
    - Market Analyst regime → caps on positions and sizes
    - Auto de-risk on bear/volatile regime detection

### Phase 4: Portfolio Intelligence (1-2 months)

11. **Correlation matrix tracking**
    - Compute rolling correlation between holdings
    - Block high-correlation entries

12. **Performance attribution**
    - Track: strategy win rate, agent accuracy, sector performance
    - Monthly review: which agents are contributing, which are noise

13. **Feedback learning**
    - Log every trade outcome with thesis data
    - Build a database of "what worked" and "what failed"
    - Use this to refine agent prompts and thresholds

---

## 7. Appendix: Position-by-Position Analysis

### Winners (should have been bigger)

| Symbol | P/L % | Problem |
|--------|-------|---------|
| COGT | +4.7% | Good thesis, but position too small ($490). Should have been $1,300+ |
| FDP | +2.0% | Low-conviction pick, tiny position. Decent steady performer |
| LW | +1.6% | Same — too small to matter |
| AMD | +1.2% | Good stock, tiny position. $5.92 profit is meaningless |
| TPH | +0.8% | Marginal winner, position too small |
| SEM | +0.18% | Basically flat. Not worth holding |

### Losers (should have been cut)

| Symbol | P/L % | What Went Wrong |
|--------|-------|-----------------|
| FENC | -24.7% | Stop loss at ~12.7% NEVER TRIGGERED. Small-cap biotech with high ATR — should have been tiny position or avoided |
| ETSY | -13.6% | Thesis expired March 5. Still held March 29. Max hold violation |
| VRT | -8.4% | DD said "SELL into S&P inclusion event." Catalyst passed. Still holding |
| DASH | -7.3% | DD said "FAILED CATALYST... at stop loss." Never exited |
| ASND | -5.5% | DD noted technical claims in thesis were wrong. Held anyway |
| PINS | -5.3% | Elliott Management thesis — medium-term play but no position management |
| CRM | -4.8% | Tech selloff, no sector hedging |
| AMZN | -4.9% | Same sector exposure as CRM, AMD, DASH — correlated |
| NOA | -3.5% | DD said "CATASTROPHICALLY FAILED." Stop obliterated. Still held |
| FXI | -2.3% | China ETF — macro bet without thesis management |
| VRTX | -1.3% | Quality pharma but entered without clear catalyst timing |
| FDX | -0.3% | Flat — no clear thesis edge |

### Summary: What Would Have Happened With v3 Rules

If Beavr v3 rules had been in effect:

1. **Max 8 positions** → Would have entered only the 8 highest-conviction names, with $1,600+ each
2. **Broker stop losses** → FENC would have been stopped at -12.7% (saving ~$56), DASH at ~-7% (similar), NOA at ~-7% (saving ~$20+)
3. **Time-based exits** → ETSY exited March 5 (was +11% at that point = +$80 profit instead of -$103 loss). VRT exited March 23 (was near target = ~$0 instead of -$63)
4. **Momentum filter** → FENC (RSI 32, price below SMAs) would not have been bought. NOA (price below SMAs) would not have been bought
5. **Sector limits** → Would not hold AMD + AMZN + CRM + DASH + PINS + VRT simultaneously (6 tech/growth names)
6. **Quality screener** → FENC ($7.85 entry), NOA ($13.32), SEM ($16.26), PINS ($18.54) — several positions would never have been considered with a $15+ price floor and $2B+ market cap requirement

**Estimated improvement**: Instead of -$506, the portfolio would likely be **+$100 to +$300** — a swing of $600-$800 purely from execution discipline and better stock selection.

**LLM cost savings**: With a pre-screener, ~40-60% of DD reports (90-136 of 227) would never have been generated, saving ~$50-80 in LLM costs and letting the DD agent focus on quality candidates.

---

## 8. Reviewer's Critical Assessment

*This section was written as a second-pass review, re-verifying every claim against the actual code and stress-testing the proposed solutions for blind spots, over-engineering, or incorrect diagnoses.*

### 8.1 Flaw-by-Flaw Verification

#### Flaw #1 (Stop Losses): PARTIALLY CORRECT — Root Cause Needs Refinement

**What the original analysis got right:**
- No broker-level stop orders (OCO/bracket) are placed. Confirmed.
- Monitoring relies on 5-minute polling. Confirmed.
- FENC at -24.7% clearly blew through any reasonable stop.

**What the original analysis got WRONG or OVERSIMPLIFIED:**

The stop-loss logic in `_monitor_positions()` is actually **correctly implemented**. The P&L math is right (`pnl_pct <= -stop_pct` fires correctly for losses), the broker IS wired up via `set_trading_client()` in the CLI startup, and `_close_position()` does submit real sell orders.

So **why aren't stops firing?** After thorough code review, the most likely causes are:

1. **db_pos returns None** — If the position was created in the broker but the `positions_repo.open_position()` call failed (or wasn't reached due to an exception earlier in `_execute_trade()`), the DB has no record of the position. The monitor falls back to `swing_short_stop_pct = 4.0%`. So for FENC, which had a DD-recommended stop of 12.7%, the system would only exit at -4%. But FENC is at -24.7% — even a 4% stop should have triggered. This suggests the positions_repo might be returning valid records but with incorrect stop values, OR the monitoring ran into an exception that was caught silently.

2. **The system wasn't running continuously** — The state file shows `last_research_run: null` and `trades_today: 0` as of March 18. If the orchestrator was only run intermittently (not 24/7), positions could have gapped past stops between manual restarts.

3. **Exception swallowing** — The entire `_monitor_positions()` body is wrapped in `try/except Exception` that logs but continues. If `self._broker.get_positions()` throws, or if the `pos.unrealized_pl` field returns an unexpected type, the monitoring silently fails for that iteration.

**Revised severity**: Still CRITICAL, but the fix is more nuanced than "stops are broken." The code is correct — the operational deployment is the likely failure point. Broker-level stops are still the right fix, but we should also add startup verification that confirms stop orders exist for every position.

#### Flaw #2 (Position Lifecycle): CONFIRMED CORRECT

The `PositionManagerAgent` with its `review_position()` method is instantiated, passed to the orchestrator, and then **never called**.  The orchestrator's `_monitor_positions()` is a simplified inline version that only checks PnL. The time-based exits (max_hold_date, catalyst_date) and thesis validation are completely absent from the run loop.

**No revision needed.** This flaw is accurately described.

#### Flaw #3 (Over-Diversification): CONFIRMED, BUT NUANCE NEEDED

18 positions is indeed too many for a $13K account. However, the original analysis didn't mention that:

- The system has a `daily_trade_limit = 5` that **does prevent** mass buying in a single day
- The real culprit is that positions **accumulate over days/weeks** because there's no max-positions cap and no exit mechanism working
- The V2Config has no `max_open_positions` parameter at all

So the over-diversification is really a **symptom of Flaws #1 and #2** — if stops and time exits worked, many positions would have been closed, keeping the count lower naturally.

**Revised take**: Over-diversification is real but is partly a downstream consequence of broken exits. We need BOTH a hard position cap AND working exit mechanisms. Adding a position cap alone without fixing exits would just cause the system to never enter new trades while holding onto losers forever.

#### Flaw #4 (Sector/Correlation): CONFIRMED, LOW IMPLEMENTATION PRIORITY

The claim is accurate — there's zero sector awareness. However, this is a **lower priority** than fixing exits. In the current situation, even perfectly diversified positions would still be losing money because stops don't fire and time exits don't work.

**Revised take**: This is a Phase 2 concern. Phase 1 should focus on stops, exits, and the screener. Sector tracking can come after the system can actually manage the positions it holds.

#### Flaw #5 (Research-Action Disconnect): CONFIRMED, BUT LARGER ISSUE

The diagnosis is correct that DD findings on held symbols don't trigger exits. However, the original analysis misses a deeper issue: **DD runs on held symbols are REJECTIONS of re-entry theses, not position reviews.**

When DD analyzes DASH and says "REJECT," it's rejecting a *new thesis to buy more DASH*. The DD agent doesn't know it's reviewing a held position — it's evaluating a new thesis. The agent's rejection commentary ("DO NOT ENTER") happens to be useful position management advice, but it's incidental, not intentional.

**Revised take**: The fix isn't just "connect DD to exits" — it requires a **distinct position review mode** where the DD agent (or Position Manager) is given the existing position context (entry price, shares held, current P&L) and asked "should we exit?" rather than "should we enter?" These are fundamentally different questions.

#### Flaw #6 (Entry Precision): CONFIRMED, but LOWER PRIORITY

The `current_price = thesis.entry_price_target  # TODO: Get live price` is a real bug but has a smaller impact than the exit-side failures. The `TODO` comment shows this was known and deprioritized. Market orders on liquid large-caps (AMD, AMZN, CRM) have minimal slippage. On small-caps (FENC, NOA) it matters more but those shouldn't be traded at all (see Flaw #7).

**Revised take**: Fix, but in Phase 2. Limit orders are nice-to-have when the fundamental issue is "we hold losers forever."

#### Flaw #7 (No Pre-DD Screener): CONFIRMED, CRITICAL

The numbers are damning: 227 DD reports, 11% approval rate, 100% lack fundamental data. The pipeline has zero enforcement of the `quality_filter` config section.

However, one correction: **the 89% rejection rate includes rejections for valid reasons beyond "junk stock"**. Many rejections are because:
- The stock is **already held** (DD correctly rejects re-entry)
- The thesis is **stale** (catalyst passed, prices moved)
- The R/R is bad at current prices (entry target missed)

So the "waste" is not purely from junk stocks. A realistic estimate of the junk-filter savings is closer to **40-50% of DD reports** (the sub-$15, sub-500K-volume, sub-$2B-market-cap names), not 89%.

**Revised take**: Still critical, still should be Phase 1, but the savings estimate should be tempered. The remaining 50-60% of rejections are features, not bugs — the DD agent *should* reject stale theses and existing positions.

### 8.2 Solution Review: What We Got Right and Wrong

#### Reform 1 (Broker-Level Stops): CORRECT, but needs Alpaca API check

Alpaca's API supports bracket orders (`order_class="bracket"`) and trailing stops. This is the right fix. However, bracket orders have constraints:
- They require `take_profit` AND `stop_loss` params at submission
- Trailing stops are separate order types, not OTO modifications
- If the entry order partially fills, the bracket applies to the fill — need to handle partial fills

**Verdict**: Right direction, implementation will be more complex than described.

#### Reform 2 (Active Position Manager): CORRECT, but don't over-LLM

The Position Manager agent uses LLM for thesis validation. Calling it every 5 minutes for every position would be **extremely expensive**. 8 positions × 12 checks/hour × 6.5 hours = 624 LLM calls per day just for position management.

**Revised approach**: 
- Price/time/stop checks should be **deterministic code**, no LLM
- LLM-based thesis validation should run **once per day** (nightly review), not every 5 minutes
- Only escalate to LLM when a position triggers a flag (approaching target, catalyst date passed, etc.)

#### Reform 3 (Max 8 Positions): SLIGHTLY TOO RIGID

8 is a reasonable number but shouldn't be a hard constant. It should scale with portfolio size. At $13K, 6-8 positions. At $50K, 10-12. At $100K, 12-15.

Also, the **minimum position size of 8%** means the system can't act at all when approaching the limit and cash is low. Better to set the minimum based on absolute dollars ($500 minimum on a $13K account) rather than percentage.

**Revised**: Scale with portfolio size. Use absolute minimum ($500) rather than percentage minimum.

#### Reform 4 (Sector Limits): CORRECT but DEFERRED

This is intellectually correct but operationally premature. The system can't even manage 18 untracked positions — adding sector tracking before fixing exits is putting the cart before the horse.

**Revised**: Phase 3, not Phase 1.

#### Reform 5 (Momentum-Only): OVERSTATED

The original analysis says "abandon mean reversion" and cites academic papers. However:

1. **The v2 architecture is thesis-driven, not indicator-driven.** The system trades on catalysts (earnings, FDA approvals, inclusion events), not pure RSI signals. The Swing Trader agent exists but is largely superseded by the Thesis Generator + DD pipeline in v2.

2. **The held positions didn't fail because of mean reversion bias.** DASH failed because earnings were sold. FENC failed because a small-cap pharma got hammered. VRT failed because the S&P inclusion was "sell the news." ETSY failed because no one exited it after it hit target. These are exit failures, not entry-philosophy failures.

3. **Telling the LLM "never buy oversold stocks" is too blunt.** Many of the best swing trades ARE pullbacks in uptrends. The issue is buying pullbacks in *downtrends* (falling knives). The filter should be: "only buy pullbacks if the TREND is intact (price > 50-day SMA)."

**Revised**: Don't abandon mean reversion entirely. Instead, add a **trend filter** to the Swing Trader prompt: "Only consider RSI < 35 setups IF price is above the 50-day SMA." This preserves the valid strategy (buying pullbacks in uptrends) while blocking the dangerous one (buying crashes).

#### Reform 6 (Limit Orders): CORRECT but NOT CRITICAL

For large-cap names, market orders are fine. The real issue is that the system doesn't check `thesis.entry_price_target` against the live price before buying. Adding a 3% price-guard check (skip if price > 103% of target) would solve most of the problem without requiring limit order infrastructure.

#### Reform 7 (DD-to-Position Feedback Loop): NEEDS REDESIGN

The original proposal says to have DD trigger exits on held positions. But as noted in the Flaw #5 revision, DD is reviewing *new entry theses*, not existing positions. Having DD accidentally double as position management is fragile.

**Revised**: Create a dedicated **nightly position review pass** that is SEPARATE from DD-on-new-theses. This review:
1. Iterates all held positions
2. For each: checks thesis dates, catalysts, invalidation conditions (deterministic, no LLM)
3. Only uses LLM for ambiguous cases ("catalyst occurred but price didn't move — keep or exit?")
4. Queues exit orders for next market open

### 8.3 Revised Priority Order

After review, the implementation priority should be:

| Priority | Fix | Why |
|----------|-----|-----|
| **P0** | Broker-level bracket orders on entry | Prevents all future max-loss blowouts |
| **P0** | Time-based exit enforcement (deterministic, no LLM) | Prevents ETSY/VRT situations |
| **P0** | Hard pre-screener in research pipeline | Prevents wasting LLM on junk stocks |
| **P1** | Max positions cap (scaled to portfolio size) | Prevents over-diversification |
| **P1** | Nightly position review pass (deterministic + LLM escalation) | Catches invalidated theses |
| **P1** | Price-guard check before entry (skip if >3% above target) | Prevents bad entries |
| **P2** | Trailing stop logic | Locks in profit on winners |
| **P2** | Trend filter in Swing Trader prompt | Prevents buying into downtrends |
| **P2** | Volatility-adjusted position sizing | Right-sizes risk per position |
| **P3** | Sector/correlation tracking | Portfolio-level diversification |
| **P3** | Regime-based exposure scaling | Adapts to market conditions |
| **P3** | Performance attribution / feedback learning | Long-term improvement |

### 8.4 What the Original Analysis Completely Missed

1. **Operational continuity**: The system may not have been running 24/7. The state file shows `last_research_run: null` and stale dates. If the orchestrator crashes or is only run ad-hoc, all the monitoring logic is moot. A **health check / watchdog** mechanism is needed to ensure the orchestrator is actually alive and polling.

2. **Paper trading vs. live gap**: The config says `mode = "paper"`. Paper trading on Alpaca may handle positions differently than live — specifically, `unrealized_pl` calculations and position state may be less reliable. Bugs that only manifest in paper mode could explain why stops don't fire.

3. **LLM unreliability**: The thesis generator, news monitor, and DD agent all use LLM reasoning. LLMs are stochastic — the same inputs can produce different outputs. A thesis that gets 62% confidence one day might get 58% the next. The system has no mechanism to detect when LLM reasoning is inconsistent or nonsensical. Adding basic sanity checks on LLM outputs (e.g., "entry price should be within 10% of current price") would catch hallucinations.

4. **No benchmark comparison**: The analysis says -4.1% is bad, but doesn't compare to SPY over the same period. If SPY was -6% in this timeframe, Beavr actually outperformed! (Though given March 2026 was broadly sideways, -4.1% is still likely underperformance.) A benchmark comparison would make the analysis more rigorous.

---

## 9. Additional Issues

### Issue #8: `bvr ai analyze` Command Is Fragile (Intermittent Crashes)

**Severity: MEDIUM**

The `bvr ai analyze` command crashes intermittently with `ValueError: not enough values to unpack`.

**Root Cause**: The `analyze_opportunities()` method in `cli/ai.py` has a return type mismatch:

```python
# Lines 316-317 — early returns give a bare list:
if not opps:
    return []        # ❌ Caller expects 3-tuple

if not with_technicals:
    return []        # ❌ Caller expects 3-tuple

# Line 406 — success path returns a 3-tuple:
return picks, result.market_view, result.risk_level  # ✅
```

The caller at line 854 does:
```python
picks, market_view, risk_level = investor.analyze_opportunities(amount_dec)
```

When no opportunities are found (weekend, pre-market, API down), the method returns `[]` instead of `([], "", "")`, causing an unpacking crash.

**Additional fragility**:
- No try/except around the LLM call — if the LLM returns a schema mismatch, the command crashes
- No error handling if the screener API is unavailable
- No fallback message if all technical indicator computations fail
- The quality filter is too permissive: the output shows stocks like ARTL (+230%, $10), CLBR (RSI 0.0), EGG ($5.75), GLND ($8.49) — the same junk-funnel problem from the autonomous pipeline

**Fix**: Change the early returns to `return [], "", ""` and wrap the LLM call + outer function in try/except with user-friendly error messages. Also apply the quality screener consistently so the analyze command doesn't recommend penny stocks.

### Issue #9: No Market Intelligence Briefing Capability

**Severity: MEDIUM-HIGH** (Missing feature, not a bug)

The system has no way to produce an on-demand market overview. There's no "what's happening in the market right now?" command — neither in the CLI nor in the messaging system.

Professional trading desks start every day with a **morning brief** covering:
- Market regime and trend assessment
- Key index levels (SPY, QQQ, VIX) and their technical posture
- Sector rotation — what's hot, what's not
- Upcoming catalysts (earnings, Fed meetings, economic data)
- Current portfolio context — how our positions relate to market conditions
- Actionable outlook — what to watch for, what to avoid

Beavr currently has all the raw ingredients (Market Analyst agent, indicator computation, news monitor), but they're wired for autonomous operation only. There's no way to ask the system "give me a market summary right now."

This is critical for trust and oversight — the user should be able to pull a briefing anytime to understand what the system sees and why it's making decisions.

---

## 10. Market Briefing System Design

### 10.1 Overview

A new **Market Briefing** subsystem that produces an on-demand, comprehensive market outlook. Accessible via:
- **CLI**: `bvr ai brief` — Rich-formatted terminal output
- **Telegram**: `/brief` — Formatted message sent to chat
- **Programmatic**: `BeavrAPI.get_market_brief()` — Returns structured data

### 10.2 What the Brief Contains

```
📊 BEAVR MARKET BRIEF — March 29, 2026
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🏛️ MARKET REGIME: Sideways → Cautious
Confidence: 72% | Risk Posture: Moderate

📈 INDEX SNAPSHOT
  SPY:  $560.42  -0.3%  (Above 50-SMA, RSI 52)
  QQQ:  $478.15  -0.5%  (Below 20-SMA, RSI 47) ⚠️
  VIX:  18.4     +5.2%  (Elevated but not panic)
  DXY:  104.2    +0.1%  (Dollar strength headwind)

🔄 SECTOR ROTATION
  Leading:  Energy (+1.2%), Utilities (+0.8%)
  Lagging:  Tech (-0.9%), Consumer Disc (-0.7%)
  Theme:    Defensive rotation — risk-off signal

📅 UPCOMING CATALYSTS (Next 5 Days)
  Mar 31: PCE Inflation data
  Apr 1:  ISM Manufacturing PMI
  Apr 2:  ADP Employment
  Apr 4:  Non-Farm Payrolls

💼 PORTFOLIO CONTEXT
  Positions: 18 | Cash: $39 | Drawdown: -6.8%
  Sector Tilt: Overweight Tech (6 positions)
  ⚠️ Portfolio heavily correlated with QQQ weakness
  ⚠️ 5 positions past max_hold_date

🎯 ACTIONABLE OUTLOOK
  • Market in wait-and-see mode ahead of PCE data
  • Tech weakness aligns with portfolio drag — consider reducing exposure
  • Energy sector strength worth monitoring for rotation plays
  • VIX at 18 = slightly elevated; avoid new high-beta entries
  • Priority: Exit stale positions (ETSY, VRT, NOA) before adding new
```

### 10.3 Architecture

The briefing system uses existing agents and data providers without creating new ones:

```
┌─────────────────────────────────────────────────┐
│              MARKET BRIEFING FLOW                │
│                                                  │
│  Data Collection (No LLM)                        │
│  ├─ Fetch SPY, QQQ, VIX, DXY bars + indicators  │
│  ├─ Fetch sector ETF performance (XLE, XLK...)   │
│  ├─ Get current portfolio positions + P/L        │
│  ├─ Get upcoming earnings calendar               │
│  └─ Get recent news headlines                    │
│                                                  │
│  LLM Synthesis (Single call)                     │
│  ├─ System prompt: "Market analyst briefing"     │
│  ├─ All data injected as context                 │
│  ├─ Structured output: MarketBrief Pydantic model│
│  └─ Includes actionable recommendations          │
│                                                  │
│  Delivery                                        │
│  ├─ CLI: Rich-formatted table + panels           │
│  ├─ Telegram: Formatted markdown message         │
│  └─ API: MarketBrief dataclass returned          │
└─────────────────────────────────────────────────┘
```

### 10.4 Implementation Plan

**New files:**
- `src/beavr/agents/market_briefing.py` — The briefing agent (single LLM call with structured output)
- `src/beavr/messaging/commands/briefing.py` — `/brief` Telegram command handler

**Modified files:**
- `src/beavr/cli/ai.py` — Add `bvr ai brief` CLI command
- `src/beavr/messaging/api.py` — Add `get_market_brief()` to BeavrAPI protocol
- `src/beavr/messaging/api_impl.py` — Implement `get_market_brief()`
- `src/beavr/cli/ai.py` (router registration) — Register BriefingCommandHandler

**Data model:**

```python
class MarketBrief(BaseModel):
    """Structured market briefing output."""
    
    # Timestamp
    generated_at: datetime
    
    # Market Regime
    regime: str  # bull, bear, sideways, volatile
    regime_confidence: float
    risk_posture: str  # aggressive, moderate, cautious, defensive
    
    # Index Snapshot
    indices: list[IndexSnapshot]  # SPY, QQQ, VIX etc.
    
    # Sector Analysis
    leading_sectors: list[SectorPerformance]
    lagging_sectors: list[SectorPerformance]
    rotation_theme: str
    
    # Upcoming Catalysts
    catalysts: list[UpcomingCatalyst]
    
    # Portfolio Context
    portfolio_summary: str
    portfolio_warnings: list[str]
    
    # Actionable Outlook
    key_takeaways: list[str]  # 3-5 bullet points
    watch_list: list[str]  # Symbols to monitor
    avoid_list: list[str]  # Things to stay away from
```

**Telegram command handler:**

```python
class BriefingCommandHandler(BaseCommandHandler):
    command_names = ["brief", "briefing", "market"]
    tier = "analysis"
    description = "Get an on-demand market briefing with outlook"
    
    async def handle(self, command: InboundCommand) -> CommandResult:
        brief = self._api.get_market_brief()
        formatted = format_market_brief(brief)
        return CommandResult(success=True, message=formatted)
```

**CLI command:**

```python
@ai_app.command()
def brief() -> None:
    """Get a market briefing with outlook and recommendations."""
    investor = get_investor()
    with console.status("Generating market brief..."):
        brief = investor.get_market_brief()
    render_market_brief(console, brief)
```

### 10.5 Key Design Decisions

1. **Single LLM call**: The brief uses ONE LLM call with all data pre-fetched. This keeps cost low (~$0.01 per brief) and latency under 30 seconds.

2. **Data-first, LLM-second**: Raw market data (prices, indicators, events) is gathered deterministically. The LLM only synthesizes and interprets — it doesn't fetch data or make API calls.

3. **Portfolio-aware**: Unlike generic market summaries, the Beavr brief includes portfolio context. "QQQ is weak" becomes "QQQ is weak and you're overweight tech" — actionable for YOUR situation.

4. **Sector ETF approach**: Use XLE, XLK, XLF, XLV, XLI, XLU, XLP, XLY, XLC, XLRE as sector proxies. Simple, liquid, universally available via Alpaca.

5. **No scheduled automation (initially)**: The brief is on-demand only. A scheduled "Monday morning brief" can be added later by wiring a cron trigger to the same `get_market_brief()` API.

---

*This document should be reviewed weekly and updated as reforms are implemented. The goal is not perfection — it's systematic improvement through disciplined execution.*
