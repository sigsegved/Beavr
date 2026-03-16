"""Analysis command handlers: /analyze, /dd, /sector, /research.

These commands delegate to BeavrAPI — they never touch internal
orchestrator state, repos, or LLM clients directly.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

from beavr.messaging.auth import validate_symbol
from beavr.messaging.commands.base import BaseCommandHandler
from beavr.models.messaging import CommandResult, InboundCommand

if TYPE_CHECKING:
    from beavr.messaging.api import BeavrAPI

logger = logging.getLogger(__name__)

# Known sectors for display
KNOWN_SECTORS = {
    "technology", "tech", "healthcare", "health", "financials", "finance",
    "energy", "utilities", "materials", "industrials", "consumer",
    "discretionary", "staples", "realestate", "real-estate",
    "communication", "communications", "telecom",
}


class AnalyzeCommandHandler(BaseCommandHandler):
    """Handles /analyze <symbol> — queue a symbol for analysis."""

    command_names: list[str] = ["analyze"]
    tier: str = "analysis"
    description: str = "Queue a symbol for analysis by the trading system"

    def __init__(self, api: Optional[BeavrAPI] = None) -> None:
        self._api = api

    async def handle(self, command: InboundCommand) -> CommandResult:
        if not command.args:
            return CommandResult(
                success=False,
                message="Usage: /analyze <SYMBOL>\nExample: /analyze AAPL",
            )

        symbol = command.args[0].upper()
        if not validate_symbol(symbol):
            return CommandResult(
                success=False,
                message=f"❌ Invalid symbol: {symbol}. Use 1-5 uppercase letters.",
            )

        if not self._api:
            return CommandResult(success=False, message="❌ System not connected.")

        try:
            msg = self._api.queue_symbol_for_analysis(symbol)
            return CommandResult(success=True, message=msg, data={"symbol": symbol})
        except Exception as e:
            logger.exception("Error queuing %s", symbol)
            return CommandResult(success=False, message=f"❌ Failed: {e}")


class DDCommandHandler(BaseCommandHandler):
    """Handles /dd <symbol> — show existing DD report or queue for analysis."""

    command_names: list[str] = ["dd"]
    tier: str = "analysis"
    description: str = "Show DD report or queue symbol for analysis"

    def __init__(self, api: Optional[BeavrAPI] = None) -> None:
        self._api = api

    async def handle(self, command: InboundCommand) -> CommandResult:
        if not command.args:
            return CommandResult(
                success=False,
                message="Usage: /dd <SYMBOL>\nExample: /dd TSLA",
            )

        symbol = command.args[0].upper()
        if not validate_symbol(symbol):
            return CommandResult(
                success=False,
                message=f"❌ Invalid symbol: {symbol}. Use 1-5 uppercase letters.",
            )

        if not self._api:
            return CommandResult(success=False, message="❌ System not connected.")

        try:
            report = self._api.get_dd_report(symbol)
            if report:
                conf = int(report.confidence * 100)
                lines = [f"📊 DD Report: {symbol} — {report.recommendation.upper()} ({conf}%)"]
                if report.executive_summary:
                    lines.append(f"\n{report.executive_summary}")
                if report.entry is not None:
                    lines.append(
                        f"\nEntry: ${report.entry:,.2f} | "
                        f"Target: ${report.target:,.2f} | "
                        f"Stop: ${report.stop:,.2f}"
                    )
                if report.risk_factors:
                    lines.append("\nRisks:")
                    for risk in report.risk_factors[:3]:
                        lines.append(f"• {risk}")
                return CommandResult(success=True, message="\n".join(lines))

            # No report — queue for analysis
            msg = self._api.queue_symbol_for_analysis(symbol)
            return CommandResult(
                success=True,
                message=f"No existing DD for {symbol}.\n{msg}",
            )
        except Exception as e:
            logger.exception("Error processing DD for %s", symbol)
            return CommandResult(success=False, message=f"❌ Failed: {e}")


class SectorCommandHandler(BaseCommandHandler):
    """Handles /sector <name> — show sector ETFs and queue for analysis."""

    command_names: list[str] = ["sector"]
    tier: str = "analysis"
    description: str = "Show sector ETFs and queue for analysis"

    def __init__(self, api: Optional[BeavrAPI] = None) -> None:
        self._api = api

    async def handle(self, command: InboundCommand) -> CommandResult:
        if not command.args:
            sector_list = ", ".join(sorted(KNOWN_SECTORS))
            return CommandResult(
                success=False,
                message=(
                    "Usage: /sector <name>\n"
                    "Example: /sector energy\n\n"
                    f"Known sectors: {sector_list}"
                ),
            )

        sector = " ".join(command.args).lower().strip()

        if not self._api:
            return CommandResult(success=False, message="❌ System not connected.")

        etfs = self._api.get_sector_etfs(sector)
        lines = [f"🏭 Sector: {sector.title()}"]

        if not etfs:
            lines.append(f"No ETF mapping for '{sector}'.")
            lines.append("Try: energy, tech, healthcare, financials")
            return CommandResult(success=True, message="\n".join(lines))

        lines.append(f"Key ETFs: {', '.join(etfs)}")

        # Queue each ETF for analysis
        queued = []
        for etf in etfs:
            try:
                self._api.queue_symbol_for_analysis(etf)
                queued.append(etf)
            except Exception:
                pass

        if queued:
            lines.append(f"\n📋 Queued for analysis: {', '.join(queued)}")
            lines.append("DD reports will be sent when ready.")

        return CommandResult(success=True, message="\n".join(lines))


class ResearchCommandHandler(BaseCommandHandler):
    """Handles /research <text> — submit info to the system's event pipeline."""

    command_names: list[str] = ["research"]
    tier: str = "analysis"
    description: str = "Submit news or market info for the system to analyze"

    def __init__(self, api: Optional[BeavrAPI] = None) -> None:
        self._api = api

    async def handle(self, command: InboundCommand) -> CommandResult:
        if not command.args:
            return CommandResult(
                success=False,
                message=(
                    "Usage: /research <your text>\n\n"
                    "Examples:\n"
                    "  /research Fed just raised rates 50bps\n"
                    "  /research TSLA reported record deliveries Q1\n"
                    "  /research Oil prices surging due to Iran tensions"
                ),
            )

        user_text = " ".join(command.args).strip()
        if len(user_text) < 5:
            return CommandResult(
                success=False,
                message="❌ Please provide more context (at least a sentence).",
            )

        if not self._api:
            return CommandResult(success=False, message="❌ System not connected.")

        try:
            msg = self._api.submit_research(user_text)
            return CommandResult(success=True, message=msg)
        except Exception as e:
            logger.exception("Error submitting research")
            return CommandResult(success=False, message=f"❌ Failed: {e}")
