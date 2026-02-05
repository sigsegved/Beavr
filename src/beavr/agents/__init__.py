"""AI Agent system for Beavr AI Investor."""

from beavr.agents.base import AgentContext, AgentProposal, BaseAgent
from beavr.agents.dd_agent import DueDiligenceAgent
from beavr.agents.indicators import build_agent_context_indicators, calculate_indicators
from beavr.agents.market_analyst import MarketAnalysis, MarketAnalystAgent
from beavr.agents.morning_scanner import MorningScannerAgent
from beavr.agents.news_monitor import NewsMonitorAgent
from beavr.agents.position_manager import PositionManagerAgent, PositionReview
from beavr.agents.swing_trader import SwingAnalysis, SwingTraderAgent
from beavr.agents.symbol_selector import SymbolSelection, SymbolSelectorAgent
from beavr.agents.thesis_generator import ThesisGeneratorAgent
from beavr.agents.trade_executor import ExecutionPlan, ExecutionResult, TradeExecutorAgent

__all__ = [
    # Base
    "AgentContext",
    "AgentProposal",
    "BaseAgent",
    # Utils
    "calculate_indicators",
    "build_agent_context_indicators",
    # v1 Agents (retained for compatibility)
    "MarketAnalystAgent",
    "MarketAnalysis",
    "SwingTraderAgent",
    "SwingAnalysis",
    "SymbolSelectorAgent",
    "SymbolSelection",
    # v2 Agents
    "DueDiligenceAgent",
    "MorningScannerAgent",
    "NewsMonitorAgent",
    "PositionManagerAgent",
    "PositionReview",
    "ThesisGeneratorAgent",
    "TradeExecutorAgent",
    "ExecutionPlan",
    "ExecutionResult",
]
