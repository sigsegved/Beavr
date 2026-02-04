# Agentic Investor System (AIS)

## Architecture Specification v0.1

## 1) Purpose

Design and implement a **hands-off, agentic investor system** that trades **equities, crypto, and options** using multiple specialized “persona” agents (e.g., Day Trader, Swing Trader). The system runs on **your own infrastructure**, supports **minimal human interaction (1–2 check-ins/day)**, and prioritizes **risk-controlled outperformance**.

**Primary objective (target, not guaranteed):** outperform SPY by ~2× on a 1-year annualized basis with a **hard max drawdown cap of 20%** enforced by automated risk controls.

---

## 2) Scope

### In-scope

* Multi-agent decision system with persona strategies
* Portfolio construction across strategies + assets
* Automated execution (broker/exchange connectors)
* Risk management with enforceable hard constraints
* Backtesting + paper trading + live trading modes
* Continuous monitoring, logging, and model governance
* Daily/Intraday operating cadence suitable for minimal oversight

### Out-of-scope (initially)

* HFT / sub-second latency market making
* Proprietary alternative datasets requiring special licenses
* Fully autonomous leverage management beyond defined constraints

---

## 3) Key Constraints & Design Principles

1. **Risk-first**: Risk constraints are not advisory—they are enforced at multiple layers.
2. **LLMs are not in the hot path**: LLM reasoning is used for slow loops (daily prep, event interpretation, explanations). Fast loops use deterministic signals/models.
3. **Modular strategies**: Each persona strategy is independently testable, deployable, and capital-allocatable.
4. **Reproducibility**: Every decision is replayable with data/version snapshots.
5. **Fail-safe execution**: Stale data, missing signals, or degraded models cause safe mode (reduce risk / hold / unwind).

---

## 4) System Overview

AIS is a layered system:

1. **Data Layer**: Ingest, normalize, validate, store, and serve market + text + alt-data.
2. **Research/Signal Layer**: Produce signals via ML/RL models + statistical features.
3. **Agentic Decision Layer**: Persona agents propose trades; risk agent gates; portfolio agent allocates.
4. **Execution Layer**: Place orders with slippage-aware logic and exchange/broker adapters.
5. **Monitoring/Governance Layer**: Telemetry, drift detection, PnL attribution, alerts, retraining.

### Operating modes

* **Backtest Mode**: deterministic replays with friction models
* **Paper Mode**: live data + simulated fills
* **Live Mode**: real orders with guardrails and kill switches

---

## 5) Architecture Diagram (Logical)

```
            ┌───────────────────────────────────────────────────┐
            │                    User Dashboard                  │
            │  Daily brief • risk status • approvals • overrides │
            └───────────────▲───────────────────▲───────────────┘
                            │                   │
                      Alerts/Reports      Manual Controls
                            │                   │
┌───────────────────────────┴───────────────────┴───────────────────────────┐
│                           Monitoring & Governance                            │
│ Metrics • PnL attribution • Drift • Model registry • Audit logs • Replay     │
└───────────────────────────▲───────────────────▲───────────────────────────┘
                            │                   │
                       Decisions/Events     Model updates
                            │                   │
┌───────────────────────────┴───────────────────────────────────────────────┐
│                         Agentic Decision Layer                              │
│ Orchestrator → Persona Agents → Portfolio Constructor → Risk Gate → Orders  │
└───────────────▲───────────────────────────────▲───────────────────────────┘
                │                               │
           Signals/Context                   Orders/Constraints
                │                               │
┌───────────────┴───────────────────────────────┴───────────────────────────┐
│                           Research / Signal Layer                           │
│ Feature store • ML predictors • RL policies • Regime detection • Vol models  │
└───────────────▲───────────────────────────────▲───────────────────────────┘
                │                               │
           Clean data feeds                 Text/Events embeddings
                │                               │
┌───────────────┴───────────────────────────────┴───────────────────────────┐
│                                 Data Layer                                  │
│ Ingest → Normalize → Validate → Store → Serve (TSDB + object + vector DB)    │
└───────────────▲───────────────────────────────▲───────────────────────────┘
                │                               │
        Exchanges/Brokers/APIs            News/Filings/Social/On-chain

┌───────────────────────────────────────────────────────────────────────────┐
│                               Execution Layer                               │
│ Broker/Exchange adapters • Smart order routing • TCA • Reconciliation        │
└───────────────────────────────────────────────────────────────────────────┘
```

