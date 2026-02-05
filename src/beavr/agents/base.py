"""Base agent interface for AI Investor."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any, ClassVar, Optional

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from beavr.llm.client import LLMClient


class AgentContext(BaseModel):
    """
    Context provided to agents for decision making.

    This is the "view of the world" that each agent receives.
    """

    # Time
    current_date: date
    timestamp: datetime

    # Market data
    prices: dict[str, Decimal]  # symbol -> current price
    bars: dict[str, list[dict[str, Any]]]  # symbol -> recent OHLCV bars
    indicators: dict[str, dict[str, float]]  # symbol -> {rsi, sma_20, etc.}

    # Portfolio state
    cash: Decimal
    positions: dict[str, Decimal]  # symbol -> shares
    portfolio_value: Decimal

    # Risk state
    current_drawdown: float  # current drawdown from peak
    peak_value: Decimal  # historical peak portfolio value
    risk_budget: float  # available risk budget (0-1)

    # Regime (from Market Analyst)
    regime: Optional[str] = None  # bull, bear, sideways, volatile
    regime_confidence: float = 0.0

    # Events/News (future extension)
    events: list[dict[str, Any]] = Field(default_factory=list)

    model_config = {"arbitrary_types_allowed": True}


class AgentProposal(BaseModel):
    """
    Output from an agent's analysis.

    Each agent produces proposals that are aggregated by the orchestrator.
    """

    agent_name: str
    timestamp: datetime

    # Proposed signals (will be converted to Signal objects)
    signals: list[dict[str, Any]] = Field(default_factory=list)

    # Confidence and reasoning
    conviction: float = Field(ge=0.0, le=1.0)
    rationale: str

    # Risk assessment
    risk_score: float = Field(ge=0.0, le=1.0, default=0.5)
    risk_factors: list[str] = Field(default_factory=list)

    # Metadata
    model_version: str = "unknown"
    processing_time_ms: float = 0.0

    # Extra data (regime info for Market Analyst, etc.)
    extra: dict[str, Any] = Field(default_factory=dict)


class BaseAgent(ABC):
    """
    Abstract base class for all AI agents.

    Each agent represents a specialized "persona" with a specific
    role and expertise in the trading system.
    """

    # Class-level metadata (override in subclass)
    name: ClassVar[str] = "Base Agent"
    role: ClassVar[str] = "base"  # analyst, trader, risk
    description: ClassVar[str] = ""
    version: ClassVar[str] = "0.1.0"

    def __init__(self, llm: LLMClient):
        """
        Initialize agent with LLM client.

        Args:
            llm: LLM client for reasoning
        """
        self.llm = llm

    @abstractmethod
    def analyze(self, ctx: AgentContext) -> AgentProposal:
        """
        Analyze context and propose actions.

        This is the main entry point called by the orchestrator.

        Args:
            ctx: Current market/portfolio context

        Returns:
            AgentProposal with signals and reasoning
        """
        pass

    @abstractmethod
    def get_system_prompt(self) -> str:
        """
        Return the agent's persona/system prompt.

        This defines the agent's role and expertise for the LLM.
        """
        pass

    def build_user_prompt(self, ctx: AgentContext) -> str:
        """
        Build the user prompt from context.

        Override for custom prompt formatting.
        """
        return f"""
Current Date: {ctx.current_date}
Regime: {ctx.regime or 'unknown'} (confidence: {ctx.regime_confidence:.2f})
Cash: ${ctx.cash:,.2f}
Portfolio Value: ${ctx.portfolio_value:,.2f}
Current Drawdown: {ctx.current_drawdown:.1%}
Risk Budget: {ctx.risk_budget:.1%}

Positions:
{self._format_positions(ctx)}

Recent Prices:
{self._format_prices(ctx)}

Indicators:
{self._format_indicators(ctx)}

Based on this information, provide your analysis and recommendations.
"""

    def _format_positions(self, ctx: AgentContext) -> str:
        """Format positions for prompt."""
        if not ctx.positions:
            return "  (no positions)"
        lines = []
        for symbol, shares in ctx.positions.items():
            price = ctx.prices.get(symbol, Decimal(0))
            value = shares * price
            lines.append(f"  {symbol}: {shares:.4f} shares @ ${price} = ${value:,.2f}")
        return "\n".join(lines)

    def _format_prices(self, ctx: AgentContext) -> str:
        """Format prices for prompt."""
        lines = []
        for symbol, price in ctx.prices.items():
            lines.append(f"  {symbol}: ${price}")
        return "\n".join(lines)

    def _format_indicators(self, ctx: AgentContext) -> str:
        """Format indicators for prompt."""
        lines = []
        for symbol, inds in ctx.indicators.items():
            ind_str = ", ".join(f"{k}={v:.2f}" for k, v in inds.items())
            lines.append(f"  {symbol}: {ind_str}")
        return "\n".join(lines)

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} '{self.name}' v{self.version}>"
