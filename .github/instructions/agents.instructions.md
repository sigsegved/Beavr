---
applyTo: "src/beavr/agents/**/*.py"
---

# AI Agent Development Rules

All agents inherit from `BaseAgent` and implement `analyze()`.

## Required Pattern

```python
from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal
from typing import ClassVar

from pydantic import BaseModel, Field

from beavr.agents.base import AgentContext, AgentProposal, BaseAgent

logger = logging.getLogger(__name__)


class MyAgentSignal(BaseModel):
    """Structured output for agent signals."""
    symbol: str = Field(description="Trading symbol")
    action: str = Field(description="buy, sell, or hold")
    conviction: float = Field(ge=0.0, le=1.0)
    rationale: str = Field(description="Reason for recommendation")


class MyAgentAnalysis(BaseModel):
    """Complete structured output from agent."""
    signals: list[MyAgentSignal]
    market_view: str
    overall_conviction: float = Field(ge=0.0, le=1.0)


class MyAgent(BaseAgent):
    """
    Detailed description of agent's role and expertise.
    """
    
    name: ClassVar[str] = "My Agent"
    role: ClassVar[str] = "trader"  # analyst | trader | risk
    description: ClassVar[str] = "Brief description"
    version: ClassVar[str] = "0.1.0"
    
    def get_system_prompt(self) -> str:
        """Define agent's LLM persona."""
        return """You are a trading agent specializing in...
        
YOUR EXPERTISE:
- Area 1
- Area 2

SIGNALS TO LOOK FOR:
- Signal 1
- Signal 2

OUTPUT FORMAT:
Return JSON matching MyAgentAnalysis schema.
"""
    
    def analyze(self, ctx: AgentContext) -> AgentProposal:
        """
        Analyze context and generate proposals.
        
        Args:
            ctx: Market and portfolio context
            
        Returns:
            AgentProposal with signals and reasoning
        """
        # Build prompt, call LLM, parse response
        # Return AgentProposal
```

## Rules

1. **Structured output** - Define Pydantic models for LLM responses
2. **Clear persona** - System prompt defines expertise
3. **Decimal for money** - in all calculations
4. **Logging** - Log key decisions for debugging

## Agent Roles
- `analyst` - Market regime, risk assessment
- `trader` - Trade signals, entry/exit
- `risk` - Validate proposals, enforce limits
