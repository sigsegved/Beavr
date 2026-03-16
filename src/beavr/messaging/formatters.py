"""Message formatters for converting Beavr domain objects to human-readable text.

Formats DD reports, trade executions, position exits, and other events
into structured text suitable for Telegram (Markdown) or other IM platforms.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Optional


def format_dd_report(
    *,
    symbol: str,
    recommendation: str,
    confidence: float,
    trade_type: Optional[str] = None,
    entry: Optional[Decimal] = None,
    target: Optional[Decimal] = None,
    stop: Optional[Decimal] = None,
    position_size_pct: Optional[float] = None,
    executive_summary: Optional[str] = None,
    risk_factors: Optional[list[str]] = None,
    bull_case: Optional[str] = None,
    bear_case: Optional[str] = None,
    base_case: Optional[str] = None,
) -> str:
    """Format a DD report as a notification message.

    Returns:
        Formatted message string.
    """
    icon = {"approve": "✅", "reject": "❌", "conditional": "⚠️"}.get(
        recommendation.lower(), "📊"
    )
    rec_upper = recommendation.upper()
    conf_pct = int(confidence * 100)

    lines = [f"📊 DD REPORT: {symbol} — {icon} {rec_upper} ({conf_pct}% confidence)"]

    if trade_type:
        lines.append(f"Trade Type: {trade_type.replace('_', ' ').title()}")

    if entry is not None and target is not None and stop is not None:
        lines.append(f"Entry: ${entry:,.2f} | Target: ${target:,.2f} | Stop: ${stop:,.2f}")

    if position_size_pct is not None:
        lines.append(f"Position Size: {position_size_pct:.0%} of portfolio")

    if executive_summary:
        lines.append(f"\n{executive_summary}")

    if bull_case or bear_case or base_case:
        lines.append("")
        if bull_case:
            lines.append(f"Bull: {bull_case}")
        if bear_case:
            lines.append(f"Bear: {bear_case}")
        if base_case:
            lines.append(f"Base: {base_case}")

    if risk_factors:
        lines.append("\nRisks:")
        for risk in risk_factors[:5]:
            lines.append(f"• {risk}")

    return "\n".join(lines)


def format_trade_executed(
    *,
    action: str,
    symbol: str,
    quantity: Decimal,
    price: Decimal,
    total_cost: Optional[Decimal] = None,
    stop_loss: Optional[Decimal] = None,
    target: Optional[Decimal] = None,
    order_id: Optional[str] = None,
    thesis_summary: Optional[str] = None,
) -> str:
    """Format a trade execution notification.

    Returns:
        Formatted message string.
    """
    icon = "🟢" if action.upper() == "BUY" else "🔴"
    lines = [f"{icon} TRADE EXECUTED"]
    lines.append(f"Action: {action.upper()} {symbol}")
    lines.append(f"Shares: {quantity}")
    lines.append(f"Price: ${price:,.2f}")

    if total_cost is not None:
        lines.append(f"Total: ${total_cost:,.2f}")

    if stop_loss is not None:
        stop_pct = ((stop_loss - price) / price) * 100
        lines.append(f"Stop Loss: ${stop_loss:,.2f} ({stop_pct:+.1f}%)")

    if target is not None:
        target_pct = ((target - price) / price) * 100
        lines.append(f"Target: ${target:,.2f} ({target_pct:+.1f}%)")

    if order_id:
        lines.append(f"Order ID: {order_id}")

    if thesis_summary:
        lines.append(f"\nThesis: {thesis_summary}")

    return "\n".join(lines)


def format_position_closed(
    *,
    symbol: str,
    exit_reason: str,
    entry_price: Decimal,
    exit_price: Decimal,
    quantity: Decimal,
    pnl: Decimal,
    pnl_pct: float,
) -> str:
    """Format a position closure notification.

    Returns:
        Formatted message string.
    """
    icon_map = {
        "target_hit": "🎯",
        "stop_hit": "⚠️",
        "time_exit": "⏰",
        "thesis_invalidated": "🚫",
        "manual": "👤",
    }
    icon = icon_map.get(exit_reason, "📤")
    pnl_icon = "📈" if pnl >= 0 else "📉"

    lines = [f"{icon} POSITION CLOSED: {symbol}"]
    lines.append(f"Reason: {exit_reason.replace('_', ' ').title()}")
    lines.append(f"Entry: ${entry_price:,.2f} → Exit: ${exit_price:,.2f}")
    lines.append(f"Shares: {quantity}")
    lines.append(f"{pnl_icon} P/L: ${pnl:,.2f} ({pnl_pct:+.1f}%)")

    return "\n".join(lines)


def format_market_event(
    *,
    headline: str,
    symbol: Optional[str] = None,
    importance: str = "medium",
    source: Optional[str] = None,
) -> str:
    """Format a market event notification.

    Returns:
        Formatted message string.
    """
    icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(importance, "🔵")
    lines = [f"{icon} MARKET EVENT"]
    if symbol:
        lines.append(f"Symbol: {symbol}")
    lines.append(headline)
    if source:
        lines.append(f"Source: {source}")
    return "\n".join(lines)


def format_system_error(*, error: str, component: Optional[str] = None) -> str:
    """Format a system error notification.

    Returns:
        Formatted message string.
    """
    lines = ["🚨 SYSTEM ERROR"]
    if component:
        lines.append(f"Component: {component}")
    lines.append(error)
    return "\n".join(lines)


def format_portfolio_status(
    *,
    cash: Decimal,
    equity: Decimal,
    positions: list[dict[str, Any]],
    day_pnl: Optional[Decimal] = None,
) -> str:
    """Format a portfolio status response.

    Returns:
        Formatted message string.
    """
    lines = ["📋 PORTFOLIO STATUS"]
    lines.append(f"Cash: ${cash:,.2f}")
    lines.append(f"Equity: ${equity:,.2f}")
    if day_pnl is not None:
        icon = "📈" if day_pnl >= 0 else "📉"
        lines.append(f"{icon} Day P/L: ${day_pnl:,.2f}")

    if positions:
        lines.append(f"\nOpen Positions ({len(positions)}):")
        for pos in positions[:10]:
            sym = pos.get("symbol", "???")
            qty = pos.get("quantity", 0)
            pnl = pos.get("unrealized_pnl", Decimal("0"))
            pnl_pct = pos.get("unrealized_pnl_pct", 0.0)
            icon = "📈" if pnl >= 0 else "📉"
            lines.append(f"  {icon} {sym}: {qty} shares (${pnl:,.2f} / {pnl_pct:+.1f}%)")
    else:
        lines.append("\nNo open positions.")

    return "\n".join(lines)
