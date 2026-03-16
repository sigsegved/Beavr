"""Tests for command router and command handlers."""

import time
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from beavr.messaging.api import DDReportSummary, PortfolioSnapshot, TradeHistoryEntry
from beavr.messaging.commands.router import (
    MAX_TOTAL_COMMANDS_PER_HOUR,
    MAX_TRADING_COMMANDS_PER_HOUR,
    CommandRouter,
)
from beavr.messaging.commands.status import (
    HistoryCommandHandler,
    PositionsCommandHandler,
    StatusCommandHandler,
)
from beavr.messaging.commands.analyze import (
    AnalyzeCommandHandler,
    DDCommandHandler,
    ResearchCommandHandler,
    SectorCommandHandler,
)
from beavr.messaging.commands.trading import TradingCommandHandler
from beavr.models.messaging import CommandResult, InboundCommand


def _make_command(
    command: str, args: list[str] | None = None, sender_id: str = "user1"
) -> InboundCommand:
    """Helper to create InboundCommand instances."""
    return InboundCommand(
        raw_text=f"/{command} {' '.join(args or [])}",
        command=command,
        args=args or [],
        sender_id=sender_id,
        platform="test",
        is_verified=True,
    )


class TestCommandRouter:
    """Tests for CommandRouter."""

    @pytest.fixture
    def router(self) -> CommandRouter:
        """Create a router with a mock handler registered."""
        r = CommandRouter()
        handler = MagicMock()
        handler.command_names = ["test"]
        handler.tier = "read"
        handler.description = "Test command"
        handler.handle = AsyncMock(
            return_value=CommandResult(success=True, message="OK")
        )
        r.register(handler)
        return r

    @pytest.mark.asyncio
    async def test_route_known_command(self, router: CommandRouter) -> None:
        cmd = _make_command("test")
        result = await router.route(cmd)
        assert result.success is True
        assert result.message == "OK"

    @pytest.mark.asyncio
    async def test_route_unknown_command(self, router: CommandRouter) -> None:
        cmd = _make_command("unknown")
        result = await router.route(cmd)
        assert result.success is False
        assert "Unknown command" in result.message

    @pytest.mark.asyncio
    async def test_help_command(self, router: CommandRouter) -> None:
        cmd = _make_command("help")
        result = await router.route(cmd)
        assert result.success is True
        assert "Available Commands" in result.message
        assert "/test" in result.message

    @pytest.mark.asyncio
    async def test_rate_limit_total(self) -> None:
        """Total command rate limit should block after threshold."""
        r = CommandRouter()
        handler = MagicMock()
        handler.command_names = ["cmd"]
        handler.tier = "read"
        handler.description = "test"
        handler.handle = AsyncMock(
            return_value=CommandResult(success=True, message="OK")
        )
        r.register(handler)

        # Fill up the rate limit
        for _ in range(MAX_TOTAL_COMMANDS_PER_HOUR):
            cmd = _make_command("cmd", sender_id="ratelimit_user")
            result = await r.route(cmd)
            assert result.success is True

        # Next command should be rate limited
        cmd = _make_command("cmd", sender_id="ratelimit_user")
        result = await r.route(cmd)
        assert result.success is False
        assert "Rate limit" in result.message

    @pytest.mark.asyncio
    async def test_rate_limit_trading(self) -> None:
        """Trading command rate limit should block after threshold."""
        r = CommandRouter()
        handler = MagicMock()
        handler.command_names = ["trade"]
        handler.tier = "trading"
        handler.description = "test"
        handler.handle = AsyncMock(
            return_value=CommandResult(success=True, message="OK")
        )
        r.register(handler)

        for _ in range(MAX_TRADING_COMMANDS_PER_HOUR):
            cmd = _make_command("trade", sender_id="trader_user")
            result = await r.route(cmd)
            assert result.success is True

        cmd = _make_command("trade", sender_id="trader_user")
        result = await r.route(cmd)
        assert result.success is False
        assert "Trading rate limit" in result.message

    @pytest.mark.asyncio
    async def test_handler_exception_caught(self) -> None:
        """Router should catch handler exceptions and return error result."""
        r = CommandRouter()
        handler = MagicMock()
        handler.command_names = ["crash"]
        handler.tier = "read"
        handler.description = "test"
        handler.handle = AsyncMock(side_effect=RuntimeError("boom"))
        r.register(handler)

        cmd = _make_command("crash")
        result = await r.route(cmd)
        assert result.success is False
        assert "Error" in result.message


class TestStatusCommandHandler:
    """Tests for StatusCommandHandler."""

    @pytest.mark.asyncio
    async def test_no_api(self) -> None:
        handler = StatusCommandHandler(api=None)
        cmd = _make_command("status")
        result = await handler.handle(cmd)
        assert result.success is False
        assert "not connected" in result.message

    @pytest.mark.asyncio
    async def test_with_api(self) -> None:
        api = MagicMock()
        api.get_portfolio_status.return_value = PortfolioSnapshot(
            cash=Decimal("10000"),
            equity=Decimal("50000"),
            positions=[],
        )

        handler = StatusCommandHandler(api=api)
        cmd = _make_command("status")
        result = await handler.handle(cmd)
        assert result.success is True
        assert "$10,000" in result.message
        assert "No open positions" in result.message


