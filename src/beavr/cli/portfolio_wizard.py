"""Interactive portfolio selection wizard for ``bvr ai auto``.

Handles both non-interactive (CLI flags) and interactive (prompt-driven)
portfolio creation/resumption flows.

Usage (internal)::

    from beavr.cli.portfolio_wizard import select_or_create_portfolio
    record = select_or_create_portfolio(store, ...)
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Optional

import typer
from rich.columns import Columns
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from beavr.db.protocols import PortfolioStore
from beavr.models.portfolio_record import (
    Aggressiveness,
    PortfolioRecord,
    PortfolioStatus,
    TradingMode,
)

console = Console()

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

_DEFAULT_CAPITAL = Decimal("10000.00")
_DEFAULT_CAPITAL_PCT = 80.0

# ---------------------------------------------------------------------------
# Visual constants
# ---------------------------------------------------------------------------

_BEAVER_LOGO = r"""
    /\_/\
   ( o.o )  [bold cyan]B E A V R[/bold cyan]
    > ^ <   [dim]Autonomous AI Trading[/dim]
"""

_MODE_INFO = {
    "1": {
        "mode": TradingMode.PAPER,
        "icon": "📝",
        "label": "Paper Trading",
        "desc": "Simulated trades — no real money at risk",
        "style": "yellow",
    },
    "2": {
        "mode": TradingMode.LIVE,
        "icon": "💰",
        "label": "Live Trading",
        "desc": "Real money — orders execute on your brokerage",
        "style": "red",
    },
}

_AGG_INFO = {
    "1": {
        "agg": Aggressiveness.CONSERVATIVE,
        "icon": "🛡️",
        "label": "Conservative",
        "desc": "Tight stops, small positions, blue-chip focus",
        "style": "green",
        "bar": "▓░░░░",
    },
    "2": {
        "agg": Aggressiveness.MODERATE,
        "icon": "⚖️",
        "label": "Moderate",
        "desc": "Balanced risk/reward, diversified approach",
        "style": "yellow",
        "bar": "▓▓▓░░",
    },
    "3": {
        "agg": Aggressiveness.AGGRESSIVE,
        "icon": "🔥",
        "label": "Aggressive",
        "desc": "Larger positions, wider stops, momentum plays",
        "style": "red",
        "bar": "▓▓▓▓▓",
    },
}


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def select_or_create_portfolio(
    portfolio_store: PortfolioStore,
    portfolio_name: Optional[str],
    mode: Optional[str],
    aggressiveness: Optional[str],
    directives: Optional[list[str]],
    capital: Optional[Decimal],
    capital_pct: Optional[float],
) -> PortfolioRecord:
    """Select an existing portfolio or create a new one.

    **Non-interactive** (``--portfolio`` flag provided):
    - Resume if the named portfolio already exists.
    - Create from flags if ``--mode`` is also provided.
    - Error if the name doesn't exist and ``--mode`` is missing.

    **Interactive** (no ``--portfolio`` flag):
    - List existing portfolios and let the user choose, or create new.

    Args:
        portfolio_store: Persistence layer for portfolios.
        portfolio_name: Explicit portfolio name (``--portfolio`` flag).
        mode: Trading mode string (``paper`` / ``live``).
        aggressiveness: Risk profile string.
        directives: AI personality directives.
        capital: Initial capital allocation.
        capital_pct: Percentage of capital available for trading.

    Returns:
        The selected or newly-created :class:`PortfolioRecord`.

    Raises:
        typer.Exit: On unrecoverable input errors.
    """
    if portfolio_name is not None:
        return _non_interactive(
            portfolio_store,
            portfolio_name,
            mode,
            aggressiveness,
            directives,
            capital,
            capital_pct,
        )
    return _interactive_select(portfolio_store)


# ---------------------------------------------------------------------------
# Non-interactive flow
# ---------------------------------------------------------------------------


def _non_interactive(
    portfolio_store: PortfolioStore,
    name: str,
    mode: Optional[str],
    aggressiveness: Optional[str],
    directives: Optional[list[str]],
    capital: Optional[Decimal],
    capital_pct: Optional[float],
) -> PortfolioRecord:
    """Resolve a portfolio by name, creating if flags allow."""
    existing = portfolio_store.get_portfolio_by_name(name)
    if existing is not None:
        _print_resume(existing)
        return existing

    # Name doesn't exist — need --mode to create
    if mode is None:
        console.print(
            f"[red]Error:[/red] Portfolio [bold]{name}[/bold] not found and "
            "[cyan]--mode[/cyan] was not provided.\n"
            "Supply [cyan]--mode paper|live[/cyan] to create it."
        )
        raise typer.Exit(1)

    return _create_from_flags(
        portfolio_store,
        name=name,
        mode=mode,
        aggressiveness=aggressiveness,
        directives=directives,
        capital=capital,
        capital_pct=capital_pct,
    )


# ---------------------------------------------------------------------------
# Interactive selection
# ---------------------------------------------------------------------------


def _interactive_select(portfolio_store: PortfolioStore) -> PortfolioRecord:
    """Interactively list portfolios and let the user pick or create new.

    Args:
        portfolio_store: Portfolio persistence layer.

    Returns:
        The chosen or newly-created :class:`PortfolioRecord`.
    """
    console.print()
    console.print(Panel(
        _BEAVER_LOGO,
        title="[bold]Portfolio Setup[/bold]",
        subtitle="[dim]Configure your trading personality[/dim]",
        border_style="bright_cyan",
        expand=False,
        padding=(0, 2),
    ))

    portfolios = portfolio_store.list_portfolios()

    if not portfolios:
        console.print()
        console.print(
            "  [dim]No existing portfolios found.[/dim]  "
            "Let's set up your first one! 🚀"
        )
        console.print()
        return _interactive_create(portfolio_store)

    # Build a rich table for existing portfolios
    console.print()
    ptable = Table(
        title="📂  Your Portfolios",
        show_lines=False,
        pad_edge=True,
        expand=False,
    )
    ptable.add_column("#", style="bold cyan", justify="center", width=3)
    ptable.add_column("Name", style="bold")
    ptable.add_column("Mode")
    ptable.add_column("Risk")
    ptable.add_column("Trades", justify="right")
    ptable.add_column("P&L", justify="right")
    ptable.add_column("Status")

    for idx, pf in enumerate(portfolios, start=1):
        pnl = pf.realized_pnl
        pnl_style = "green" if pnl >= 0 else "red"
        status_icon = "🟢" if pf.status == PortfolioStatus.ACTIVE else "🟡"
        mode_icon = "📝" if pf.mode == TradingMode.PAPER else "💰"
        agg_bar = {"conservative": "🛡️", "moderate": "⚖️", "aggressive": "🔥"}.get(
            pf.aggressiveness.value, "⚖️"
        )

        ptable.add_row(
            str(idx),
            pf.name,
            f"{mode_icon} {pf.mode.value}",
            f"{agg_bar} {pf.aggressiveness.value}",
            str(pf.total_trades),
            f"[{pnl_style}]${pnl:+,.2f}[/{pnl_style}]",
            f"{status_icon} {pf.status.value}",
        )

    console.print(ptable)
    console.print()
    console.print("  [bold bright_green]N[/bold bright_green]  ✨ Create new portfolio")
    console.print()

    choice = typer.prompt(
        "  Select",
        default="N" if not portfolios else "1",
    )

    if choice.upper() == "N":
        console.print()
        return _interactive_create(portfolio_store)

    try:
        index = int(choice) - 1
        if index < 0 or index >= len(portfolios):
            raise ValueError
    except ValueError:
        console.print(f"[red]Error:[/red] Invalid selection: {choice}")
        raise typer.Exit(1) from None

    selected = portfolios[index]
    _print_resume(selected)
    return selected


# ---------------------------------------------------------------------------
# Interactive creation
# ---------------------------------------------------------------------------


def _interactive_create(portfolio_store: PortfolioStore) -> PortfolioRecord:
    """Walk the user through creating a new portfolio interactively.

    Prompts for name, mode, aggressiveness, directives, and capital.
    Shows a summary panel and asks for confirmation before persisting.

    Args:
        portfolio_store: Portfolio persistence layer.

    Returns:
        The newly-created :class:`PortfolioRecord`.
    """
    console.print(Rule("[bold bright_cyan]New Portfolio[/bold bright_cyan]", style="bright_cyan"))
    console.print()

    # --- Step 1: Name ---
    console.print("  [bold]Step 1/5[/bold]  [dim]Give your portfolio a name[/dim]")
    name = typer.prompt("  📛 Name")
    if not name.strip():
        console.print("[red]Error:[/red] Name cannot be empty.")
        raise typer.Exit(1)
    name = name.strip()

    if portfolio_store.get_portfolio_by_name(name) is not None:
        console.print(f"[red]Error:[/red] Portfolio [bold]{name}[/bold] already exists.")
        raise typer.Exit(1)

    console.print()

    # --- Step 2: Mode ---
    console.print("  [bold]Step 2/5[/bold]  [dim]Choose trading mode[/dim]")
    console.print()
    for key, info in _MODE_INFO.items():
        console.print(
            f"   [bold {info['style']}]{key}[/bold {info['style']}]  "
            f"{info['icon']}  [bold]{info['label']}[/bold]"
        )
        console.print(f"      [dim]{info['desc']}[/dim]")
    console.print()
    mode_choice = typer.prompt("  Select mode", default="1")

    if mode_choice not in _MODE_INFO:
        console.print(f"[red]Error:[/red] Invalid mode selection: {mode_choice}")
        raise typer.Exit(1)

    mode = _MODE_INFO[mode_choice]["mode"]
    console.print(
        f"  → [{_MODE_INFO[mode_choice]['style']}]"
        f"{_MODE_INFO[mode_choice]['icon']}  {_MODE_INFO[mode_choice]['label']}"
        f"[/{_MODE_INFO[mode_choice]['style']}]"
    )
    console.print()

    # --- Step 3: Aggressiveness ---
    console.print("  [bold]Step 3/5[/bold]  [dim]Set your risk appetite[/dim]")
    console.print()
    for key, info in _AGG_INFO.items():
        console.print(
            f"   [bold {info['style']}]{key}[/bold {info['style']}]  "
            f"{info['icon']}  [bold]{info['label']}[/bold]  "
            f"[{info['style']}]{info['bar']}[/{info['style']}]"
        )
        console.print(f"      [dim]{info['desc']}[/dim]")
    console.print()
    agg_choice = typer.prompt("  Select risk level", default="2")

    if agg_choice not in _AGG_INFO:
        console.print(f"[red]Error:[/red] Invalid selection: {agg_choice}")
        raise typer.Exit(1)

    aggressiveness = _AGG_INFO[agg_choice]["agg"]
    console.print(
        f"  → [{_AGG_INFO[agg_choice]['style']}]"
        f"{_AGG_INFO[agg_choice]['icon']}  {_AGG_INFO[agg_choice]['label']}  "
        f"{_AGG_INFO[agg_choice]['bar']}"
        f"[/{_AGG_INFO[agg_choice]['style']}]"
    )
    console.print()

    # --- Step 4: Directives ---
    console.print("  [bold]Step 4/5[/bold]  [dim]Define your AI trading personality[/dim]")
    console.print(
        "  [dim]Tell the AI how to trade. Be specific about strategies,\n"
        "  risk tolerance, instruments, and style. Empty line to finish.[/dim]"
    )
    console.print()

    directives: list[str] = []
    n = 1
    while True:
        line = typer.prompt(f"  💬 [{n}]", default="", show_default=False)
        if not line.strip():
            break
        directives.append(line.strip())
        n += 1

    if directives:
        console.print(f"  [green]✓[/green] {len(directives)} directive(s) captured")
    else:
        console.print("  [dim]No directives — AI will use default strategy.[/dim]")
    console.print()

    # --- Step 5: Capital ---
    console.print("  [bold]Step 5/5[/bold]  [dim]Set your capital allocation[/dim]")
    console.print()
    capital_str = typer.prompt("  💵 Initial capital ($)", default=str(_DEFAULT_CAPITAL))
    try:
        capital = Decimal(capital_str.replace(",", ""))
        if capital <= 0:
            raise InvalidOperation
    except (InvalidOperation, ValueError):
        console.print(f"[red]Error:[/red] Invalid capital amount: {capital_str}")
        raise typer.Exit(1) from None

    capital_pct_str = typer.prompt(
        "  📊 Trading allocation (%)",
        default=str(_DEFAULT_CAPITAL_PCT),
    )
    try:
        capital_pct = float(capital_pct_str)
        if capital_pct <= 0 or capital_pct > 100:
            raise ValueError
    except ValueError:
        console.print(f"[red]Error:[/red] Invalid capital percentage: {capital_pct_str}")
        raise typer.Exit(1) from None

    # --- Summary ---
    console.print()
    allocated = capital * Decimal(str(capital_pct)) / Decimal("100")
    reserved = capital - allocated

    mode_info = next(v for v in _MODE_INFO.values() if v["mode"] == mode)
    agg_info = next(v for v in _AGG_INFO.values() if v["agg"] == aggressiveness)

    # Build the left column: config
    config_text = Text.from_markup(
        f"  [bold]Name:[/bold]    {name}\n"
        f"  [bold]Mode:[/bold]    {mode_info['icon']}  [{mode_info['style']}]{mode_info['label']}[/{mode_info['style']}]\n"
        f"  [bold]Risk:[/bold]    {agg_info['icon']}  [{agg_info['style']}]{agg_info['label']}  {agg_info['bar']}[/{agg_info['style']}]"
    )

    # Build the right column: capital
    capital_text = Text.from_markup(
        f"  [bold]Capital:[/bold]    ${capital:>12,.2f}\n"
        f"  [bold]Trading:[/bold]    [green]${allocated:>12,.2f}[/green] ({capital_pct:.0f}%)\n"
        f"  [bold]Reserved:[/bold]   [dim]${reserved:>12,.2f}[/dim]"
    )

    console.print(Panel(
        Columns([config_text, capital_text], padding=(0, 4)),
        title="[bold]📋  Portfolio Summary[/bold]",
        border_style="bright_green",
        expand=False,
        padding=(1, 2),
    ))

    # Directives sub-panel
    if directives:
        dir_lines = "\n".join(f"  [dim]•[/dim] {d}" for d in directives)
        console.print(Panel(
            dir_lines,
            title="[bold]🧠  AI Directives[/bold]",
            border_style="bright_blue",
            expand=False,
            padding=(0, 2),
        ))

    console.print()
    if not typer.confirm("  Create this portfolio?", default=True):
        console.print("  [yellow]Cancelled.[/yellow]")
        raise typer.Exit(0)

    portfolio_id = portfolio_store.create_portfolio(
        name=name,
        mode=mode.value,
        initial_capital=capital,
        config_snapshot={},
        aggressiveness=aggressiveness.value,
        directives=directives,
    )

    record = portfolio_store.get_portfolio(portfolio_id)
    if record is None:
        console.print("[red]Error:[/red] Failed to retrieve created portfolio.")
        raise typer.Exit(1)

    console.print()
    console.print(Panel(
        f"  [bold green]✅  Portfolio created![/bold green]\n\n"
        f"  [bold]{name}[/bold]  •  {mode_info['icon']} {mode.value}  •  "
        f"{agg_info['icon']} {aggressiveness.value}\n"
        f"  ID: [dim]{portfolio_id}[/dim]",
        border_style="green",
        expand=False,
        padding=(0, 2),
    ))
    console.print()
    return record


# ---------------------------------------------------------------------------
# Non-interactive creation from flags
# ---------------------------------------------------------------------------


def _create_from_flags(
    portfolio_store: PortfolioStore,
    name: str,
    mode: str,
    aggressiveness: Optional[str],
    directives: Optional[list[str]],
    capital: Optional[Decimal],
    capital_pct: Optional[float],
) -> PortfolioRecord:
    """Create a portfolio from CLI flags without prompting.

    Args:
        portfolio_store: Portfolio persistence layer.
        name: Portfolio name.
        mode: Trading mode (``paper`` / ``live``).
        aggressiveness: Risk profile; defaults to ``moderate``.
        directives: AI directives; defaults to empty list.
        capital: Initial capital; defaults to ``$10,000.00``.
        capital_pct: Allocation percentage; defaults to ``80.0``.

    Returns:
        The newly-created :class:`PortfolioRecord`.

    Raises:
        typer.Exit: On validation errors.
    """
    # Validate mode
    try:
        validated_mode = TradingMode(mode)
    except ValueError:
        console.print(
            f"[red]Error:[/red] Invalid mode [bold]{mode}[/bold]. "
            "Use [cyan]paper[/cyan] or [cyan]live[/cyan]."
        )
        raise typer.Exit(1) from None

    # Validate aggressiveness
    agg_value = aggressiveness or Aggressiveness.MODERATE.value
    try:
        validated_agg = Aggressiveness(agg_value)
    except ValueError:
        console.print(
            f"[red]Error:[/red] Invalid aggressiveness [bold]{agg_value}[/bold]. "
            "Use [cyan]conservative[/cyan], [cyan]moderate[/cyan], or [cyan]aggressive[/cyan]."
        )
        raise typer.Exit(1) from None

    resolved_directives = directives or []
    resolved_capital = capital if capital is not None else _DEFAULT_CAPITAL
    resolved_capital_pct = capital_pct if capital_pct is not None else _DEFAULT_CAPITAL_PCT

    if resolved_capital <= 0:
        console.print("[red]Error:[/red] Capital must be positive.")
        raise typer.Exit(1)

    if resolved_capital_pct <= 0 or resolved_capital_pct > 100:
        console.print("[red]Error:[/red] Capital percentage must be between 0 and 100.")
        raise typer.Exit(1)

    portfolio_id = portfolio_store.create_portfolio(
        name=name,
        mode=validated_mode.value,
        initial_capital=resolved_capital,
        config_snapshot={},
        aggressiveness=validated_agg.value,
        directives=resolved_directives,
    )

    record = portfolio_store.get_portfolio(portfolio_id)
    if record is None:
        console.print("[red]Error:[/red] Failed to retrieve created portfolio.")
        raise typer.Exit(1)

    mode_icon = "📝" if validated_mode == TradingMode.PAPER else "💰"
    agg_icon = {"conservative": "🛡️", "moderate": "⚖️", "aggressive": "🔥"}.get(
        validated_agg.value, "⚖️"
    )
    console.print(
        f"\n[green]✅[/green] Portfolio [bold]{name}[/bold] created  "
        f"{mode_icon} {validated_mode.value}  {agg_icon} {validated_agg.value}  "
        f"💵 ${resolved_capital:,.2f}"
    )
    return record


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _print_resume(record: PortfolioRecord) -> None:
    """Print a rich resume panel for an existing portfolio."""
    mode_icon = "📝" if record.mode == TradingMode.PAPER else "💰"
    agg_icon = {"conservative": "🛡️", "moderate": "⚖️", "aggressive": "🔥"}.get(
        record.aggressiveness.value, "⚖️"
    )
    pnl = record.realized_pnl
    pnl_style = "green" if pnl >= 0 else "red"
    status_icon = "🟢" if record.status == PortfolioStatus.ACTIVE else "🟡"

    console.print()
    console.print(Panel(
        f"  [bold green]▶  Resuming portfolio[/bold green]\n\n"
        f"  [bold]{record.name}[/bold]  •  {mode_icon} {record.mode.value}  •  "
        f"{agg_icon} {record.aggressiveness.value}  •  {status_icon} {record.status.value}\n"
        f"  Capital: ${record.initial_capital:,.2f}  |  "
        f"P&L: [{pnl_style}]${pnl:+,.2f}[/{pnl_style}]  |  "
        f"Trades: {record.total_trades}\n"
        f"  ID: [dim]{record.id}[/dim]",
        border_style="cyan",
        expand=False,
        padding=(0, 2),
    ))
    console.print()
