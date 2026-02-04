# Beavr AI Investor

## Architecture Guide

---

## What is Beavr AI Investor?

Beavr AI Investor is a **multi-agent autonomous trading system** that combines large language model (LLM) reasoning with quantitative trading strategies. It extends the existing Beavr automated trading platform to make intelligent, explainable investment decisions with minimal human oversight.

The system employs multiple specialized AI agents—each with distinct expertise—that collaborate to analyze markets, propose trades, manage risk, and execute orders. This mirrors how a professional trading desk operates, with analysts, traders, and risk managers working together.

### Key Capabilities

- **Autonomous Decision Making**: Generates trading signals through multi-agent deliberation
- **Multi-Asset Support**: Trades equities, ETFs, and cryptocurrencies
- **Risk-First Design**: Enforces hard constraints on drawdown, position sizing, and exposure
- **Explainability**: Every trade includes human-readable rationale
- **Pluggable Intelligence**: Supports multiple LLM providers (OpenAI, Anthropic, Ollama, etc.)
- **Backtesting Integration**: Uses existing Beavr engine for strategy validation

### Target Performance

| Metric | Goal | Enforcement |
|--------|------|-------------|
| Risk-Adjusted Returns | Sharpe ratio > 1.0 | Optimization target |
| Maximum Drawdown | < 20% | Circuit breakers (progressive) |
| Win Rate | > 45% on closed trades | Monitoring |
| Win/Loss Ratio | > 1.5:1 | Monitoring |

> **Important:** These are optimization goals based on backtesting, not guarantees. Actual performance will vary. This is experimental software, not financial advice. Past performance does not indicate future results.

---

## Key Concepts

### Agents

An **agent** is an autonomous component with specialized expertise. Each agent has a defined role, receives market context, and produces recommendations. Agents use LLMs for reasoning but operate within strict boundaries.

| Agent Type | Role | Output |
|------------|------|--------|
| Analyst | Assesses market conditions | Regime classification, risk posture |
| Trader | Identifies opportunities | Buy/sell signals with conviction |
| Sentinel | Guards against risk | Approval, modification, or rejection |

### Regime

The **regime** describes current market conditions. The system adjusts its behavior based on regime:

- **Bull**: Sustained uptrend, favorable for long positions
- **Bear**: Sustained downtrend, defensive posture
- **Sideways**: Range-bound, mean-reversion opportunities
- **Volatile**: High uncertainty, reduced position sizes

### Signals

A **signal** is a trading recommendation from an agent. Signals include:
- Symbol and action (buy/sell/hold)
- Conviction level (0-100%)
- Position sizing guidance
- Human-readable rationale

### Blackboard

The **blackboard** is shared memory where agents read and write information. It enables loose coupling—agents don't communicate directly but observe and contribute to shared state.

### Orchestrator

