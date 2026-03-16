"""NotificationService — dispatches system events to messaging providers.

Central hub that receives domain events (DD reports, trades, exits)
and forwards them as formatted messages through the configured provider.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from beavr.messaging import formatters
from beavr.models.messaging import (
    MessagePriority,
    NotificationType,
    OutboundMessage,
)

if TYPE_CHECKING:
    from beavr.messaging.log_repo import MessagingLogRepository
    from beavr.messaging.protocols import MessagingProvider

logger = logging.getLogger(__name__)


class NotificationService:
    """Dispatches domain events to configured messaging providers.

    Attributes:
        provider: The active messaging provider.
        log_repo: Optional audit log repository.
    """

    def __init__(
        self,
        provider: MessagingProvider,
        log_repo: Optional[MessagingLogRepository] = None,
    ) -> None:
        self._provider = provider
        self._log_repo = log_repo

    async def notify_dd_report(
        self,
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
    ) -> bool:
        """Send a DD report notification.

        Returns:
            True if the message was delivered successfully.
        """
        body = formatters.format_dd_report(
            symbol=symbol,
            recommendation=recommendation,
            confidence=confidence,
            trade_type=trade_type,
            entry=entry,
            target=target,
            stop=stop,
            position_size_pct=position_size_pct,
            executive_summary=executive_summary,
            risk_factors=risk_factors,
            bull_case=bull_case,
            bear_case=bear_case,
            base_case=base_case,
        )
        msg = OutboundMessage(
            notification_type=NotificationType.DD_REPORT,
            priority=MessagePriority.MEDIUM,
            title=f"DD Report: {symbol} — {recommendation.upper()}",
            body=body,
            symbol=symbol,
        )
        return await self._send(msg)

    async def notify_trade_executed(
        self,
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
    ) -> bool:
        """Send a trade execution notification.

        Returns:
            True if the message was delivered successfully.
        """
        body = formatters.format_trade_executed(
            action=action,
            symbol=symbol,
            quantity=quantity,
            price=price,
            total_cost=total_cost,
            stop_loss=stop_loss,
            target=target,
            order_id=order_id,
            thesis_summary=thesis_summary,
        )
        msg = OutboundMessage(
            notification_type=NotificationType.TRADE_EXECUTED,
            priority=MessagePriority.HIGH,
            title=f"Trade: {action.upper()} {symbol}",
            body=body,
            symbol=symbol,
        )
        return await self._send(msg)

    async def notify_position_closed(
        self,
        *,
        symbol: str,
        exit_reason: str,
        entry_price: Decimal,
        exit_price: Decimal,
        quantity: Decimal,
        pnl: Decimal,
        pnl_pct: float,
    ) -> bool:
        """Send a position closure notification.

        Returns:
            True if the message was delivered successfully.
        """
        body = formatters.format_position_closed(
            symbol=symbol,
            exit_reason=exit_reason,
            entry_price=entry_price,
            exit_price=exit_price,
            quantity=quantity,
            pnl=pnl,
            pnl_pct=pnl_pct,
        )
        ntype = NotificationType.POSITION_CLOSED
        if exit_reason == "stop_hit":
            ntype = NotificationType.STOP_LOSS_HIT
        elif exit_reason == "target_hit":
            ntype = NotificationType.TARGET_HIT

        msg = OutboundMessage(
            notification_type=ntype,
            priority=MessagePriority.HIGH,
            title=f"Position Closed: {symbol}",
            body=body,
            symbol=symbol,
        )
        return await self._send(msg)

    async def notify_market_event(
        self,
        *,
        headline: str,
        symbol: Optional[str] = None,
        importance: str = "medium",
        source: Optional[str] = None,
    ) -> bool:
        """Send a market event notification.

        Returns:
            True if the message was delivered successfully.
        """
        body = formatters.format_market_event(
            headline=headline,
            symbol=symbol,
            importance=importance,
            source=source,
        )
        priority = (
            MessagePriority.HIGH if importance == "high" else MessagePriority.MEDIUM
        )
        msg = OutboundMessage(
            notification_type=NotificationType.MARKET_EVENT,
            priority=priority,
            title=f"Market Event: {headline[:60]}",
            body=body,
            symbol=symbol,
        )
        return await self._send(msg)

    async def notify_error(
        self,
        *,
        error: str,
        component: Optional[str] = None,
    ) -> bool:
        """Send a system error notification.

        Returns:
            True if the message was delivered successfully.
        """
        body = formatters.format_system_error(error=error, component=component)
        msg = OutboundMessage(
            notification_type=NotificationType.SYSTEM_ERROR,
            priority=MessagePriority.CRITICAL,
            title="System Error",
            body=body,
        )
        return await self._send(msg)

    async def send_raw(self, message: OutboundMessage) -> bool:
        """Send an arbitrary message through the provider.

        Returns:
            True if the message was delivered successfully.
        """
        return await self._send(message)

    async def _send(self, message: OutboundMessage) -> bool:
        """Internal send with logging.

        Returns:
            True if the message was delivered successfully.
        """
        try:
            success = await self._provider.send_message(message)
            if self._log_repo:
                self._log_repo.log_outbound(
                    platform=self._provider.provider_name,
                    notification_type=message.notification_type.value,
                    priority=message.priority.value,
                    message_text=message.body,
                    symbol=message.symbol,
                    success=success,
                )
            return success
        except Exception:
            logger.exception("Failed to send %s notification", message.notification_type.value)
            if self._log_repo:
                self._log_repo.log_outbound(
                    platform=self._provider.provider_name,
                    notification_type=message.notification_type.value,
                    priority=message.priority.value,
                    message_text=message.body,
                    symbol=message.symbol,
                    success=False,
                    error_message=str(message),
                )
            return False
