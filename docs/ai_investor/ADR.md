# Beavr AI Investor: Architecture Decision Records

This document captures the key architectural decisions for the AI Investor system, including alternatives considered and rationale.

---

## ADR-001: LLM Provider Architecture

### Status: DECIDED

### Context
We need LLM capabilities for intelligent agent reasoning. Options include:
1. Single provider (locked to one service)
2. Pluggable provider architecture (abstraction layer)

### Decision
**Use pluggable LLM provider architecture** with an abstract `LLMProvider` interface.

### Rationale

| Provider | Pros | Cons | Best For |
|----------|------|------|----------|
| **OpenAI** | Best models, reliable, function calling | Cost per token | Production |
| **Anthropic** | Strong reasoning, large context | Cost per token | Complex analysis |
| **Copilot SDK** | No extra setup for Copilot users | Tied to GitHub | Quick start |
| **Ollama** | Free, private, offline | GPU required, lower quality | Privacy, offline |
| **Azure OpenAI** | Enterprise compliance | Setup complexity | Enterprise |

**Architecture:**
```python
class LLMProvider(ABC):
    @abstractmethod
    async def reason(self, system_prompt, user_prompt, output_schema) -> T:
        pass

# Implementations
class OpenAIProvider(LLMProvider): ...
class AnthropicProvider(LLMProvider): ...
class OllamaProvider(LLMProvider): ...
class CopilotProvider(LLMProvider): ...

# Factory
def create_provider(config: LLMConfig) -> LLMProvider:
    return providers[config.provider](config)
```

**Key factors:**
- Users may have different provider preferences/access
- Cost optimization (use cheaper models for simple tasks)
- Privacy requirements may mandate local models
- Enterprise may require Azure for compliance
- Provider landscape is evolving rapidly

### Consequences
- Positive: Flexibility, cost optimization, future-proof
- Positive: Can use local models for privacy-sensitive deployments
- Positive: Easy to add new providers as they emerge
- Negative: Slight abstraction overhead
- Negative: Need to test across multiple providers
- Mitigation: Comprehensive provider tests, fallback logic

---

## ADR-002: Agent Architecture Pattern

### Status: DECIDED

### Context
Multi-agent systems can be structured in several ways:
1. Hierarchical (manager → workers)
2. Peer-to-peer (agents communicate directly)
3. Blackboard (shared state, loose coupling)
4. Pipeline (sequential processing)

### Decision
**Use Blackboard pattern** with orchestrator coordination.

### Rationale

```
┌─────────────────────────────────────────────────────────────┐
│                       ORCHESTRATOR                           │
│   (coordinates timing, triggers, aggregation)               │
└────────────────────────────┬────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────┐
│                        BLACKBOARD                            │
│   (shared state: market analysis, proposals, decisions)     │
└──────┬──────────────┬───────────────┬──────────────┬────────┘
       │              │               │              │
       ▼              ▼               ▼              ▼
   ┌───────┐    ┌───────────┐   ┌──────────┐   ┌──────────┐
   │Market │    │  Swing    │   │Momentum  │   │ Sentinel │
   │Analyst│    │  Trader   │   │ Trader   │   │  (Risk)  │
   └───────┘    └───────────┘   └──────────┘   └──────────┘
```

**Why Blackboard:**
- Agents are loosely coupled (can add/remove easily)
- Shared state is observable for debugging
- Natural fit for async parallel execution
- Well-documented pattern in AI systems

**Why not others:**
- Hierarchical: Too rigid, hard to extend
- Peer-to-peer: Complex communication, hard to debug
- Pipeline: Doesn't support parallel agent analysis

### Consequences
- Positive: Extensibility, debuggability, parallel execution
- Negative: Shared state management complexity
- Mitigation: Thread-safe Blackboard implementation

---

## ADR-003: Integration with Existing Beavr

### Status: DECIDED