The **orchestrator** coordinates the multi-agent workflow. It triggers agents in sequence, manages timing, aggregates proposals, and produces final trading decisions.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                             │
│                              BEAVR AI INVESTOR                              │
│                                                                             │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                         USER INTERFACE                                │  │
│  │                                                                       │  │
│  │    CLI Commands    │    Daily Reports    │    Trade Explanations      │  │
│  └────────────────────────────────▲──────────────────────────────────────┘  │
│                                   │                                         │
│                            Decisions & Explanations                         │
│                                   │                                         │
│  ┌────────────────────────────────┴──────────────────────────────────────┐  │
│  │                         ORCHESTRATION LAYER                           │  │
│  │                                                                       │  │
│  │   ┌─────────────┐    ┌─────────────┐    ┌─────────────┐               │  │
│  │   │  Scheduler  │    │ Blackboard  │    │   Workflow  │               │  │
│  │   │             │    │  (Shared    │    │   Engine    │               │  │
│  │   │  Triggers   │───▶│   State)    │◀───│             │               │  │
│  │   │  daily/hourly    └─────────────┘    │  Sequences  │               │  │
│  │   └─────────────┘           ▲           └─────────────┘               │  │
│  │                             │                                          │  │
│  └─────────────────────────────┼──────────────────────────────────────────┘  │
│                                │                                             │
│                         Read/Write Context                                   │
│                                │                                             │
│  ┌─────────────────────────────┼──────────────────────────────────────────┐  │
│  │                     AGENT LAYER                                        │  │
│  │                             │                                          │  │
│  │   ┌─────────────────────────┴─────────────────────────────────────┐   │  │
│  │   │                                                                │   │  │
│  │   │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐        │   │  │
│  │   │  │    Market    │  │    Swing     │  │   Momentum   │        │   │  │
│  │   │  │   Analyst    │  │    Trader    │  │    Trader    │  ...   │   │  │
│  │   │  │              │  │              │  │              │        │   │  │
│  │   │  │  Regime &    │  │  Multi-day   │  │   Trend      │        │   │  │
│  │   │  │  Assessment  │  │  Positions   │  │   Following  │        │   │  │
│  │   │  └──────────────┘  └──────────────┘  └──────────────┘        │   │  │
│  │   │                                                                │   │  │
│  │   └────────────────────────────┬───────────────────────────────────┘   │  │
│  │                                │                                       │  │
│  │                          Proposals                                     │  │
│  │                                │                                       │  │
│  │   ┌────────────────────────────▼───────────────────────────────────┐  │  │
│  │   │                      SENTINEL (Risk Gate)                       │  │  │
│  │   │                                                                 │  │  │
│  │   │    Validates all proposals against risk constraints             │  │  │
│  │   │    Can approve, modify, or reject                               │  │  │
│  │   └────────────────────────────┬────────────────────────────────────┘  │  │
│  │                                │                                       │  │
│  └────────────────────────────────┼───────────────────────────────────────┘  │
│                                   │                                          │
│                           Approved Signals                                   │
│                                   │                                          │
│  ┌────────────────────────────────▼───────────────────────────────────────┐  │
│  │                         EXECUTION LAYER                                 │  │
│  │                                                                         │  │
│  │   Signal Processing  ──▶  Position Sizing  ──▶  Order Generation       │  │
│  │                                                                         │  │
│  └────────────────────────────────┬────────────────────────────────────────┘  │
│                                   │                                          │
│  ┌────────────────────────────────▼────────────────────────────────────────┐  │
│  │                     EXISTING BEAVR INFRASTRUCTURE                        │  │
│  │                                                                          │  │
│  │   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐   ┌────────────┐ │  │
│  │   │    Data     │   │  Backtest   │   │    Live     │   │  Database  │ │  │
│  │   │   (Alpaca)  │   │   Engine    │   │  Execution  │   │  (SQLite)  │ │  │
│  │   └─────────────┘   └─────────────┘   └─────────────┘   └────────────┘ │  │
│  │                                                                          │  │
│  └──────────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## How It Works

### Daily Decision Cycle

The system operates on a **daily decision cycle** optimized for swing trading and position management. This cycle runs once per trading day (or more frequently if configured).

```
    ┌─────────────────────────────────────────────────────────────────┐
    │                                                                 │
    │   1. DATA COLLECTION                                           │
    │   ────────────────────                                         │
    │   • Fetch latest OHLCV bars from Alpaca                        │
    │   • Calculate technical indicators (RSI, MACD, SMAs, etc.)     │
    │   • Retrieve current portfolio state                           │
    │   • Check current drawdown from peak                           │
    │                                                                 │
    └─────────────────────────────────┬───────────────────────────────┘
                                      │
                                      ▼
    ┌─────────────────────────────────────────────────────────────────┐
    │                                                                 │
    │   2. MARKET ANALYSIS                                           │
    │   ──────────────────                                           │
    │   • Market Analyst agent examines indicators                   │
    │   • Determines current regime (bull/bear/sideways/volatile)    │
    │   • Assesses overall risk level                                │
    │   • Recommends risk budget for the day                         │
    │                                                                 │
    └─────────────────────────────────┬───────────────────────────────┘
                                      │
                                      ▼
    ┌─────────────────────────────────────────────────────────────────┐
    │                                                                 │
    │   3. TRADING PROPOSALS  (Parallel)                             │
    │   ────────────────────────────────                             │
    │   • Swing Trader analyzes mean-reversion opportunities         │
    │   • Momentum Trader looks for trend continuation               │
    │   • Each agent produces signals with conviction scores         │
    │   • Agents operate independently using shared context          │
    │                                                                 │
    └─────────────────────────────────┬───────────────────────────────┘
                                      │
                                      ▼
    ┌─────────────────────────────────────────────────────────────────┐
    │                                                                 │
    │   4. RISK GATING                                               │
    │   ──────────────                                               │
    │   • Sentinel agent reviews all proposals                       │
    │   • Checks against position limits and exposure caps           │
    │   • Validates portfolio-level risk                             │
    │   • Approves, modifies, or rejects each signal                 │
    │                                                                 │
    └─────────────────────────────────┬───────────────────────────────┘
                                      │
                                      ▼
    ┌─────────────────────────────────────────────────────────────────┐
    │                                                                 │
    │   5. SIGNAL AGGREGATION                                        │
    │   ─────────────────────                                        │
    │   • Resolve conflicts (e.g., buy vs sell same symbol)          │
    │   • Prioritize by conviction and risk-adjusted potential       │
    │   • Generate final signal list                                 │
    │                                                                 │
    └─────────────────────────────────┬───────────────────────────────┘
                                      │
                                      ▼
    ┌─────────────────────────────────────────────────────────────────┐
    │                                                                 │
    │   6. POSITION SIZING (Deterministic)                           │
    │   ──────────────────────────────────                           │
    │   • Calculate position size using volatility (ATR)             │
    │   • Apply regime multiplier and drawdown adjustment            │
    │   • This is MATH, not LLM reasoning                            │
    │                                                                 │
    └─────────────────────────────────┬───────────────────────────────┘
                                      │
                                      ▼
    ┌─────────────────────────────────────────────────────────────────┐
    │                                                                 │
    │   7. EXECUTION                                                 │
    │   ───────────                                                  │
    │   • Convert sized signals to orders                            │
    │   • Use limit orders (not market orders)                       │
    │   • Execute via Beavr's existing infrastructure                │
    │   • Log all decisions with explanations                        │
    │                                                                 │
    └─────────────────────────────────────────────────────────────────┘
```

