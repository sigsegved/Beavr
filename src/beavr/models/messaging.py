"""Messaging data models for the Beavr notification system."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class MessagePriority(str, Enum):
    """Priority level for outbound notifications."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class NotificationType(str, Enum):
    """Type of system notification."""

    DD_REPORT = "dd_report"
    TRADE_EXECUTED = "trade_executed"
    POSITION_CLOSED = "position_closed"
    STOP_LOSS_HIT = "stop_loss_hit"
    TARGET_HIT = "target_hit"
    MARKET_EVENT = "market_event"
    SYSTEM_ERROR = "system_error"
    COMMAND_RESPONSE = "command_response"


class OutboundMessage(BaseModel):
    """A notification message to be sent to the user.

    Attributes:
        notification_type: Category of notification
        priority: Urgency level
        title: Short summary line
        body: Full message content
        symbol: Related stock ticker, if any
        metadata: Arbitrary extra context
        timestamp: When the event occurred
    """

    notification_type: NotificationType = Field(description="Category of notification")
    priority: MessagePriority = Field(description="Urgency level")
    title: str = Field(description="Short summary line")
    body: str = Field(description="Full message content")
    symbol: Optional[str] = Field(default=None, description="Related stock ticker")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Extra context")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Event time")


class InboundCommand(BaseModel):
    """A parsed command received from the user.

    Attributes:
        raw_text: Original message text
        command: Parsed command name (e.g. 'analyze', 'buy')
        args: Parsed positional arguments
        sender_id: Platform-specific user identifier
        platform: Messaging platform name
        timestamp: When the message was received
        is_verified: Whether the sender passed auth checks
    """

    raw_text: str = Field(description="Original message text")
    command: str = Field(description="Parsed command name")
    args: list[str] = Field(default_factory=list, description="Parsed arguments")
    sender_id: str = Field(description="Platform-specific user ID")
    platform: str = Field(description="Messaging platform name")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Received time")
    is_verified: bool = Field(default=False, description="Sender passed auth checks")


class CommandResult(BaseModel):
    """Result of processing an inbound command.

    Attributes:
        success: Whether the command executed successfully
        message: Human-readable response text
        data: Optional structured data
    """

    success: bool = Field(description="Command executed successfully")
    message: str = Field(description="Human-readable response")
    data: Optional[dict[str, Any]] = Field(default=None, description="Structured data")


class PendingConfirmation(BaseModel):
    """A trading command awaiting user confirmation.

    Attributes:
        chat_id: The chat/conversation ID
        command: The trading action (buy or sell)
        symbol: Stock ticker
        amount: Dollar amount (for buys)
        quantity: Share quantity (for sells)
        created_at: When the confirmation was requested
        expires_at: When this confirmation expires
    """

    chat_id: str = Field(description="Chat/conversation ID")
    command: str = Field(description="Trading action: buy or sell")
    symbol: str = Field(description="Stock ticker")
    amount: Optional[Decimal] = Field(default=None, description="Dollar amount for buys")
    quantity: Optional[Decimal] = Field(default=None, description="Share quantity for sells")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Request time")
    expires_at: datetime = Field(description="Expiration time")
