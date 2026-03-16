"""Read-only command handlers: /status, /positions, /history.

All commands go through BeavrAPI — no direct access to broker or repos.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

from beavr.messaging.commands.base import BaseCommandHandler
from beavr.models.messaging import CommandResult, InboundCommand

if TYPE_CHECKING:
    from beavr.messaging.api import BeavrAPI

logger = logging.getLogger(__name__)


class StatusCommandHandler(BaseCommandHandler):
    """Handles /status — show portfolio summary."""

    command_names: list[str] = ["status"]
    tier: str = "read"
    description: str = "Show portfolio summary (cash, equity, positions)"

    def __init__(self, api: Optional[BeavrAPI] = None) -> None:
        self._api = api

    async def handle(self, command: InboundCommand) -> CommandResult:  # noqa: ARG002
        if not self._api:
            return CommandResult(success=False, message="❌ System not connected.")

        try:
            snapshot = self._api.get_portfolio_status()

            lines = ["📋 PORTFOLIO STATUS"]
            lines.append(f"Cash: ${snapshot.cash:,.2f}")
            lines.append(f"Equity: ${snapshot.equity:,.2f}")

            if snapshot.positions:
                lines.append(f"\nOpen Positions ({len(snapshot.positions)}):")
                for pos in snapshot.positions[:15]:
                    unrealized = pos.get("unrealized_pnl", 0)
                    icon = "📈" if unrealized >= 0 else "📉"
                    lines.append(
                        f"  {icon} {pos['symbol']}: {pos['quantity']} shares "
                        f"@ ${pos['avg_entry']:,.2f} "
                        f"(P/L: ${unrealized:,.2f})"
                    )
            else:
                lines.append("\nNo open positions.")

            return CommandResult(success=True, message="\n".join(lines))
        except Exception as e:
            logger.exception("Error getting status")
            return CommandResult(success=False, message=f"❌ Error: {e}")


class PositionsCommandHandler(BaseCommandHandler):
    """Handles /positions — list current broker positions."""

    command_names: list[str] = ["positions"]
    tier: str = "read"
    description: str = "List current portfolio positions with P/L"

    def __init__(self, api: Optional[BeavrAPI] = None) -> None:
        self._api = api

    async def handle(self, command: InboundCommand) -> CommandResult:  # noqa: ARG002
        if not self._api:
            return CommandResult(success=False, message="❌ System not connected.")

        try:
            snapshot = self._api.get_portfolio_status()
            positions = snapshot.positions

            if not positions:
                return CommandResult(success=True, message="No open positions.")

            lines = [f"📊 Open Positions ({len(positions)}):"]
            for pos in positions:
                symbol = pos.get("symbol", "???")
                qty = pos.get("quantity", 0)
                entry = pos.get("avg_entry", 0)
                unrealized = pos.get("unrealized_pnl", 0)
                pnl_pct = pos.get("unrealized_pnl_pct", 0)
                icon = "📈" if unrealized >= 0 else "📉"

                lines.append(
                    f"  {icon} {symbol}: {qty} shares "
                    f"@ ${entry:,.2f} "
                    f"(${unrealized:,.2f} / {pnl_pct:+.1f}%)"
                )

            return CommandResult(success=True, message="\n".join(lines))
        except Exception as e:
            logger.exception("Error getting positions")
            return CommandResult(success=False, message=f"❌ Error: {e}")


class HistoryCommandHandler(BaseCommandHandler):
    """Handles /history [n] — show recent trade history."""

    command_names: list[str] = ["history"]
    tier: str = "read"
    description: str = "Show recent trade history (default: last 10)"

    def __init__(self, api: Optional[BeavrAPI] = None) -> None:
        self._api = api

    async def handle(self, command: InboundCommand) -> CommandResult:
        if not self._api:
            return CommandResult(success=False, message="❌ System not connected.")

        limit = 10
        if command.args:
            try:
                limit = int(command.args[0])
            except ValueError:
                pass

        try:
            trades = self._api.get_trade_history(limit=limit)
            if not trades:
                return CommandResult(success=True, message="No trade history yet.")

            lines = [f"📜 Last {len(trades)} trades:"]
            for t in trades:
                icon = "📈" if t.pnl >= 0 else "📉"
                lines.append(
                    f"  {icon} {t.symbol}: ${t.pnl:,.2f} ({t.pnl_pct:+.1f}%) — {t.exit_type}"
                )

            return CommandResult(success=True, message="\n".join(lines))
        except Exception as e:
            logger.exception("Error getting history")
            return CommandResult(success=False, message=f"❌ Error: {e}")