### Information Flow

```
                     ┌─────────────────┐
                     │   Market Data   │
                     │   (Alpaca API)  │
                     └────────┬────────┘
                              │
                              ▼
                     ┌─────────────────┐
                     │   Indicators    │
                     │   Calculator    │
                     └────────┬────────┘
                              │
              ┌───────────────┼───────────────┐
              │               │               │
              ▼               ▼               ▼
       ┌────────────┐  ┌────────────┐  ┌────────────┐
       │   Market   │  │   Swing    │  │  Momentum  │
       │  Analyst   │  │   Trader   │  │   Trader   │
       └─────┬──────┘  └─────┬──────┘  └─────┬──────┘
             │               │               │
             │    ┌──────────┴───────────┐   │
             │    │                      │   │
             ▼    ▼                      ▼   ▼
       ┌─────────────┐            ┌─────────────┐
       │  Regime &   │            │   Trading   │
       │ Risk Budget │            │   Signals   │
       └──────┬──────┘            └──────┬──────┘
              │                          │
              └────────────┬─────────────┘
                           │
                           ▼
                    ┌─────────────┐
                    │  Sentinel   │
                    │ (Risk Gate) │
                    └──────┬──────┘
                           │
                           ▼
                    ┌─────────────┐
                    │  Position   │   ← DETERMINISTIC
                    │   Sizing    │     (not LLM)
                    │   Engine    │
                    └──────┬──────┘
                           │
                           ▼
                    ┌─────────────┐
                    │  Execution  │
                    │   Engine    │
                    └─────────────┘
```

### Key Design Principle: LLM as Advisor, Not Executor

The LLM agents decide **WHAT** to trade. Deterministic code decides **HOW MUCH**.

```
  PROBABILISTIC (LLM)                    DETERMINISTIC (Code)
  ───────────────────                    ────────────────────
  
  • Regime classification                • Position sizing
  • Signal generation                    • Risk calculations
  • Pattern recognition                  • Order execution
  • Explainability                       • Circuit breakers
```

This separation ensures that even if an LLM hallucinates high conviction, the position sizing engine will limit exposure based on volatility and current drawdown.

---

## Components

### Orchestrator

The **Orchestrator** is the central coordinator that manages the multi-agent workflow.

**Responsibilities:**
- Triggers the daily decision cycle on schedule
- Manages the blackboard (shared state)
- Sequences agent execution (analysis → proposals → risk → aggregation)
- Handles timeouts and failures gracefully
- Produces audit logs for every decision

**Workflow Management:**

The orchestrator ensures agents run in the correct order. Market analysis must complete before trading agents run, as they depend on regime classification. Trading agents run in parallel for efficiency, while the Sentinel runs last to gate all proposals.

**Failure Handling:**

