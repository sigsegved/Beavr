"""Pydantic models for data representation."""

from beavr.models.bar import Bar
from beavr.models.config import (
    AlpacaConfig,
    AppConfig,
    BacktestConfig,
    DipBuyDCAParams,
    SimpleDCAParams,
    StrategyConfig,
)
from beavr.models.dd_report import (
    DayTradePlan,
    DDRecommendation,
    DDSummary,
    DueDiligenceReport,
    RecommendedTradeType,
    SwingTradePlan,
)
from beavr.models.market_event import (
    EventImportance,
    EventSummary,
    EventType,
    MarketEvent,
)
from beavr.models.morning_candidate import (
    MorningCandidate,
    MorningScanResult,
    ScanType,
)
from beavr.models.portfolio import PortfolioState, Position
from beavr.models.signal import Signal
from beavr.models.thesis import (
    ThesisStatus,
    ThesisSummary,
    TradeDirection,
    TradeThesis,
    TradeType,
)
from beavr.models.trade import Trade

__all__ = [
    # Core models
    "Bar",
    "Signal",
    "Trade",
    "Position",
    "PortfolioState",
    # Config models
    "AlpacaConfig",
    "AppConfig",
    "BacktestConfig",
    "StrategyConfig",
    "SimpleDCAParams",
    "DipBuyDCAParams",
    # V2 AI Investor models
    "DayTradePlan",
    "DDRecommendation",
    "DDSummary",
    "DueDiligenceReport",
    "RecommendedTradeType",
    "SwingTradePlan",
    "EventImportance",
    "EventSummary",
    "EventType",
    "MarketEvent",
    "MorningCandidate",
    "MorningScanResult",
    "ScanType",
    "ThesisStatus",
    "ThesisSummary",
    "TradeDirection",
    "TradeThesis",
    "TradeType",
]