### Context
Beavr has existing infrastructure:
- Strategy interface (`BaseStrategy`, `evaluate()`, `Signal`)
- Backtest engine
- Data layer (Alpaca)
- Database (SQLite, bar cache)

Options:
1. Replace existing system entirely
2. Fork and create separate AI system
3. Extend existing system with AI as addon

### Decision
**Extend existing system** - AI strategies implement `BaseStrategy` interface.

### Rationale

```python
# AI strategy wraps agent system into existing interface
@register_strategy("ai_multi_agent")
class MultiAgentStrategy(BaseStrategy):
    def evaluate(self, ctx: StrategyContext) -> list[Signal]:
        # Bridge to agent system
        agent_ctx = self._build_agent_context(ctx)
        signals = self.orchestrator.run_daily_cycle(agent_ctx)
        return signals
```

**Benefits:**
- Reuse existing backtest engine unchanged
- Same data pipeline for AI and rule-based
- Gradual migration path (can run both)
- Unified configuration (TOML)
- Shared metrics and reporting

### Consequences
- Positive: No disruption, reuse existing code
- Negative: Must adapt agent context from strategy context
- Mitigation: Clean adapter layer

---

## ADR-004: Sync vs Async Execution

### Status: DECIDED

### Context
LLM calls are I/O bound and benefit from async execution. However:
- Beavr's current `evaluate()` is synchronous
- Backtest engine runs synchronously
- Python async requires careful handling

### Decision
**Async agents, sync bridge** - Agent system is async, wrapped with `asyncio.run()` at strategy level.

### Rationale

```python
# Agent layer: async for parallel LLM calls
async def run_daily_cycle(self, ctx) -> list[Signal]:
    proposals = await asyncio.gather(*[
        agent.analyze(ctx) for agent in self.trading_agents
    ])
    return self._aggregate(proposals)

# Strategy layer: sync interface
def evaluate(self, ctx: StrategyContext) -> list[Signal]:
    return asyncio.run(self.orchestrator.run_daily_cycle(agent_ctx))
```

**Benefits:**
- Parallel LLM calls (3-4x faster for multiple agents)
- Compatible with existing sync backtest engine
- Can optimize individual agent timeouts

### Consequences
- Positive: Performance for multi-agent scenarios
- Negative: `asyncio.run()` overhead, nested loop issues
- Mitigation: Use `nest_asyncio` if needed, or single event loop

---

## ADR-005: Risk Management Layer

### Status: DECIDED

### Context
Risk management can be implemented as:
1. Hard constraints in execution layer only
2. Advisory signals from risk agent
3. Multi-layer: agent analysis + hard constraints

### Decision
**Multi-layer risk management** with hard constraints as final gate.

### Rationale

```
┌────────────────────────────────────────────────────────────┐
│                    RISK LAYERS                              │
├────────────────────────────────────────────────────────────┤
│                                                             │
│  Layer 1: Sentinel Agent (LLM-based)                       │
│  ├─ Analyzes proposed trades for risk                      │
│  ├─ Considers market context and correlations              │
│  └─ Can reject or modify proposals                         │
│                                                             │
│  Layer 2: Risk Manager (Rule-based)                        │
│  ├─ Hard position limits (10% per position)                │
│  ├─ Sector concentration limits (30%)                      │
│  ├─ Correlation checks                                     │
│  └─ Cash reserve requirements (5%)                         │
│                                                             │
│  Layer 3: Kill Switch (Non-negotiable)                     │
│  ├─ 10% drawdown: Reduce risk budget 30%                   │
│  ├─ 15% drawdown: Reduce 60%, require hedges               │
│  └─ 20% drawdown: Flatten positions, halt trading          │
│                                                             │
└────────────────────────────────────────────────────────────┘
```

**Why multi-layer:**
- LLM agent can catch nuanced risks
- Hard constraints are guaranteed (no LLM hallucination)
- Kill switch protects against all failures

### Consequences
- Positive: Defense in depth, both intelligent and deterministic
- Negative: More complex implementation
- Mitigation: Clear separation of concerns