class TestTradingCommandHandler:
    """Tests for TradingCommandHandler."""

    @pytest.fixture
    def handler(self) -> TradingCommandHandler:
        return TradingCommandHandler(api=None)

    @pytest.mark.asyncio
    async def test_buy_missing_args(self, handler: TradingCommandHandler) -> None:
        cmd = _make_command("buy")
        result = await handler.handle(cmd)
        assert result.success is False
        assert "Usage" in result.message

    @pytest.mark.asyncio
    async def test_buy_invalid_symbol(self, handler: TradingCommandHandler) -> None:
        cmd = _make_command("buy", ["TOOLONG", "$500"])
        result = await handler.handle(cmd)
        assert result.success is False
        assert "Invalid symbol" in result.message

    @pytest.mark.asyncio
    async def test_buy_invalid_amount(self, handler: TradingCommandHandler) -> None:
        cmd = _make_command("buy", ["AAPL", "abc"])
        result = await handler.handle(cmd)
        assert result.success is False
        assert "Invalid amount" in result.message

    @pytest.mark.asyncio
    async def test_buy_stages_confirmation(
        self, handler: TradingCommandHandler
    ) -> None:
        cmd = _make_command("buy", ["AAPL", "$500"])
        result = await handler.handle(cmd)
        assert result.success is True
        assert "CONFIRM TRADE" in result.message
        assert "BUY AAPL" in result.message
        assert "$500.00" in result.message

    @pytest.mark.asyncio
    async def test_sell_missing_args(self, handler: TradingCommandHandler) -> None:
        cmd = _make_command("sell")
        result = await handler.handle(cmd)
        assert result.success is False
        assert "Usage" in result.message

    @pytest.mark.asyncio
    async def test_sell_stages_confirmation(
        self, handler: TradingCommandHandler
    ) -> None:
        cmd = _make_command("sell", ["AAPL", "10"])
        result = await handler.handle(cmd)
        assert result.success is True
        assert "CONFIRM TRADE" in result.message
        assert "SELL AAPL" in result.message

    @pytest.mark.asyncio
    async def test_confirm_no_pending(self, handler: TradingCommandHandler) -> None:
        cmd = _make_command("confirm")
        result = await handler.handle(cmd)
        assert result.success is False
        assert "No pending trade" in result.message

    @pytest.mark.asyncio
    async def test_confirm_no_api(self, handler: TradingCommandHandler) -> None:
        # Stage a buy first
        buy_cmd = _make_command("buy", ["AAPL", "$500"])
        await handler.handle(buy_cmd)

        # Confirm without API
        confirm_cmd = _make_command("confirm")
        result = await handler.handle(confirm_cmd)
        assert result.success is False
        assert "not connected" in result.message

    @pytest.mark.asyncio
    async def test_cancel_pending(self, handler: TradingCommandHandler) -> None:
        buy_cmd = _make_command("buy", ["AAPL", "$500"])
        await handler.handle(buy_cmd)

        cancel_cmd = _make_command("cancel")
        result = await handler.handle(cancel_cmd)
        assert result.success is True
        assert "Cancelled" in result.message

    @pytest.mark.asyncio
    async def test_cancel_no_pending(self, handler: TradingCommandHandler) -> None:
        cmd = _make_command("cancel")
        result = await handler.handle(cmd)
        assert result.success is True
        assert "No pending trade" in result.message

    @pytest.mark.asyncio
    async def test_buy_negative_amount(self, handler: TradingCommandHandler) -> None:
        cmd = _make_command("buy", ["AAPL", "-100"])
        result = await handler.handle(cmd)
        assert result.success is False

    @pytest.mark.asyncio
    async def test_sell_invalid_quantity(self, handler: TradingCommandHandler) -> None:
        cmd = _make_command("sell", ["AAPL", "abc"])
        result = await handler.handle(cmd)
        assert result.success is False
        assert "Invalid quantity" in result.message


class TestSectorCommandHandler:
    """Tests for SectorCommandHandler."""

    @pytest.mark.asyncio
    async def test_no_args_shows_usage(self) -> None:
        handler = SectorCommandHandler()
        cmd = _make_command("sector")
        result = await handler.handle(cmd)
        assert result.success is False
        assert "Usage" in result.message
        assert "energy" in result.message

    @pytest.mark.asyncio
    async def test_no_api(self) -> None:
        handler = SectorCommandHandler(api=None)
        cmd = _make_command("sector", ["energy"])
        result = await handler.handle(cmd)
        assert result.success is False
        assert "not connected" in result.message

    @pytest.mark.asyncio
    async def test_with_api(self) -> None:
        api = MagicMock()
        api.get_sector_etfs.return_value = ["XLE", "USO", "XOP"]
        api.queue_symbol_for_analysis.return_value = "Queued"
        handler = SectorCommandHandler(api=api)
        cmd = _make_command("sector", ["energy"])
        result = await handler.handle(cmd)
        assert result.success is True
        assert "Energy" in result.message
        assert "XLE" in result.message

    @pytest.mark.asyncio
    async def test_unknown_sector(self) -> None:
        api = MagicMock()
        api.get_sector_etfs.return_value = []
        handler = SectorCommandHandler(api=api)
        cmd = _make_command("sector", ["cryptomining"])
        result = await handler.handle(cmd)
        assert result.success is True
        assert "No ETF mapping" in result.message


