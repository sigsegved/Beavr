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
from rich.console import Console
from rich.panel import Panel

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
    console.print(
        Panel(
            "[bold]Beavr AI — Portfolio Setup[/bold]",
            border_style="cyan",
            expand=False,
        )
    )

    portfolios = portfolio_store.list_portfolios()

    if not portfolios:
        console.print("\nNo existing portfolios found — let's create one.\n")
        return _interactive_create(portfolio_store)

    console.print("\n[bold]Existing portfolios:[/bold]")
    for idx, pf in enumerate(portfolios, start=1):
        pnl = pf.realized_pnl
        pnl_sign = "+" if pnl >= 0 else ""
        status_style = "green" if pf.status == PortfolioStatus.ACTIVE else "yellow"
        console.print(
            f"  [cyan][{idx}][/cyan] {pf.name} "
            f"({pf.mode.value}, [{status_style}]{pf.status.value}[/{status_style}], "
            f"{pnl_sign}${pnl:,.2f})"
        )
    console.print("  [cyan][N][/cyan] Create new portfolio\n")

    choice = typer.prompt(
        "Select portfolio",
        default="N" if not portfolios else "1",
    )

    if choice.upper() == "N":
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
    console.print("[bold]Create New Portfolio[/bold]\n")

    # --- Name ---
    name = typer.prompt("Portfolio name")
    if not name.strip():
        console.print("[red]Error:[/red] Name cannot be empty.")
        raise typer.Exit(1)
    name = name.strip()

    # Check uniqueness
    if portfolio_store.get_portfolio_by_name(name) is not None:
        console.print(f"[red]Error:[/red] Portfolio [bold]{name}[/bold] already exists.")
        raise typer.Exit(1)

    # --- Mode ---
    console.print("  [cyan][1][/cyan] Paper trading")
    console.print("  [cyan][2][/cyan] Live trading")
    mode_choice = typer.prompt("Select mode", default="1")
    if mode_choice == "1":
        mode = TradingMode.PAPER
    elif mode_choice == "2":
        mode = TradingMode.LIVE
    else:
        console.print(f"[red]Error:[/red] Invalid mode selection: {mode_choice}")
        raise typer.Exit(1)

    # --- Aggressiveness ---
    console.print("  [cyan][1][/cyan] Conservative")
    console.print("  [cyan][2][/cyan] Moderate")
    console.print("  [cyan][3][/cyan] Aggressive")
    agg_choice = typer.prompt("Select aggressiveness", default="2")
    agg_map = {
        "1": Aggressiveness.CONSERVATIVE,
        "2": Aggressiveness.MODERATE,
        "3": Aggressiveness.AGGRESSIVE,
    }
    if agg_choice not in agg_map:
        console.print(f"[red]Error:[/red] Invalid aggressiveness selection: {agg_choice}")
        raise typer.Exit(1)
    aggressiveness = agg_map[agg_choice]

    # --- Directives ---
    console.print(
        "\nEnter trading directives (one per line, empty line to finish):"
    )
    directives: list[str] = []
    while True:
        line = typer.prompt("", default="", show_default=False)
        if not line.strip():
            break
        directives.append(line.strip())

    # --- Capital ---
    capital_str = typer.prompt("Initial capital ($)", default=str(_DEFAULT_CAPITAL))
    try:
        capital = Decimal(capital_str)
        if capital <= 0:
            raise InvalidOperation
    except (InvalidOperation, ValueError):
        console.print(f"[red]Error:[/red] Invalid capital amount: {capital_str}")
        raise typer.Exit(1) from None

    capital_pct_str = typer.prompt(
        "Capital % to allocate for trading",
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
    allocated = capital * Decimal(str(capital_pct)) / Decimal("100")
    dir_display = "\n".join(f"  - {d}" for d in directives) if directives else "  (none)"
    summary = (
        f"[bold]Name:[/bold]            {name}\n"
        f"[bold]Mode:[/bold]            {mode.value}\n"
        f"[bold]Aggressiveness:[/bold]  {aggressiveness.value}\n"
        f"[bold]Directives:[/bold]\n{dir_display}\n"
        f"[bold]Capital:[/bold]         ${capital:,.2f}\n"
        f"[bold]Allocated:[/bold]       ${allocated:,.2f} ({capital_pct}%)"
    )
    console.print(Panel(summary, title="New Portfolio Summary", border_style="green"))

    if not typer.confirm("Create this portfolio?", default=True):
        console.print("[yellow]Cancelled.[/yellow]")
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

    console.print(f"\n[green]✓[/green] Portfolio [bold]{name}[/bold] created (id={portfolio_id})")
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

    console.print(
        f"[green]✓[/green] Portfolio [bold]{name}[/bold] created "
        f"(mode={validated_mode.value}, aggressiveness={validated_agg.value}, "
        f"capital=${resolved_capital:,.2f})"
    )
    return record


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _print_resume(record: PortfolioRecord) -> None:
    """Print a brief resume message for an existing portfolio."""
    console.print(
        f"[green]✓[/green] Resuming portfolio [bold]{record.name}[/bold] "
        f"(id={record.id}, mode={record.mode.value}, status={record.status.value})"
    )
