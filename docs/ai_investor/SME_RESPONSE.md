# SME Feedback Analysis & Architecture Response

This document analyzes the critical feedback received from SMEs and documents our architectural decisions in response.

---

## Executive Summary

Both SME reviews raise valid concerns. After careful analysis:

- **12 items**: Accept and will address in architecture
- **4 items**: Partially accept with modifications  
- **2 items**: Respectfully decline with justification

The feedback correctly identifies that we've over-indexed on the "intelligence" layer and under-indexed on the "risk infrastructure" layer. This document outlines the architectural changes required.

---

## Feedback Analysis

### 🟢 ACCEPTED — Will Address

| # | Feedback | Source | Why We Accept | Architectural Response |
|---|----------|--------|---------------|----------------------|
| 1 | **Non-determinism breaks testing** | Both | LLMs are probabilistic. CI/CD cannot rely on live API calls. | Add VCR/replay testing framework. Pin model versions. Log all prompts/responses. |
| 2 | **Structured output fragility** | SME1 | JSON hallucination is real. Schema violations will corrupt blackboard. | Add `instructor` library for guaranteed schema compliance. Retry with backoff. Fail-safe on parse errors. |
| 3 | **Missing observability** | SME2 | Cannot debug/improve what we cannot measure. | Add OpenTelemetry integration. Track token usage, latency percentiles, decision drift. |
| 4 | **No transaction cost model** | SME2 | Backtests without costs are fantasy. 10-30bps round-trip destroys swing trading edge. | Add slippage model (spread + market impact). Apply in backtest AND live. |
| 5 | **Kill switch sells at worst prices** | Both | Flattening at -20% during a crash means executing at -30%+ due to liquidity vacuum. | Replace percentage-based kill switch with VaR/CVaR limits. Add circuit breaker that reduces position sizing progressively, not binary flatten. |
| 6 | **Position sizing is ex-post, not ex-ante** | SME1 | Stop losses don't protect you. Position sizing before entry does. | LLM generates *signals only*. Deterministic Python calculates position size using volatility-adjusted formula (simplified Kelly or ATR-based). |
| 7 | **Execution logic is amateur** | SME1 | "Market Buy" for illiquid assets is unacceptable. | Add execution strategies: Limit orders with timeout → TWAP fallback. Never market orders except for kill switch. |
| 8 | **No prompt injection defense** | SME2 | If we add news/fundamentals, malicious content could manipulate agents. | Sanitize all external inputs. Separate "data" from "instructions" in prompts. Add input validation layer. |
| 9 | **Timeout cascades** | SME2 | 30s × N agents during API degradation = stale decisions. | Add circuit breakers per provider. Cache last-known-good analysis. Fallback to rule-based signals if LLM unavailable for >60s. |
| 10 | **Schema evolution** | SME2 | Pydantic schemas will change. No versioning = breaking changes. | Version all output schemas. Store schema version with logged decisions. Add backward compatibility layer. |
| 11 | **Regulatory/liability language** | SME2 | "2× SPY" reads as a promise, not a goal. | Remove specific return targets from user-facing docs. Add explicit disclaimers: "Experimental. Not financial advice. Past performance ≠ future results." |
| 12 | **Walk-forward validation missing** | SME2 | Backtesting on training data = guaranteed overfitting. | Implement strict train/test separation. Walk-forward with rolling windows. Minimum 90-day paper trading gate before live. |

---

### 🟡 PARTIALLY ACCEPTED — With Modifications

| # | Feedback | Source | Our Position | Architectural Response |
|---|----------|--------|--------------|----------------------|
| 1 | **Regime model is naive (4 regimes)** | SME2 | Partially agree. 4 regimes is a starting point, not the final answer. But adding 12 regime types increases complexity and LLM hallucination risk. | Keep 4 primary regimes. Add **sub-indicators** (sector rotation score, VIX level, credit spread) as context. Let the LLM reason about nuance within regimes rather than classifying into more buckets. |
| 2 | **Correlation limit 0.8 is too loose** | SME2 | Agree it's loose in crisis, but 0.5 would reject most equity portfolios in normal markets. | Dynamic correlation limits: 0.8 in Bull/Sideways, 0.6 in Bear/Volatile. Add **realized correlation monitoring** that tightens automatically when cross-asset correlation spikes. |
| 3 | **Alpha decay from consensus LLMs** | SME1 | Valid for "sentiment" signals. Less valid for technical pattern recognition. We're not asking the LLM "should I buy NVDA?" — we're asking "is RSI oversold at support?" | Document clearly: LLM is a *pattern recognition and reasoning* layer, not an alpha source. Alpha comes from the trading rules + risk management. LLM provides explainability and regime-awareness. |
| 4 | **Crypto 24/7 blind spot** | SME2 | Valid. Daily cycle misses 16+ hours of volatility. But intraday monitoring adds significant complexity and cost. | For Phase 1: Crypto positions capped at 10% of portfolio. Add "overnight risk" penalty to crypto signals. Phase 2: Optional intraday check at market midpoint for crypto-heavy portfolios. |