If any agent fails or times out:
1. The orchestrator logs the failure
2. Falls back to conservative defaults (hold existing positions)
3. Alerts the user via the daily report
4. Does not execute trades with incomplete analysis

---

### Agents

#### Market Analyst

The **Market Analyst** assesses overall market conditions before any trading decisions are made.

**Inputs:**
- Price bars for all tracked symbols
- Technical indicators (RSI, MACD, moving averages, Bollinger Bands)
- Volume patterns
- Recent price changes

**Analysis Process:**
1. Evaluates trend direction (price vs. key moving averages)
2. Assesses momentum (RSI, MACD signals)
3. Measures volatility (ATR, Bollinger Band width)
4. Synthesizes into regime classification

**Outputs:**
- **Regime**: Bull, Bear, Sideways, or Volatile
- **Confidence**: 0-100% certainty in classification
- **Risk Posture**: Recommended risk budget (0-100%)
- **Key Observations**: Notable patterns detected
- **Risk Factors**: Current concerns

**Impact on System:**

The regime classification affects all downstream decisions:

| Regime | Risk Budget | Trading Behavior |
|--------|-------------|------------------|
| Bull | 80-100% | Full position sizes, trend following |
| Sideways | 50-70% | Mean reversion focus, moderate sizes |
| Bear | 20-40% | Defensive, smaller positions |
| Volatile | 10-30% | Minimal new positions, protect capital |

---

#### Swing Trader

The **Swing Trader** identifies multi-day position opportunities based on technical setups.

**Trading Style:**
- Holding period: 3-10 trading days
- Focus: Mean reversion, support/resistance, pullback entries
- Risk: 3-5% stop loss per position

**Entry Conditions (examples):**
- RSI below 30 (oversold) with price at support
- Price pulling back to 20-day SMA in uptrend
- Bounce from lower Bollinger Band

**Exit Conditions:**
- Price reaches take-profit target (2:1 or 3:1 risk/reward)
- Stop loss triggered
- Thesis invalidated (e.g., trend reversal)

**Output:**
- Symbol and action (buy/sell)
- Conviction score
- Entry price, stop loss, take profit levels
- Position size recommendation
- Rationale explaining the setup

---

#### Momentum Trader

The **Momentum Trader** follows trends and breakouts for trend-continuation opportunities.

**Trading Style:**
- Holding period: Days to weeks
- Focus: Breakouts, relative strength, sector rotation
- Risk: Trailing stops, let winners run

**Entry Conditions (examples):**
- Price breaking above resistance with volume
- Relative strength vs. benchmark (SPY) improving
- Sector showing leadership

**Output:**
- Similar structure to Swing Trader
- Emphasis on trend strength and continuation probability

---

#### Sentinel (Risk Gate)

The **Sentinel** is the final checkpoint before any trade executes. It enforces risk constraints that are non-negotiable.

**Hard Constraints:**

| Constraint | Default | Purpose |
|------------|---------|---------|
| Max Position Size | 10% of portfolio | Prevent concentration |
| Max Sector Exposure | 30% of portfolio | Diversification |
| Max Correlation | 0.6-0.8 (regime-adjusted) | Avoid hidden concentration |
| Min Cash Reserve | 5% of portfolio | Liquidity buffer |
| Max 1-Day VaR (95%) | 3% of portfolio | Tail risk control |

**Review Process:**

For each proposed signal, the Sentinel:
1. Calculates post-trade position sizes
2. Checks sector and correlation exposure
3. Estimates impact on portfolio VaR
4. Validates against all constraints

**Possible Responses:**
- **Approve**: Trade passes all checks
- **Modify**: Reduce position size to fit constraints
- **Reject**: Trade violates hard limits

**Circuit Breakers (Progressive De-risking):**

Unlike a binary "kill switch," the system progressively reduces risk:

| Drawdown | Action |
|----------|--------|
| 10% | Reduce new position sizes by 50% |
| 15% | No new positions, tighten stops on existing |
| 20% | Reduce all positions to 50% over 4 hours (not instant) |

> **Why progressive?** Flattening all positions instantly during a crash means selling into a liquidity vacuum—you'll execute at far worse prices than the current quote. Gradual de-risking is safer.

---

### LLM Layer (GitHub Copilot SDK)