---

## 6) Major Components

### 6.1 Data Layer

**Responsibilities**

* Ingest real-time and batch data
* Normalize across venues
* Validate (staleness, outliers, missing fields)
* Store raw + cleaned + features
* Provide low-latency query APIs

**Data sources (typical)**

* Equities: OHLCV, L2 (optional), corporate actions, fundamentals, calendars
* Options: chain snapshots, greeks, implied vols, surfaces, term structure
* Crypto: OHLCV, order book, funding rates, open interest
* Text: news, earnings transcripts, filings, macro releases
* Alt: on-chain metrics (addresses, flows), sentiment indicators

**Storage & serving**

* Raw immutable store (object storage)
* Cleaned time-series store (TSDB)
* Relational metadata store (instruments, mappings, corporate actions)
* Feature store (offline + online)
* Vector store for text embeddings (news/event memory)

**Key data contracts**

* `MarketBar`: {symbol, venue, ts, open, high, low, close, volume}
* `OrderBook`: {symbol, ts, bids[], asks[]}
* `OptionQuote`: {underlying, strike, expiry, right, bid/ask, iv, greeks}
* `NewsEvent`: {id, ts, source, entities[], text, embedding, sentiment}

**Validation rules (examples)**

* Stale feed threshold: (equities 60s, crypto 10s)
* Price sanity: clamp or reject if >N std dev from rolling median
* Corporate actions: adjusted price continuity checks

---

### 6.2 Research / Signal Layer

**Responsibilities**

* Produce standardized signals for agents
* Provide risk model inputs (vol, corr, factor exposures)
* Support both daily and intraday horizons

**Signal families**

1. Technical: momentum, trend, mean-reversion, volatility breakout
2. Statistical: pairs/spread, cointegration, regime-switch models
3. Fundamental: valuation factors, quality, earnings surprise proxies
4. Event/Text: sentiment, event novelty, macro surprise
5. Options: vol surface features, skew, term structure, gamma exposure
6. Crypto-specific: funding/oi, on-chain flows, whale activity

**Models (examples)**

* Supervised predictors: return quantiles, direction, volatility forecasts
* RL policies: allocation / position sizing under transaction costs
* Regime detector: hidden Markov model / change-point detection / classifier
* Vol models: GARCH variants + neural vol forecaster + surface smoother

**Standard output format**

* `SignalPacket`:

  * horizon: {intraday | 1d | 5d | 20d}
  * expected_return (mu)
  * risk (sigma, tail)
  * conviction (0–1)
  * rationale tags (e.g., “trend_up”, “news_positive”)
  * model_version + data_snapshot_id

---

### 6.3 Agentic Decision Layer

This is the core. A multi-agent system where persona agents propose actions and a risk-gated portfolio agent decides.

#### 6.3.1 Orchestrator

**Responsibilities**

* Trigger agent workflows by schedule/event
* Maintain shared state (“blackboard”) for the trading day
* Enforce time budgets and deterministic ordering
* Aggregate proposals and request revisions (e.g., if risk vetoed)

**Shared state (Blackboard)**

* Portfolio state (positions, cash, margin)
* Market context (regime, vol, liquidity)
* Active constraints (risk budgets, exposure caps)
* Latest signals and event summaries

#### 6.3.2 Persona Strategy Agents

Each persona outputs **trade proposals** for its scope.

**A) Day Trader Agent (intraday)**

* Inputs: intraday bars, microstructure signals, volatility, liquidity
* Style: short holding times; avoids overnight risk (configurable)
* Outputs: small position sizes; tight stops; high turnover budgeted

**B) Swing Trader Agent (multi-day)**

