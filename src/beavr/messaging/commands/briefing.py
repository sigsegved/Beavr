"""Briefing command handler: /brief."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

from beavr.messaging.commands.base import BaseCommandHandler
from beavr.models.messaging import CommandResult, InboundCommand

if TYPE_CHECKING:
    from beavr.messaging.api import BeavrAPI

logger = logging.getLogger(__name__)


class BriefingCommandHandler(BaseCommandHandler):
    """Handles /brief — generate on-demand market briefing."""

    command_names: list[str] = ["brief", "briefing", "market"]
    tier: str = "analysis"
    description: str = "Get an on-demand market briefing with outlook"

    def __init__(self, api: Optional[BeavrAPI] = None) -> None:
        self._api = api

    async def handle(self, command: InboundCommand) -> CommandResult:  # noqa: ARG002
        if not self._api:
            return CommandResult(success=False, message="❌ System not connected.")

        try:
            brief = self._api.get_market_brief()
            if not brief:
                return CommandResult(
                    success=False,
                    message="❌ Could not generate market brief. Try again later.",
                )

            # Format for Telegram (max 4096 chars)
            lines = [
                f"📊 BEAVR MARKET BRIEF — {brief.generated_at.strftime('%b %d, %Y')}",
                f"{'━' * 30}",
                "",
                f"🏛️ Regime: {brief.regime.upper()} ({brief.regime_confidence:.0%} confidence)",
                f"Risk Posture: {brief.risk_posture}",
                "",
            ]

            if brief.leading_sectors:
                lines.append(f"📈 Leading: {', '.join(brief.leading_sectors[:3])}")
            if brief.lagging_sectors:
                lines.append(f"📉 Lagging: {', '.join(brief.lagging_sectors[:3])}")
            if brief.rotation_theme:
                lines.append(f"🔄 {brief.rotation_theme}")

            lines.append("")

            if brief.portfolio_warnings:
                lines.append("⚠️ Portfolio Warnings:")
                for w in brief.portfolio_warnings[:3]:
                    lines.append(f"  • {w}")
                lines.append("")

            if brief.key_takeaways:
                lines.append("🎯 Key Takeaways:")
                for t in brief.key_takeaways[:5]:
                    lines.append(f"  • {t}")

            msg = "\n".join(lines)
            # Telegram limit
            if len(msg) > 4000:
                msg = msg[:3997] + "..."

            return CommandResult(success=True, message=msg)

        except Exception as e:
            logger.exception("Error generating market brief")
            return CommandResult(success=False, message=f"❌ Brief failed: {e}")