For MVP, the system uses the official [GitHub Copilot Python SDK](https://github.com/github/copilot-sdk/tree/main/python) exclusively. This simplifies setup—no API keys to manage, no cloud infrastructure to configure.

**Prerequisites:**
- GitHub Copilot CLI installed and authenticated
- Python 3.9+

**Why Copilot SDK for MVP:**

| Benefit | Description |
|---------|-------------|
| Zero setup | Works with existing GitHub Copilot subscription |
| No API keys | Authentication handled by Copilot CLI |
| Quality models | Access to GPT-4.1, Claude Sonnet 4.5, and other models |
| Cost included | No per-token billing to manage |
| Native Python | First-class Python SDK with async/await support |

> **Future:** Post-MVP, we may add support for other providers (OpenAI direct, Anthropic, Ollama) for users who need specific models or want to run locally.

**How Agents Use Copilot SDK:**

Agents use the SDK's tools feature for structured output:

```
┌─────────────┐     create_session()    ┌─────────────┐
│             │      + tools            │             │
│    Agent    │ ─────────────────────▶ │   Copilot   │
│             │                         │     SDK     │
│             │     session.send()      │             │
│             │   (Market Context)      │             │
│             │ ─────────────────────▶ │             │
│             │                         │             │
│             │ ◀───────────────────── │             │
│             │   Tool call with        │             │
│             │   Pydantic model        │             │
└─────────────┘                         └─────────────┘
```

**Structured Output via Tools:**

The SDK uses `@define_tool` with Pydantic models for structured output:

```python
from copilot import CopilotClient, define_tool
from pydantic import BaseModel, Field

class MarketAnalysis(BaseModel):
    regime: str = Field(description="bull, bear, sideways, volatile")
    confidence: float = Field(ge=0.0, le=1.0)
    risk_factors: list[str]

@define_tool(description="Return your market analysis")
async def return_analysis(params: MarketAnalysis) -> str:
    # SDK validates params against Pydantic schema automatically
    return "Analysis recorded"

session = await client.create_session({
    "model": "gpt-4.1",
    "tools": [return_analysis],
})
```

This ensures:
- Guaranteed schema compliance (Pydantic validation)
- Type safety with Python type hints
- Graceful handling of malformed responses

---

### Position Sizing Engine (Deterministic)

The **Position Sizing Engine** is a critical non-LLM component that calculates how much to trade. This is pure math—no AI reasoning.

**Why Separate from LLM?**

An LLM might output high conviction for a trade based on pattern recognition. But if volatility is high or we're already in drawdown, we must size down regardless of conviction. This logic must be deterministic, not probabilistic.

**Inputs:**
- Signal (symbol, direction, conviction from LLM)
- Current ATR (14-period Average True Range)
- Portfolio value
- Current drawdown from peak
- Regime risk budget

**Position Sizing Formula:**

```
base_risk_per_trade = 2% of portfolio

regime_multiplier:
  bull     = 1.0
  sideways = 0.7
  bear     = 0.4
  volatile = 0.3

drawdown_multiplier = max(0.3, 1.0 - current_drawdown × 2)

effective_risk = base_risk × regime_multiplier × drawdown_multiplier × conviction

position_value = (effective_risk × portfolio_value) / ATR_as_percentage
```

**Example:**

```
Portfolio: $100,000
Signal: Buy AAPL, conviction 0.8
Regime: Sideways (multiplier 0.7)
Drawdown: 5% (multiplier 0.9)
AAPL ATR: 2.5%

effective_risk = 0.02 × 0.7 × 0.9 × 0.8 = 1.008%
position_value = (0.01008 × 100,000) / 0.025 = $40,320
```

**Hard Caps (always enforced):**
- Max 10% of portfolio per position
- Max 30% of portfolio per sector
- Min 5% cash reserve

---

### Transaction Cost Model

The system models realistic trading costs in both backtesting and live trading.

| Component | Equities | Crypto |
|-----------|----------|--------|
| Spread | 0.02% | 0.10% |
| Slippage | 0.05% | 0.10% |
| Market impact (>$10K) | 0.03% | 0.05% |
| **Total round-trip** | **~0.15%** | **~0.30%** |

These costs are deducted from backtest returns and factored into live order pricing (e.g., limit orders set inside the spread).

---

### Blackboard (Shared State)

The **Blackboard** enables loose coupling between agents. Instead of direct communication, agents read from and write to shared state.

**Contents:**

| Key | Written By | Read By | Purpose |
|-----|------------|---------|---------|
| `market_analysis` | Market Analyst | All traders | Regime and risk context |
| `trading_proposals` | Trading agents | Sentinel, Orchestrator | Raw signals |
| `approved_signals` | Sentinel | Execution | Final trade list |
| `portfolio_state` | System | All agents | Current positions |
| `cycle_summary` | Orchestrator | Reporting | Audit trail |

**Benefits:**
- Agents can be added/removed without changing others
- Easy to inspect system state for debugging
- Natural audit trail of decision process
- Supports replay for backtesting

---

## Integration with Existing Beavr

The AI Investor is designed as an **extension** of Beavr, not a replacement. It reuses existing infrastructure while adding intelligent decision-making.

### Compatibility Layer

The AI system implements Beavr's existing `BaseStrategy` interface:

```
┌───────────────────────────────────────────────────────────────┐
│                     BEAVR STRATEGY INTERFACE                   │
│                                                                │
│   All strategies implement:                                    │
│   • symbols: list of assets to trade                          │
│   • evaluate(context) → signals                               │
│                                                                │
├───────────────────────────────────────────────────────────────┤
│                                                                │
│  ┌─────────────────┐  ┌─────────────────┐  ┌───────────────┐  │
│  │   Simple DCA    │  │   Dip Buy DCA   │  │ AI Multi-Agent│  │
│  │                 │  │                 │  │               │  │
│  │  Rule-based     │  │  Rule-based     │  │  LLM-powered  │  │
│  │  Fixed schedule │  │  Dip detection  │  │  Intelligent  │  │
│  └─────────────────┘  └─────────────────┘  └───────────────┘  │
│                                                                │
│         All strategies use the same interface                  │
│         and can be backtested with the same engine            │
│                                                                │
└───────────────────────────────────────────────────────────────┘
```

**What's Reused:**
- Backtest engine (no changes needed)
- Data layer (Alpaca integration)
- Database (SQLite for bar cache and results)
- CLI infrastructure
- Signal and Trade models

**What's Added:**
- Agent layer (LLM-powered reasoning)
- Orchestrator (multi-agent coordination)
- LLM provider abstraction
- Risk management module

### Running AI Strategies

AI strategies are configured and run like any other Beavr strategy:

```bash
# Backtest
bvr backtest --strategy ai_multi_agent --config ai_config.toml

# Paper trading
bvr paper --strategy ai_multi_agent --config ai_config.toml

# Live trading
bvr live --strategy ai_multi_agent --config ai_config.toml
```

---

## Configuration

### Strategy Configuration

All configuration is done via TOML files, consistent with existing Beavr patterns.

**Structure:**

```toml
[strategy]
name = "ai_multi_agent"

[params]
symbols = ["SPY", "QQQ", "AAPL", ...]     # Universe

[params.risk]                              # Risk constraints
max_drawdown = 0.20
max_position_pct = 0.10

[params.agents]                            # Agent selection
enabled = ["market_analyst", "swing_trader"]

[params.llm]                               # Copilot SDK settings
model = "gpt-4.1"
streaming = false
```

### LLM Configuration

For MVP, LLM configuration maps to Copilot SDK session options:

```toml
[params.llm]
model = "gpt-4.1"              # Model: gpt-4.1, gpt-5, claude-sonnet-4.5, etc.
streaming = false              # Enable streaming responses
reasoning_effort = "medium"    # For reasoning models: low, medium, high, xhigh
```

**Available Models (via Copilot SDK):**
- `gpt-4.1` - Default, good balance of speed and quality
- `gpt-5` - Latest OpenAI model
- `claude-sonnet-4.5` - Anthropic Claude

No API keys required—Copilot SDK authenticates via GitHub Copilot CLI.

---

## Operational Considerations

### Latency Budget

The system is designed for daily decisions, not high-frequency trading.

| Component | Typical Latency | Budget |
|-----------|-----------------|--------|
| Data fetch | 1-2 seconds | 5 seconds |
| Indicator calculation | < 100ms | 1 second |
| Market Analyst (LLM) | 2-5 seconds | 30 seconds |
| Trading Agents (parallel) | 2-5 seconds | 30 seconds |
| Risk gating | < 500ms | 5 seconds |
| **Total cycle** | **~10 seconds** | **< 2 minutes** |

### Cost Estimation

For MVP using Copilot SDK:

| Component | Cost |
|-----------|------|
| Copilot SDK | Included with GitHub Copilot subscription |
| Alpaca Data | Free tier available |
| Infrastructure | Your machine only |

No per-token LLM costs for MVP.

### Failure Modes & Circuit Breakers

The system uses circuit breakers to handle failures gracefully without catastrophic decisions.

**LLM Provider Circuit Breaker:**

| State | Trigger | Behavior |
|-------|---------|----------|
| **Healthy** | Response < 10s | Normal operation |
| **Degraded** | 3 consecutive > 15s | Use cached regime, reduce position sizes |
| **Open** | 5 consecutive failures | Rule-based fallback for 5 minutes |
| **Recovering** | 1 success after open | Back to degraded, then healthy |

**Failure Response Matrix:**

| Failure | Detection | Response |
|---------|-----------|----------|
| LLM timeout (>30s) | Request timeout | Use cached analysis, skip agent |
| LLM parse error | Schema validation | Auto-retry with `instructor`, then skip |
| LLM unavailable (>5min) | Circuit open | Hold positions, no new trades, alert user |
| Data stale (>2min equities) | Timestamp check | Halt trading, cancel open orders |
| Data stale (>30s crypto) | Timestamp check | Halt crypto trading only |
| Drawdown 10% | Portfolio monitoring | Reduce new position sizes 50% |
| Drawdown 15% | Portfolio monitoring | No new positions, tighten stops |
| Drawdown 20% | Portfolio monitoring | Reduce positions to 50% over 4 hours |

**Why not instant flatten at 20%?**

In a market crash, liquidity disappears. If you market-sell everything when you hit -20% drawdown, you'll actually execute at -30% or worse due to slippage. Progressive de-risking over 4 hours is safer.

---

## Security Considerations

### API Key Management

- Store API keys in environment variables, never in config files
- Use `api_key_env` parameter to reference environment variable names
- Support for secret managers in enterprise deployments

### Data Privacy

- **Cloud LLMs**: Market data and portfolio state sent to provider
- **Local LLMs (Ollama)**: All data stays on your machine
- No PII is sent to LLMs (only symbols, prices, indicators)

### Audit Trail

All decisions are logged with:
- Timestamp
- Agent proposals
- Risk gate decisions
- Final signals
- LLM request/response summaries (sanitized)

---

## Extensibility

### Adding New Agents

New agents can be added by implementing the agent interface:

1. Define the agent's role and expertise
2. Create system prompt (persona)
3. Define output schema
4. Register with orchestrator

Agents are loosely coupled via the blackboard, so adding agents doesn't require modifying existing ones.

### Adding New LLM Providers

New providers can be added by implementing the provider interface:

1. Implement `reason()` for structured output
2. Implement `complete()` for text generation
3. Handle provider-specific authentication
4. Register in provider factory

### Custom Risk Rules

Risk constraints can be extended:
- Add new constraint types to Sentinel
- Create custom kill switch thresholds
- Implement portfolio-specific rules

---

## Limitations

### What This System Is NOT

- **Not HFT**: Designed for daily/hourly decisions, not millisecond trading
- **Not Guaranteed**: Target returns are goals, not promises
- **Not Autonomous Forever**: Requires periodic human review
- **Not a Black Box**: All decisions are explainable

### Current Limitations

- **Single Exchange**: Currently Alpaca only (future: multiple brokers)
- **No Options Yet**: Equities and crypto only (options planned)
- **English Only**: LLM prompts and outputs in English

---

## Glossary

| Term | Definition |
|------|------------|
| Agent | Autonomous component with specialized expertise |
| Blackboard | Shared state container for agent communication |
| Conviction | Agent's confidence in a trading signal (0-100%) |
| Kill Switch | Automatic position flattening on drawdown breach |
| Orchestrator | Central coordinator for multi-agent workflow |
| Provider | LLM service implementation (OpenAI, Anthropic, etc.) |
| Regime | Market condition classification (bull/bear/sideways/volatile) |
| Sentinel | Risk management agent that gates all proposals |
| Signal | Trading recommendation from an agent |

---

## Related Documentation

- [Implementation Guide](./IMPLEMENTATION.md) — Code-level details and examples
- [Architecture Decision Records](./ADR.md) — Design decisions and rationale
- [ChatGPT Plan](./CHATGPT_PLAN.md) — Original detailed specification
- [Research](./RESEARCH.md) — Background on AI investor systems

---

*Document Version: 1.0.0*  
*Last Updated: February 2026*