* Inputs: daily/4h signals, regime, fundamentals, macro, sentiment
* Style: holds days–weeks; lower turnover
* Outputs: core positions with wider stops, thesis tags

**C) Volatility/Options Agent**

* Inputs: IV surface, skew, term structure, realized vol forecast, events
* Style: long/short vol strategies with defined risk (spreads, hedges)
* Outputs: option structures (verticals, calendars, collars) + hedges

**D) Crypto Specialist Agent**

* Inputs: funding, oi, order book, on-chain flows, sentiment
* Style: momentum + mean-reversion; risk on weekends; venue-aware

**E) Regime & Macro Agent (slow loop)**

* Inputs: macro calendar, yields, FX, risk-on/off indicators
* Output: regime label + recommended risk posture

**F) LLM Event Interpreter Agent (slow loop)**

* Inputs: news, filings, transcripts
* Output: structured event impacts (affected tickers, confidence)

#### 6.3.3 Portfolio Construction Agent

Takes proposals from persona agents and produces a unified portfolio.

**Responsibilities**

* Capital allocation across personas (risk budgeting)
* Translate proposals into target positions (size, entry bands)
* Deconflict exposures (avoid doubling the same risk factor)
* Optimize for risk-adjusted return subject to constraints

**Allocation approaches**

* Hierarchical: allocate risk to {Day, Swing, Options, Crypto}
* Within-strategy: mean-variance w/ robust covariance + turnover penalty
* RL allocator: policy outputs risk budgets and position scalars

**Portfolio objective (configurable)**

* Maximize expected return minus penalties:

  * volatility penalty
  * drawdown penalty
  * transaction cost penalty
  * concentration penalty

#### 6.3.4 Risk Management Agent (Hard Gate)

**Non-negotiable**. Any trade must pass risk checks.

**Hard constraints**

* Max portfolio drawdown: **20%** (system-level)
* Max single-name exposure: X% NAV (config)
* Max sector/asset-class exposure: Y%
* Max options Greeks: |delta|, |gamma|, |vega| caps
* Max leverage/margin: caps per asset class
* Liquidity constraints: % of ADV / order book depth

**Risk checks (examples)**

* Pre-trade VaR/CVaR within limit
* Scenario stress (gap down, vol spike, correlation spike)
* Concentration & factor exposures
* Kill switch triggers

**Responses**

* Approve as-is
* Approve with reduced size
* Require hedge (e.g., SPY put spread)
* Reject and request alternate proposal

#### 6.3.5 Trade Decision Object

Output of decision layer.

* Targets: desired holdings and risk posture
* Orders: list of order intents
* Metadata: reasons, signals, approvals, model versions

---

### 6.4 Execution Layer

**Responsibilities**

* Convert order intents into executable orders
* Venue selection and order type selection
* Slippage controls and transaction cost analysis (TCA)
* Post-trade reconciliation

**Execution features**

* Smart order routing (best bid/ask, fees, liquidity)
* Order slicing for larger orders (VWAP/TWAP)
* Limit-first policy with fallback logic
* Cancel/replace logic
* Hard price bands and max slippage per order

**Reconciliation**

* Compare expected vs filled
* Detect partial fills, rejects, and venue outages
* Update portfolio state in near real-time

---

### 6.5 Monitoring & Governance Layer

**Responsibilities**

* Performance tracking (PnL, Sharpe, Sortino, Calmar)
* Attribution: by strategy, asset class, signal family
* Drift detection: data drift + model drift + regime drift
* Alerting: risk breaches, degraded execution, stale feeds
* Audit trail: full decision replayability

**Daily outputs (to you)**

* Morning plan: risk posture, top exposures, key events
* Midday check: PnL, risk, notable deviations
* End-of-day report: actions, attribution, issues, changes

---

## 7) Schedules & Workflows

### 7.1 Daily cycle (equities focus)

1. Pre-market (T-60m to open)

* Data refresh, corporate actions, events
* Regime classification + risk posture
* Swing agent updates targets
* Options agent updates vol/event structures
* Portfolio construction generates target book
* Risk gate approves target book
* Execution preps entry orders

