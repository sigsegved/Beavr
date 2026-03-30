"""BeavrAPI implementation — wraps internal components behind a safe boundary.

This is the concrete implementation of the BeavrAPI protocol.
It holds references to internal components but only exposes
safe, validated operations through the public API.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any, Optional

from beavr.messaging.api import (
    DDReportSummary,
    PortfolioSnapshot,
    TradeHistoryEntry,
)

logger = logging.getLogger(__name__)

# Sector → ETF mapping (static, no internal state)
_SECTOR_ETFS: dict[str, list[str]] = {
    "technology": ["XLK", "QQQ", "SMH"],
    "tech": ["XLK", "QQQ", "SMH"],
    "energy": ["XLE", "USO", "XOP"],
    "healthcare": ["XLV", "IBB", "XBI"],
    "health": ["XLV", "IBB", "XBI"],
    "financials": ["XLF", "KBE", "KRE"],
    "finance": ["XLF", "KBE", "KRE"],
    "industrials": ["XLI", "ITA"],
    "materials": ["XLB", "GDX"],
    "utilities": ["XLU"],
    "consumer": ["XLY", "XLP"],
    "discretionary": ["XLY"],
    "staples": ["XLP"],
    "realestate": ["XLRE", "VNQ"],
    "real-estate": ["XLRE", "VNQ"],
    "communication": ["XLC"],
    "communications": ["XLC"],
    "telecom": ["XLC"],
}


class BeavrAPIImpl:
    """Concrete BeavrAPI implementation.

    Wraps broker, repos, and CLI-level functions behind a safe API.
    All internal references are private — never exposed to callers.
    """

    def __init__(
        self,
        *,
        broker: Any = None,
        positions_repo: Any = None,
        dd_repo: Any = None,
        events_repo: Any = None,
        thesis_repo: Any = None,
        llm_client: Any = None,
        orchestrator: Any = None,
    ) -> None:
        self._broker = broker
        self._positions_repo = positions_repo
        self._dd_repo = dd_repo
        self._events_repo = events_repo
        self._thesis_repo = thesis_repo
        self._llm = llm_client
        self._orchestrator = orchestrator

    def get_portfolio_status(self) -> PortfolioSnapshot:
        """Get current portfolio snapshot."""
        if not self._broker:
            raise RuntimeError("Broker not configured")

        account = self._broker.get_account()
        positions = self._broker.get_positions()

        pos_list = []
        for pos in positions:
            unrealized = pos.unrealized_pl or Decimal("0")
            cost = pos.avg_cost * pos.qty if pos.qty else Decimal("0")
            pnl_pct = float(unrealized / cost * 100) if cost > 0 else 0.0
            pos_list.append({
                "symbol": pos.symbol,
                "quantity": float(pos.qty),
                "avg_entry": float(pos.avg_cost),
                "market_value": float(pos.market_value),
                "unrealized_pnl": float(unrealized),
                "unrealized_pnl_pct": pnl_pct,
            })

        return PortfolioSnapshot(
            cash=account.cash,
            equity=account.equity,
            positions=pos_list,
        )

    def get_open_positions(self) -> list[dict[str, Any]]:
        """Get AI-managed open positions."""
        if not self._positions_repo:
            return []

        try:
            positions = self._positions_repo.get_open_positions()
            return [
                {
                    "symbol": p.symbol,
                    "quantity": float(p.quantity),
                    "entry_price": float(p.entry_price),
                    "stop_loss_price": float(p.stop_price),
                    "target_price": float(p.target_price),
                    "trade_type": p.strategy or "unknown",
                }
                for p in positions
            ]
        except Exception:
            logger.exception("Error getting open positions")
            return []

    def get_trade_history(self, limit: int = 10) -> list[TradeHistoryEntry]:
        """Get recent closed trades."""
        if not self._positions_repo:
            return []

        limit = min(max(limit, 1), 50)

        try:
            all_positions = self._positions_repo.get_all_positions(limit=limit)
            closed = [p for p in all_positions if p.status != "open"]
            return [
                TradeHistoryEntry(
                    symbol=p.symbol,
                    pnl=float(p.pnl) if p.pnl else 0.0,
                    pnl_pct=float(p.pnl_pct) if p.pnl_pct else 0.0,
                    exit_type=p.exit_reason or "unknown",
                )
                for p in closed
            ]
        except Exception:
            logger.exception("Error getting trade history")
            return []

    def get_dd_report(self, symbol: str) -> Optional[DDReportSummary]:
        """Get the latest DD report for a symbol."""
        if not self._dd_repo:
            return None

        try:
            report = self._dd_repo.get_latest_by_symbol(symbol)
            if not report:
                return None

            rec = report.recommendation.value if hasattr(report.recommendation, "value") else str(report.recommendation)
            return DDReportSummary(
                symbol=report.symbol,
                recommendation=rec,
                confidence=report.confidence,
                executive_summary=getattr(report, "executive_summary", "") or "",
                entry=report.recommended_entry,
                target=report.recommended_target,
                stop=report.recommended_stop,
                risk_factors=report.risk_factors or [],
            )
        except Exception:
            logger.exception("Error getting DD report for %s", symbol)
            return None

    def queue_symbol_for_analysis(self, symbol: str) -> str:
        """Queue a symbol for analysis by creating a market event."""
        if not self._events_repo:
            return f"❌ Cannot queue {symbol}: events repository not available."

        try:
            # Check for existing active thesis
            if self._thesis_repo:
                try:
                    existing = self._thesis_repo.get_active_by_symbol(symbol)
                    if existing:
                        status = existing.status.value if hasattr(existing.status, "value") else str(existing.status)
                        catalyst = existing.catalyst[:100] if existing.catalyst else "N/A"
                        return (
                            f"📋 {symbol} already has an active thesis.\n"
                            f"Status: {status}\n"
                            f"Catalyst: {catalyst}"
                        )
                except Exception:
                    pass  # thesis_repo may not support get_active_by_symbol

            from datetime import datetime

            from beavr.models.market_event import EventImportance, EventType, MarketEvent

            event = MarketEvent(
                event_type=EventType.OTHER,
                headline=f"User requested analysis: {symbol}",
                summary=f"User requested DD analysis for {symbol} via Telegram",
                source="user_telegram",
                symbol=symbol,
                importance=EventImportance.HIGH,
                timestamp=datetime.utcnow(),
            )
            self._events_repo.create(event)

            return (
                f"📋 {symbol} queued for analysis.\n"
                f"The system will process this through its agent pipeline "
                f"(thesis → DD → recommendation).\n"
                f"You'll receive the DD report when it's ready."
            )
        except Exception as e:
            logger.exception("Error queuing %s", symbol)
            return f"❌ Failed to queue {symbol}: {e}"

    def submit_research(self, text: str) -> str:
        """Submit freeform text for analysis. Processes immediately.

        Uses the LLM to identify relevant symbols, creates market events,
        and runs thesis + DD through the orchestrator synchronously.
        Returns a summary of results.
        """
        if not self._llm:
            return "❌ Cannot submit research: LLM not available."

        if not self._events_repo:
            return "❌ Cannot submit research: events repository not available."

        try:
            import json
            import re
            from datetime import datetime

            from beavr.models.market_event import EventImportance, EventType, MarketEvent

            # Use LLM to analyze the text and extract actionable info
            prompt = (
                "A user submitted the following market observation for analysis:\n\n"
                f'"{text}"\n\n'
                "Extract the following as JSON:\n"
                '{"symbols": ["TICKER1", "TICKER2"], '
                '"catalyst": "one sentence summary of the catalyst", '
                '"sector": "affected sector if any"}\n\n'
                "Rules:\n"
                "- symbols: List of 1-5 stock ticker symbols most relevant.\n"
                "- If a sector is mentioned but no specific stocks, include the sector ETF "
                "(XLK for tech, XLE for energy, XLF for financials, XLV for healthcare, "
                "SMH for semiconductors, XBI for biotech, XLC for communication, "
                "XLI for industrials, XLB for materials, XLU for utilities).\n"
                "- catalyst: A concise one-sentence description of the event/thesis.\n"
                "- Return ONLY valid JSON, no markdown or explanation."
            )

            response = self._llm.complete(prompt)

            # Parse LLM response
            json_match = re.search(r"\{[^}]+\}", response)
            if not json_match:
                return "❌ Could not analyze the text. Try including specific stock tickers."

            parsed = json.loads(json_match.group())
            symbols = parsed.get("symbols", [])
            catalyst = parsed.get("catalyst", text[:200])

            if not symbols:
                return (
                    "❌ No relevant symbols identified.\n\n"
                    "Try: /research MU and NVDA rallying on AI chip demand"
                )

            valid_symbols = [
                s.upper() for s in symbols
                if isinstance(s, str) and 1 <= len(s) <= 5 and s.isalpha()
            ][:10]

            if not valid_symbols:
                return "❌ No valid ticker symbols identified."

            # Create events
            created_events = []
            for symbol in valid_symbols:
                event = MarketEvent(
                    event_type=EventType.OTHER,
                    headline=catalyst[:200],
                    summary=text,
                    source="user_telegram",
                    symbol=symbol,
                    importance=EventImportance.HIGH,
                    timestamp=datetime.utcnow(),
                )
                self._events_repo.create(event)
                created_events.append(event)

            symbols_str = ", ".join(valid_symbols)

            # Process immediately if orchestrator is available
            if self._orchestrator and hasattr(self._orchestrator, "process_user_research"):
                lines = [
                    f"🔬 Research: {symbols_str}",
                    f"Catalyst: {catalyst}",
                    "",
                    "Processing through agent pipeline...",
                ]

                try:
                    results = self._orchestrator.process_user_research(created_events)

                    if results:
                        lines.append("")
                        for r in results:
                            sym = r.get("symbol", "?")
                            rec = r.get("recommendation", r.get("status", "?"))
                            conf = r.get("confidence")
                            summary = r.get("summary") or r.get("message", "")
                            if conf:
                                lines.append(f"{sym}: {rec.upper()} ({int(conf * 100)}%)")
                            else:
                                lines.append(f"{sym}: {rec}")
                            if summary:
                                lines.append(f"  {summary[:150]}")
                    else:
                        lines.append("No actionable results from DD analysis.")

                    # Approved DDs are auto-notified separately
                    approved = [r for r in results if r.get("recommendation") == "approve"]
                    if approved:
                        lines.append(f"\n✅ {len(approved)} approved — full DD reports sent separately.")

                except Exception as e:
                    logger.exception("Error in immediate research processing")
                    lines.append(f"\n⚠️ Processing error: {e}")
                    lines.append("Events saved — will be retried in next research cycle.")

                return "\n".join(lines)
            else:
                # Fallback: queue for next cycle
                return (
                    f"📥 Research submitted for: {symbols_str}\n\n"
                    f"Catalyst: {catalyst}\n\n"
                    f"Will be processed in the next research cycle."
                )
        except Exception as e:
            logger.exception("Error submitting research")
            return f"❌ Research submission failed: {e}"

    def get_sector_etfs(self, sector: str) -> list[str]:
        """Get ETF tickers for a sector."""
        return _SECTOR_ETFS.get(sector.lower(), [])

    def submit_buy_order(
        self, symbol: str, notional: Decimal
    ) -> dict[str, Any]:
        """Submit a buy order through the broker."""
        if not self._broker:
            raise RuntimeError("Broker not configured")

        from beavr.broker.models import OrderRequest

        order = OrderRequest(
            symbol=symbol,
            side="buy",
            notional=notional,
            order_type="market",
            time_in_force="day",
        )
        result = self._broker.submit_order(order)
        return {"order_id": result.order_id, "status": result.status}

    def submit_sell_order(
        self, symbol: str, quantity: Optional[Decimal] = None
    ) -> dict[str, Any]:
        """Submit a sell order through the broker."""
        if not self._broker:
            raise RuntimeError("Broker not configured")

        from beavr.broker.models import OrderRequest

        if quantity is None:
            positions = self._broker.get_positions()
            pos = next((p for p in positions if p.symbol == symbol), None)
            if not pos:
                raise ValueError(f"No position found for {symbol}")
            quantity = pos.qty

        order = OrderRequest(
            symbol=symbol,
            side="sell",
            qty=quantity,
            order_type="market",
            time_in_force="day",
        )
        result = self._broker.submit_order(order)
        return {"order_id": result.order_id, "status": result.status}

    def get_market_brief(self) -> Any | None:
        """Generate an on-demand market briefing."""
        try:
            from datetime import date, datetime
            from decimal import Decimal

            from beavr.agents.base import AgentContext
            from beavr.agents.market_briefing import MarketBriefingAgent

            # Build minimal context
            ctx = AgentContext(
                current_date=date.today(),
                timestamp=datetime.now(),
                portfolio_value=Decimal("0"),
                cash=Decimal("0"),
                current_drawdown=0.0,
                peak_value=Decimal("0"),
                regime="sideways",
                risk_budget=1.0,
                prices={},
                bars={},
                positions={},
                indicators={},
            )

            # Try to get real portfolio data
            if self._orchestrator and self._orchestrator._broker:
                try:
                    account = self._orchestrator._broker.get_account()
                    ctx = AgentContext(
                        current_date=date.today(),
                        timestamp=datetime.now(),
                        portfolio_value=account.equity,
                        cash=account.cash,
                        current_drawdown=0.0,
                        peak_value=account.equity,
                        regime=getattr(self._orchestrator.state, "current_regime", "sideways"),
                        risk_budget=1.0,
                        prices={},
                        bars={},
                        positions={},
                        indicators={},
                    )
                except Exception:
                    pass

            # Get LLM client
            if self._orchestrator and hasattr(self._orchestrator, "_llm") and self._orchestrator._llm:
                agent = MarketBriefingAgent(llm=self._orchestrator._llm)
                return agent.generate_brief(ctx)

            return None
        except Exception as e:
            logger.exception(f"Failed to generate market brief: {e}")
            return None