---

### 🔴 DECLINED — With Justification

| # | Feedback | Source | Why We Decline |
|---|----------|--------|----------------|
| 1 | **"Regime detection is impossible, LLMs can't do it"** | SME1 | **Respectfully disagree with the absolutism.** We're not asking the LLM to predict the future. We're asking it to classify *current conditions* based on observable data (price vs. SMAs, RSI, volatility). This is pattern recognition, not prophecy. A 60% accurate regime classifier + conservative position sizing is better than no regime awareness. We'll validate with historical backtests on crisis periods. If it fails, we'll know. |
| 2 | **"No factor exposure control"** | SME2 | **Deferred, not declined.** For a retail investor with $50-200K, factor exposure tracking (beta, momentum, size, value) adds complexity without proportional benefit. The position limits (10% per name, 30% per sector) provide sufficient diversification. We'll add factor tracking in Phase 3 when/if we support larger portfolios or institutional users. |

---

## Revised Architecture Principles

Based on accepted feedback, we're adding these principles:

### Principle: LLM is Advisor, Not Executor

```
┌─────────────────────────────────────────────────────────────────┐
│                         DECISION FLOW                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   LLM Agents                    Deterministic Layer             │
│   ──────────                    ───────────────────             │
│                                                                 │
│   ┌─────────────┐               ┌─────────────────┐             │
│   │   Market    │               │                 │             │
│   │  Analyst    │──── Regime ──▶│                 │             │
│   └─────────────┘               │                 │             │
│                                 │   Position      │             │
│   ┌─────────────┐               │   Sizing        │             │
│   │   Swing     │── Signal ────▶│   Engine        │── Orders ──▶│
│   │   Trader    │  (direction   │                 │             │
│   └─────────────┘   + conviction)│  (volatility-  │             │
│                                 │   adjusted,     │             │
│   ┌─────────────┐               │   deterministic)│             │
│   │  Sentinel   │── Approval ──▶│                 │             │
│   └─────────────┘               └─────────────────┘             │
│                                                                 │
│   PROBABILISTIC                 DETERMINISTIC                   │
│   (reasoning)                   (math)                          │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**The LLM decides WHAT to trade. Deterministic code decides HOW MUCH.**

### Principle: Progressive Degradation

```
┌─────────────────────────────────────────────────────────────────┐
│                    FAILURE HANDLING LADDER                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   Normal Operation                                              │
│   ────────────────                                              │
│   Full LLM analysis → Position sizing → Execution               │
│                                                                 │
│   LLM Timeout (>30s)                                            │
│   ──────────────────                                            │
│   Use cached regime → Rule-based signals → Reduced sizes        │
│                                                                 │
│   LLM Unavailable (>5min)                                       │
│   ─────────────────────────                                     │
│   Hold existing positions → No new trades → Alert user          │
│                                                                 │
│   Data Stale (>2min for equities, >30s for crypto)              │
│   ──────────────────────────────────────────────────            │
│   Halt trading → Close open orders → Alert user                 │
│                                                                 │
│   Drawdown Breach                                               │
│   ───────────────                                               │
│   10%: Reduce new position sizes by 50%                         │
│   15%: No new positions, tighten stops on existing              │
│   20%: Reduce all positions to 50% over 4 hours (not instant)   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Principle: Defense in Depth for Risk