2. Intraday loop (every 1–5 minutes)

* Update intraday signals
* Day trader agent proposes tactical adds/reductions
* Risk gate checks incremental risk
* Execution applies orders

3. Close / Post-market

* Reconcile fills, compute realized PnL
* Model monitoring & drift checks
* Backtest “shadow replay” for sanity

### 7.2 Crypto cycle (24/7)

* Use rolling windows + a “sleep” period to maintain minimal oversight.
* Weekend risk posture can auto-reduce exposure.

---

## 8) Model Lifecycle

### 8.1 Versioning

* Data snapshot IDs (immutable)
* Model versions (registry)
* Strategy config versions
* Decision logs reference all versions

### 8.2 Retraining

* Cadence: weekly for intraday models, monthly for swing, as needed for options
* Triggered retraining: drift exceeds threshold, performance decay

### 8.3 Evaluation

* Walk-forward backtests with realistic costs
* Stress tests: 2020 crash, 2022 rates shock, crypto crash regimes
* Paper trading gate before live promote

---

## 9) Risk & Safety Mechanisms

### 9.1 Kill switches

* Hard drawdown threshold ladder (e.g., 10%, 15%, 20%)

  * 10%: reduce risk budgets by 30%
  * 15%: reduce by 60% + require hedges
  * 20%: flatten risk assets / halt new risk

### 9.2 Data integrity safe mode

* If feeds stale or corrupted: stop trading, cancel opens, optionally flatten

### 9.3 Model degradation safe mode

* If prediction confidence collapses: shift to conservative baseline (cash/hedged)

---

## 10) Human Interaction Design (1–2 touches/day)

* **Morning briefing**: recommended posture + planned trades + key risks
* **Optional midday ping**: only if anomalies or big deviations
* **Overrides**

  * Pause strategy
  * Reduce risk multiplier
  * Approve/deny large trades beyond thresholds
* **Explainability**

  * Every trade includes a concise “why” (signals + event summary + risk notes)

---

## 11) Interfaces (APIs)

### 11.1 Internal event bus topics (examples)

* `data.market_bars`
* `data.options_quotes`
* `signals.*`
* `agent.proposals.*`
* `portfolio.targets`
* `risk.decisions`
* `execution.orders`
* `execution.fills`
* `monitoring.alerts`

### 11.2 Service APIs

* Data Service: query bars/options/news by symbol and time range
* Feature Service: get latest features online
* Decision Service: submit proposals, retrieve targets
* Execution Service: submit orders, status, cancel

---

## 12) Initial Strategy Set (MVP → v1)

### MVP (4–8 weeks)

* Swing Trader (equities + crypto) + conservative risk
* Basic options hedging (protective collar/put spreads)
* Deterministic baseline model + limited ML features
* Full backtest + paper trading + monitoring

### v1

* Add Day Trader intraday tactical layer
* Add vol/option alpha strategies (defined-risk spreads)
* Add LLM event interpreter for daily brief + event flags
* Add RL-based allocator for risk budgets

---

## 13) Acceptance Criteria

* Engineering

  * End-to-end replayable decisions with consistent outputs
  * Zero-trade on stale data conditions
  * Broker/exchange execution with reconciliation

* Trading performance (gated)

  * Paper trading meets defined risk metrics
  * Backtests show plausible edge and robust out-of-sample behavior
  * Drawdown enforcement works under stress scenarios

---

## 14) Open Decisions (to finalize during implementation)

* Primary broker/exchange stack and asset universe
* Rebalance frequency and intraday cadence
* Position sizing method (risk parity vs RL allocator vs hybrid)
* Option strategy constraints (allowed structures, max tenor)
* Alert thresholds and approval requirements

---

## 15) Next Step

Convert this architecture spec into:

1. a **component-level implementation plan** (repo structure, services, schemas), and
2. an **MVP strategy definition** (universe, signals, risk limits, execution rules), then
3. a **backtest harness** that enforces the same risk constraints as live trading.
