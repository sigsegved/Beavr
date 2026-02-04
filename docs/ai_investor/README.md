# AI Investor Documentation

This folder contains all documentation for Beavr's AI Investor system—a multi-agent autonomous trading platform powered by large language models.

## Documents

| Document | Description |
|----------|-------------|
| [ARCHITECTURE.md](./ARCHITECTURE.md) | System architecture, components, and how they work together |
| [IMPLEMENTATION.md](./IMPLEMENTATION.md) | Code-level implementation details and examples |
| [ADR.md](./ADR.md) | Architecture Decision Records—key design decisions and rationale |
| [SME_RESPONSE.md](./SME_RESPONSE.md) | Analysis of expert feedback and architectural responses |
| [CHATGPT_PLAN.md](./CHATGPT_PLAN.md) | Original detailed specification from ChatGPT |
| [RESEARCH.md](./RESEARCH.md) | Background research on AI investor systems and multi-agent architectures |

## Reading Order

1. **Start here**: [ARCHITECTURE.md](./ARCHITECTURE.md) — Understand the system design
2. **Expert feedback**: [SME_RESPONSE.md](./SME_RESPONSE.md) — See how we addressed critical concerns
3. **Deep dive**: [IMPLEMENTATION.md](./IMPLEMENTATION.md) — See how to build it
4. **Why decisions**: [ADR.md](./ADR.md) — Understand design choices
5. **Background**: [RESEARCH.md](./RESEARCH.md) — Academic and industry context

## Quick Links

- [Key Concepts](./ARCHITECTURE.md#key-concepts)
- [Daily Decision Cycle](./ARCHITECTURE.md#daily-decision-cycle)
- [Position Sizing Engine](./ARCHITECTURE.md#position-sizing-engine-deterministic)
- [Circuit Breakers](./ARCHITECTURE.md#failure-modes--circuit-breakers)
- [Copilot SDK Integration](./IMPLEMENTATION.md#11-copilot-sdk-integration)

## MVP Scope

For the initial MVP, we use **GitHub Copilot SDK** exclusively for LLM reasoning:
- No API key management needed (uses your Copilot subscription)
- No cloud model setup required
- Included in GitHub Copilot Business/Enterprise

Future versions may add support for other LLM providers.

## Important Disclaimers

This is **experimental software**, not financial advice. The system:
- Has optimization goals, not performance guarantees
- Requires validation through paper trading before live use
- May lose money—all trading involves risk
- Should not be used without understanding the risks involved