class TestResearchCommandHandler:
    """Tests for ResearchCommandHandler."""

    @pytest.mark.asyncio
    async def test_no_args_shows_usage(self) -> None:
        handler = ResearchCommandHandler()
        cmd = _make_command("research")
        result = await handler.handle(cmd)
        assert result.success is False
        assert "Usage" in result.message

    @pytest.mark.asyncio
    async def test_too_short_input(self) -> None:
        handler = ResearchCommandHandler()
        cmd = _make_command("research", ["hi"])
        result = await handler.handle(cmd)
        assert result.success is False
        assert "more context" in result.message

    @pytest.mark.asyncio
    async def test_no_api(self) -> None:
        handler = ResearchCommandHandler(api=None)
        cmd = _make_command("research", ["Fed", "raised", "rates", "50bps"])
        result = await handler.handle(cmd)
        assert result.success is False
        assert "not connected" in result.message

    @pytest.mark.asyncio
    async def test_with_api(self) -> None:
        api = MagicMock()
        api.submit_research.return_value = "📥 Research submitted."
        handler = ResearchCommandHandler(api=api)
        cmd = _make_command("research", ["Fed", "raised", "rates", "50bps"])
        result = await handler.handle(cmd)
        assert result.success is True
        assert "Research submitted" in result.message
        api.submit_research.assert_called_once_with("Fed raised rates 50bps")

    @pytest.mark.asyncio
    async def test_long_news_input(self) -> None:
        api = MagicMock()
        api.submit_research.return_value = "📥 Research submitted."
        handler = ResearchCommandHandler(api=api)
        news = (
            "Oil prices surged 5% after Iran-backed militants attacked "
            "shipping lanes in the Red Sea disrupting global trade"
        )
        cmd = _make_command("research", news.split())
        result = await handler.handle(cmd)
        assert result.success is True

    @pytest.mark.asyncio
    async def test_api_error_handled(self) -> None:
        api = MagicMock()
        api.submit_research.side_effect = RuntimeError("DB error")
        handler = ResearchCommandHandler(api=api)
        cmd = _make_command("research", ["TSLA", "record", "deliveries"])
        result = await handler.handle(cmd)
        assert result.success is False
        assert "Failed" in result.message


class TestAnalyzeCommandHandler:
    """Tests for AnalyzeCommandHandler."""

    @pytest.mark.asyncio
    async def test_no_args(self) -> None:
        handler = AnalyzeCommandHandler()
        cmd = _make_command("analyze")
        result = await handler.handle(cmd)
        assert result.success is False
        assert "Usage" in result.message

    @pytest.mark.asyncio
    async def test_invalid_symbol(self) -> None:
        handler = AnalyzeCommandHandler()
        cmd = _make_command("analyze", ["TOOLONG"])
        result = await handler.handle(cmd)
        assert result.success is False
        assert "Invalid symbol" in result.message

    @pytest.mark.asyncio
    async def test_with_api(self) -> None:
        api = MagicMock()
        api.queue_symbol_for_analysis.return_value = "📋 AAPL queued for analysis."
        handler = AnalyzeCommandHandler(api=api)
        cmd = _make_command("analyze", ["AAPL"])
        result = await handler.handle(cmd)
        assert result.success is True
        assert "AAPL" in result.message
        api.queue_symbol_for_analysis.assert_called_once_with("AAPL")


class TestDDCommandHandler:
    """Tests for DDCommandHandler."""

    @pytest.mark.asyncio
    async def test_no_args(self) -> None:
        handler = DDCommandHandler()
        cmd = _make_command("dd")
        result = await handler.handle(cmd)
        assert result.success is False

    @pytest.mark.asyncio
    async def test_existing_report(self) -> None:
        api = MagicMock()
        api.get_dd_report.return_value = DDReportSummary(
            symbol="TSLA",
            recommendation="approve",
            confidence=0.85,
            executive_summary="Strong momentum play.",
            entry=Decimal("250.00"),
            target=Decimal("280.00"),
            stop=Decimal("235.00"),
            risk_factors=["Valuation risk"],
        )
        handler = DDCommandHandler(api=api)
        cmd = _make_command("dd", ["TSLA"])
        result = await handler.handle(cmd)
        assert result.success is True
        assert "TSLA" in result.message
        assert "APPROVE" in result.message
        assert "85%" in result.message

    @pytest.mark.asyncio
    async def test_no_report_queues(self) -> None:
        api = MagicMock()
        api.get_dd_report.return_value = None
        api.queue_symbol_for_analysis.return_value = "📋 TSLA queued."
        handler = DDCommandHandler(api=api)
        cmd = _make_command("dd", ["TSLA"])
        result = await handler.handle(cmd)
        assert result.success is True
        assert "No existing DD" in result.message