```
┌─────────────────────────────────────────────────────────────────┐
│                    RISK LAYERS (Revised)                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   Layer 0: POSITION SIZING (Ex-Ante) ← NEW                      │
│   ─────────────────────────────────────                         │
│   • Volatility-adjusted: Position = Risk% / ATR                 │
│   • Max 2% portfolio risk per trade                             │
│   • Calculated BEFORE order, not by LLM                         │
│                                                                 │
│   Layer 1: SENTINEL AGENT (LLM-based)                           │
│   ─────────────────────────────────────                         │
│   • Reviews signals for logical consistency                     │
│   • Checks correlation with existing positions                  │
│   • Can reject or reduce conviction                             │
│                                                                 │
│   Layer 2: HARD CONSTRAINTS (Rule-based)                        │
│   ────────────────────────────────────────                      │
│   • Max 10% per position                                        │
│   • Max 30% per sector                                          │
│   • Dynamic correlation limits (regime-adjusted)                │
│   • 5% cash reserve                                             │
│                                                                 │
│   Layer 3: CIRCUIT BREAKERS                                     │
│   ─────────────────────────                                     │
│   • VaR limit (95% 1-day VaR < 3% of portfolio)                │
│   • Intraday drawdown monitoring                                │
│   • Progressive de-risking (not binary flatten)                 │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## New Components Required

Based on feedback, these components must be added to the architecture:

### 1. Position Sizing Engine (Deterministic)

Calculates position sizes using volatility, NOT LLM output.

**Inputs:**
- Signal (symbol, direction, conviction)
- Current ATR (14-period)
- Portfolio value
- Current drawdown
- Regime risk budget

**Formula:**
```
base_risk = 0.02 (2% of portfolio per trade)
regime_multiplier = {bull: 1.0, sideways: 0.7, bear: 0.4, volatile: 0.3}
drawdown_multiplier = max(0.3, 1.0 - current_drawdown * 2)

risk_per_trade = base_risk × regime_multiplier × drawdown_multiplier × conviction
position_value = (risk_per_trade × portfolio_value) / ATR_percentage
```

### 2. Transaction Cost Model

Applied in backtesting AND live trading.

| Component | Estimate |
|-----------|----------|
| Spread (equities) | 0.02% |
| Spread (crypto) | 0.10% |
| Slippage | 0.05% |
| Market impact (>$10K orders) | 0.03% |
| **Total round-trip** | **0.15-0.30%** |

### 3. VCR Testing Framework

Records and replays LLM interactions for deterministic testing.

**Recording Mode:**
- Log full prompt + response + model version + timestamp
- Store in SQLite alongside backtest results

**Replay Mode:**
- Match prompts to recorded responses
- Fail if prompt doesn't match (indicates code change)
- CI runs in replay mode only

### 4. Circuit Breaker System

Prevents cascade failures during API degradation.

| Provider State | Trigger | Action |
|----------------|---------|--------|
| Healthy | Response < 10s | Normal operation |
| Degraded | 3 consecutive >15s responses | Switch to cached analysis |
| Open | 5 consecutive failures | Use rule-based fallback for 5 min |
| Recovering | 1 success after open | Back to degraded, then healthy |

### 5. Observability Stack

Metrics to track:

| Metric | Purpose |
|--------|---------|
| `llm_request_latency_p99` | Detect API degradation |
| `llm_tokens_per_cycle` | Cost monitoring |
| `regime_changes_per_week` | Detect regime instability |
| `signal_accuracy_30d` | Track if signals lead to profit |
| `drawdown_current` | Real-time risk monitoring |
| `correlation_matrix_max` | Detect concentration risk |

---

## Updated Target Performance

Per SME feedback, we're changing how we communicate targets:

### Before (Problematic)
> "Target: 2× SPY returns with <20% max drawdown"

### After (Honest)
> **Performance Goals** (not guarantees):
> - Risk-adjusted returns: Sharpe ratio > 1.0
> - Maximum drawdown: < 20% (hard limit via circuit breakers)
> - Win rate: > 45% on closed trades
> - Average win/loss ratio: > 1.5:1
>
> **Important:** These are optimization targets based on backtesting. Actual performance will vary. This is experimental software, not financial advice.

---

## Implementation Priority

Based on risk-adjusted impact:

| Priority | Item | Rationale |
|----------|------|-----------|
| P0 | Position sizing engine | Without this, entire risk model is broken |
| P0 | Transaction cost model | Backtests are meaningless without it |
| P0 | Disclaimer/language changes | Legal/liability risk |
| P1 | VCR testing framework | Required for CI/CD |
| P1 | Circuit breakers | Required for production stability |
| P1 | Progressive de-risking | Kill switch is dangerous as designed |
| P2 | Observability | Required before production, not for backtest |
| P2 | Schema versioning | Required before production |
| P3 | Dynamic correlation limits | Enhancement, not blocker |
| P3 | Execution strategies (TWAP) | Enhancement for larger orders |

---

## Conclusion

The SME feedback was invaluable. It correctly identified that we built a sophisticated reasoning system but forgot that **risk management is math, not reasoning**.

Key architectural changes:
1. **LLM scope reduced**: Signals and explanations only, not position sizing
2. **Deterministic layer added**: Position sizing, execution, risk limits
3. **Kill switch redesigned**: Progressive de-risking, not binary flatten
4. **Testing strategy**: VCR replay for determinism
5. **Honest communication**: Goals, not promises

The system is still ambitious, but now it's *responsibly* ambitious.

---

*Analysis completed: February 2026*