---

## ADR-006: Data Flow for LLM Context

### Status: DECIDED

### Context
LLMs have limited context windows. Need to efficiently convey:
- Price history
- Technical indicators
- Portfolio state
- Market regime

### Decision
**Summarized indicators** rather than raw bars in prompts.

### Rationale

```python
# DON'T: Raw bars (too verbose, wastes tokens)
prompt = f"Here are the last 50 OHLCV bars: {bars.to_json()}"

# DO: Pre-computed indicators (concise, meaningful)
prompt = f"""
SPY: price=$500.25, RSI=55, MACD=+2.3, above 20/50 SMA
Trend: bullish (price +3% from 20-day low)
Volatility: normal (ATR 1.2%)
"""
```

**Data flow:**
1. Raw bars → Indicator calculator → Structured indicators
2. Indicators + portfolio → Formatted prompt
3. LLM receives ~500-1000 tokens of context

### Consequences
- Positive: Lower token usage, faster responses, more consistent
- Negative: LLM can't discover novel patterns in raw data
- Mitigation: Include key raw data points when relevant

---

## ADR-007: Testing Strategy

### Status: DECIDED

### Context
Testing AI systems is challenging:
- LLM outputs are non-deterministic
- API calls are slow and costly
- Backtests require historical data

### Decision
**Multi-tier testing** with mocks and integration tests.

### Rationale

```
┌─────────────────────────────────────────────────────────────┐
│                     TESTING PYRAMID                          │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Tier 1: Unit Tests (fast, deterministic)                   │
│  ├─ Indicator calculations                                  │
│  ├─ Context building                                        │
│  ├─ Risk constraint checks                                  │
│  └─ Mock LLM with canned responses                          │
│                                                              │
│  Tier 2: Integration Tests (with real LLM)                  │
│  ├─ Agent analysis with live Copilot                        │
│  ├─ Orchestrator full cycle                                 │
│  └─ Strategy backtest on sample data                        │
│                                                              │
│  Tier 3: Backtest Validation                                │
│  ├─ Walk-forward on historical data                         │
│  ├─ Stress test scenarios (2020 crash, etc.)               │
│  └─ Paper trading before live                               │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### Consequences
- Positive: Fast feedback loop, reliable CI
- Negative: Mocks may not capture LLM edge cases
- Mitigation: Periodic integration tests with real API

---

## ADR-008: Configuration Management

### Status: DECIDED

### Context
Need to configure:
- Strategy parameters
- Risk limits
- Agent settings
- LLM parameters

### Decision
**Unified TOML configuration** consistent with existing Beavr patterns.

### Rationale

```toml
# Single file for complete strategy configuration
[strategy]
name = "ai_multi_agent"

[params]
symbols = ["SPY", "QQQ", "AAPL"]

[params.risk]
max_drawdown = 0.20
max_position_pct = 0.10

[params.agents]
enabled = ["market_analyst", "swing_trader"]

[params.llm]
model = "gpt-4"
temperature = 0.7
```

**Benefits:**
- Consistent with existing Beavr config
- Human-readable
- Version controllable
- Easy to create variations

### Consequences
- Positive: Familiar pattern, easy to use
- Negative: Need validation for LLM-specific params
- Mitigation: Pydantic models with validation

---

## Summary: Architecture at a Glance

| Component | Decision | Key Benefit |
|-----------|----------|-------------|
| LLM Infrastructure | GitHub Copilot SDK | No infra management |
| Agent Pattern | Blackboard + Orchestrator | Extensibility |
| Integration | Extend BaseStrategy | Reuse existing engine |
| Execution | Async agents, sync bridge | Parallel performance |
| Risk | Multi-layer + kill switch | Defense in depth |
| Data | Pre-computed indicators | Token efficiency |
| Testing | Multi-tier with mocks | Fast, reliable |
| Config | TOML files | Consistency |

---

*Architecture Decision Records v0.1.0*
*Last Updated: February 2026*
