"""CLI commands for the Beavr messaging system.

Usage:
    bvr messaging setup     — Verify Telegram bot connection
    bvr messaging test      — Send a test notification
    bvr messaging log       — Show recent messaging audit log
"""

from __future__ import annotations

import asyncio
import os
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(
    help="Messaging and notification system",
    no_args_is_help=True,
)
console = Console()


@app.command()
def setup() -> None:
    """Verify Telegram bot configuration and test connectivity."""
    from beavr.models.config import AppConfig

    config = AppConfig()
    if not config.messaging or not config.messaging.enabled:
        console.print("[yellow]Messaging is not enabled.[/yellow]")
        console.print(
            "Set BEAVR_MESSAGING__ENABLED=true and configure Telegram settings."
        )
        raise typer.Exit(1)

    tg_config = config.messaging.telegram
    if not tg_config:
        console.print("[red]Telegram config not set.[/red]")
        raise typer.Exit(1)

    bot_token = tg_config.get_bot_token()
    if not bot_token:
        console.print(
            f"[red]Bot token not found.[/red] Set {tg_config.bot_token_env} env var."
        )
        raise typer.Exit(1)

    console.print(f"[green]Bot token:[/green] {bot_token[:10]}...")
    console.print(
        f"[green]Verified chat IDs:[/green] {tg_config.verified_chat_ids or 'none'}"
    )

    verify_token = os.environ.get(tg_config.verify_token_env)
    if verify_token:
        console.print(f"[green]Verify token:[/green] {verify_token[:8]}...")
    else:
        console.print(
            f"[yellow]No verify token set.[/yellow] "
            f"Set {tg_config.verify_token_env} for user verification."
        )

    console.print("\n[bold green]Messaging setup looks good![/bold green]")


@app.command()
def test(
    message: Optional[str] = typer.Option(
        None, "--message", "-m", help="Custom test message"
    ),
) -> None:
    """Send a test notification to verify delivery."""
    from beavr.messaging.providers.factory import MessagingProviderFactory
    from beavr.models.config import AppConfig
    from beavr.models.messaging import (
        MessagePriority,
        NotificationType,
        OutboundMessage,
    )

    config = AppConfig()
    if not config.messaging or not config.messaging.enabled:
        console.print("[red]Messaging is not enabled.[/red]")
        raise typer.Exit(1)

    try:
        provider = MessagingProviderFactory.create(config.messaging)
    except ValueError as e:
        console.print(f"[red]Failed to create provider:[/red] {e}")
        raise typer.Exit(1) from None

    text = message or "This is a test notification from Beavr."
    msg = OutboundMessage(
        notification_type=NotificationType.COMMAND_RESPONSE,
        priority=MessagePriority.LOW,
        title="🧪 Test Notification",
        body=text,
    )

    with console.status("Sending test message..."):
        success = asyncio.run(provider.send_message(msg))

    if success:
        console.print("[green]Test message sent successfully![/green]")
    else:
        console.print("[red]Failed to send test message.[/red]")
        raise typer.Exit(1)


@app.command()
def log(
    limit: int = typer.Option(20, "--limit", "-n", help="Number of entries to show"),
) -> None:
    """Show recent messaging audit log entries."""
    from beavr.db.connection import Database
    from beavr.messaging.log_repo import MessagingLogRepository
    from beavr.models.config import AppConfig

    config = AppConfig()
    db = Database(config.database_path)
    repo = MessagingLogRepository(db)

    entries = repo.get_recent(limit=limit)
    if not entries:
        console.print("[yellow]No messaging log entries found.[/yellow]")
        return

    table = Table(title=f"Messaging Log (last {len(entries)})")
    table.add_column("Time", style="dim")
    table.add_column("Dir", style="cyan")
    table.add_column("Type", style="magenta")
    table.add_column("Symbol")
    table.add_column("Success")
    table.add_column("Message", max_width=50)

    for entry in entries:
        direction = entry.get("direction", "?")
        icon = "📤" if direction == "outbound" else "📥"
        ntype = entry.get("notification_type") or entry.get("command") or "—"
        symbol = entry.get("symbol") or "—"
        success = "✅" if entry.get("success") else "❌"
        text = (entry.get("raw_text") or "")[:50]
        ts = (entry.get("timestamp") or "")[:19]

        table.add_row(ts, f"{icon} {direction}", ntype, symbol, success, text)

    console.print(table)
