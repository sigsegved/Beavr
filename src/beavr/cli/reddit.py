"""CLI commands for Reddit meme stock trend analysis."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

if TYPE_CHECKING:
    from beavr.db.connection import Database
    from beavr.models.config import RedditConfig
    from beavr.reddit.models import MemeStockTrend, RedditScanResult

reddit_app = typer.Typer(help="Reddit meme stock trend analysis")
console = Console()


def _get_reddit_config() -> RedditConfig:
    """Load Reddit config from app settings."""
    from beavr.models.config import RedditConfig as _RedditConfig

    return _RedditConfig()


def _get_database() -> Database:
    """Get database connection."""
    from beavr.core.config import load_app_config
    from beavr.db.connection import Database as _Database

    config = load_app_config()
    config.ensure_data_dir()
    return _Database(config.database_path)


@reddit_app.command("scan")
def scan_reddit(
    subreddits: Optional[str] = typer.Option(
        None,
        "--subreddits",
        "-s",
        help="Comma-separated subreddits (default: wallstreetbets,stocks,pennystocks)",
    ),
    limit: int = typer.Option(100, "--limit", "-l", help="Max posts per subreddit"),
    min_mentions: int = typer.Option(2, "--min-mentions", "-m", help="Min mentions to qualify"),
    save: bool = typer.Option(True, "--save/--no-save", help="Save results to database"),
) -> None:
    """Scan Reddit for meme stock mentions and trends."""
    from beavr.db.reddit_store import RedditStore
    from beavr.reddit.analyzer import RedditAnalyzer
    from beavr.reddit.client import RedditClient, RedditClientError

    reddit_config = _get_reddit_config()

    sub_list = (
        [s.strip() for s in subreddits.split(",")]
        if subreddits
        else list(reddit_config.subreddits)
    )

    console.print(f"[bold]Scanning {len(sub_list)} subreddits...[/bold]")
    for sub in sub_list:
        console.print(f"  r/{sub}")

    # Fetch posts
    client = RedditClient(
        user_agent=reddit_config.user_agent,
        subreddits=sub_list,
        post_limit=min(limit, 100),
    )

    try:
        with console.status("[bold green]Fetching posts from Reddit..."):
            posts = client.fetch_all_posts()
    except RedditClientError as e:
        console.print(f"[red]Error fetching from Reddit: {e}[/red]")
        raise typer.Exit(1) from e

    if not posts:
        console.print("[yellow]No posts fetched. Reddit may be rate-limiting.[/yellow]")
        raise typer.Exit(0)

    console.print(f"[green]Fetched {len(posts)} unique posts[/green]")

    # Analyze
    analyzer = RedditAnalyzer(min_mentions=min_mentions)
    with console.status("[bold green]Analyzing posts for ticker mentions..."):
        result = analyzer.scan(posts, subreddits=sub_list)

    # Save to database
    if save:
        try:
            db = _get_database()
            store = RedditStore(db)
            store.save_scan(result)
            console.print(f"[dim]Scan saved (ID: {result.scan_id[:8]}...)[/dim]")
        except Exception as e:
            console.print(f"[yellow]Warning: Could not save scan: {e}[/yellow]")

    # Display results
    _print_scan_result(result)


@reddit_app.command("trending")
def show_trending(
    top: int = typer.Option(20, "--top", "-n", help="Number of trending tickers to show"),
) -> None:
    """Show trending meme stocks from the latest scan."""
    from beavr.db.reddit_store import RedditStore

    db = _get_database()
    store = RedditStore(db)
    result = store.get_latest_scan()

    if result is None:
        console.print("[yellow]No scan data found. Run 'bvr reddit scan' first.[/yellow]")
        raise typer.Exit(0)

    console.print(f"[dim]Latest scan: {result.scanned_at.strftime('%Y-%m-%d %H:%M UTC')}[/dim]")
    _print_trending_table(result.trends[:top])


@reddit_app.command("sentiment")
def show_sentiment(
    ticker: str = typer.Argument(..., help="Stock ticker symbol (e.g., GME)"),
) -> None:
    """Show Reddit sentiment details for a specific ticker."""
    from beavr.db.reddit_store import RedditStore

    ticker = ticker.upper()
    db = _get_database()
    store = RedditStore(db)

    # Get latest scan
    result = store.get_latest_scan()
    if result is None:
        console.print("[yellow]No scan data found. Run 'bvr reddit scan' first.[/yellow]")
        raise typer.Exit(0)

    # Find ticker in trends
    trend = None
    for t in result.trends:
        if t.ticker == ticker:
            trend = t
            break

    if trend is None:
        console.print(f"[yellow]{ticker} not found in latest scan.[/yellow]")
        # Check history
        history = store.get_ticker_history(ticker, limit=5)
        if history:
            console.print(f"[dim]But found {len(history)} historical entries:[/dim]")
            _print_ticker_history(ticker, history)
        raise typer.Exit(0)

    # Display detailed sentiment
    _print_sentiment_detail(ticker, trend, result)

    # Show history if available
    history = store.get_ticker_history(ticker, limit=10)
    if len(history) > 1:
        console.print()
        console.print("[bold]Historical Trend[/bold]")
        _print_ticker_history(ticker, history)


@reddit_app.command("history")
def show_history(
    limit: int = typer.Option(10, "--limit", "-l", help="Number of past scans to show"),
) -> None:
    """Show past Reddit scan results."""
    from beavr.db.reddit_store import RedditStore

    db = _get_database()
    store = RedditStore(db)
    scans = store.get_scan_history(limit=limit)

    if not scans:
        console.print("[yellow]No scan history found. Run 'bvr reddit scan' first.[/yellow]")
        raise typer.Exit(0)

    table = Table(title="Reddit Scan History", show_header=True)
    table.add_column("Scan ID", style="dim")
    table.add_column("Subreddits")
    table.add_column("Posts", justify="right")
    table.add_column("Tickers", justify="right")
    table.add_column("Scanned At")

    for scan in scans:
        subs = ", ".join(str(s) for s in scan["subreddits"]) if isinstance(scan["subreddits"], list) else str(scan["subreddits"])
        table.add_row(
            str(scan["scan_id"])[:8] + "...",
            subs,
            str(scan["post_count"]),
            str(scan["ticker_count"]),
            str(scan["scanned_at"]),
        )

    console.print(table)


def _print_scan_result(result: RedditScanResult) -> None:
    """Print a formatted scan result summary."""
    console.print()
    console.print(Panel(
        f"[bold cyan]Reddit Meme Stock Scan[/bold cyan]\n"
        f"Posts analyzed: {result.post_count} | "
        f"Unique tickers: {result.ticker_count} | "
        f"Subreddits: {', '.join(result.subreddits)}",
        expand=False,
    ))

    if result.trends:
        _print_trending_table(result.trends[:20])
    else:
        console.print("[yellow]No trending tickers found matching criteria.[/yellow]")


def _print_trending_table(trends: list) -> None:
    """Print the trending tickers table."""
    table = Table(show_header=True, title="Trending Meme Stocks")
    table.add_column("#", style="dim", justify="right")
    table.add_column("Ticker", style="bold")
    table.add_column("Mentions", justify="right")
    table.add_column("Sentiment", justify="center")
    table.add_column("Score", justify="right")
    table.add_column("Engagement", justify="right")
    table.add_column("Subreddits")

    for trend in trends:
        # Sentiment coloring
        sent_val = trend.avg_sentiment
        if sent_val > 0.3:
            sent_str = f"[bold green]{sent_val:+.2f} Bullish[/bold green]"
        elif sent_val > 0.1:
            sent_str = f"[green]{sent_val:+.2f}[/green]"
        elif sent_val < -0.3:
            sent_str = f"[bold red]{sent_val:+.2f} Bearish[/bold red]"
        elif sent_val < -0.1:
            sent_str = f"[red]{sent_val:+.2f}[/red]"
        else:
            sent_str = f"[yellow]{sent_val:+.2f} Neutral[/yellow]"

        # Subreddit breakdown
        subs = ", ".join(f"r/{s}({c})" for s, c in sorted(trend.subreddit_breakdown.items()))

        engagement = f"{trend.total_post_score:,} pts / {trend.total_comments:,} cmts"

        table.add_row(
            str(trend.rank),
            trend.ticker,
            str(trend.mention_count),
            sent_str,
            f"{trend.trending_score:.1f}",
            engagement,
            subs,
        )

    console.print(table)


def _print_sentiment_detail(ticker: str, trend: MemeStockTrend, result: RedditScanResult) -> None:
    """Print detailed sentiment info for a ticker."""
    sent_val = trend.avg_sentiment
    if sent_val > 0.3:
        sent_color = "bold green"
        sent_label = "Bullish"
    elif sent_val > 0.1:
        sent_color = "green"
        sent_label = "Slightly Bullish"
    elif sent_val < -0.3:
        sent_color = "bold red"
        sent_label = "Bearish"
    elif sent_val < -0.1:
        sent_color = "red"
        sent_label = "Slightly Bearish"
    else:
        sent_color = "yellow"
        sent_label = "Neutral"

    console.print()
    console.print(Panel(
        f"[bold cyan]Sentiment Analysis: {ticker}[/bold cyan]",
        expand=False,
    ))

    info_table = Table(show_header=False, box=None, padding=(0, 2))
    info_table.add_column("Label", style="dim")
    info_table.add_column("Value")

    info_table.add_row("Ticker:", f"[bold]{ticker}[/bold]")
    info_table.add_row("Rank:", f"#{trend.rank}")
    info_table.add_row("Mentions:", str(trend.mention_count))
    info_table.add_row("Sentiment:", f"[{sent_color}]{sent_val:+.3f} ({sent_label})[/{sent_color}]")
    info_table.add_row("Trending Score:", f"{trend.trending_score:.1f}")
    info_table.add_row("Engagement:", f"{trend.total_post_score:,} upvotes / {trend.total_comments:,} comments")

    # Subreddit breakdown
    sub_parts = [f"r/{s}: {c}" for s, c in sorted(trend.subreddit_breakdown.items())]
    info_table.add_row("Subreddits:", " | ".join(sub_parts))

    console.print(info_table)

    # Show recent mentions
    ticker_mentions = [m for m in result.mentions if m.ticker == ticker]
    if ticker_mentions:
        console.print()
        console.print("[bold]Recent Mentions[/bold]")
        console.print("-" * 40)

        mention_table = Table(show_header=True, box=None, padding=(0, 1))
        mention_table.add_column("Subreddit", style="dim")
        mention_table.add_column("Post Title", max_width=50)
        mention_table.add_column("Sentiment", justify="center")
        mention_table.add_column("Score", justify="right")

        for mention in ticker_mentions[:10]:
            m_sent = mention.sentiment
            if m_sent > 0.1:
                m_sent_str = f"[green]{m_sent:+.2f}[/green]"
            elif m_sent < -0.1:
                m_sent_str = f"[red]{m_sent:+.2f}[/red]"
            else:
                m_sent_str = f"[yellow]{m_sent:+.2f}[/yellow]"

            title = mention.post_title[:50] + "..." if len(mention.post_title) > 50 else mention.post_title

            mention_table.add_row(
                f"r/{mention.subreddit}",
                title,
                m_sent_str,
                str(mention.post_score),
            )

        console.print(mention_table)


def _print_ticker_history(ticker: str, history: list[dict]) -> None:  # noqa: ARG001
    """Print historical trend data for a ticker."""
    table = Table(show_header=True, box=None, padding=(0, 1))
    table.add_column("Date", style="dim")
    table.add_column("Mentions", justify="right")
    table.add_column("Sentiment", justify="center")
    table.add_column("Rank", justify="right")
    table.add_column("Score", justify="right")

    for entry in history:
        sent = entry.get("avg_sentiment", 0.0) or 0.0
        if sent > 0.1:
            sent_str = f"[green]{sent:+.2f}[/green]"
        elif sent < -0.1:
            sent_str = f"[red]{sent:+.2f}[/red]"
        else:
            sent_str = f"[yellow]{sent:+.2f}[/yellow]"

        table.add_row(
            str(entry.get("scanned_at", ""))[:16],
            str(entry.get("mention_count", 0)),
            sent_str,
            f"#{entry.get('rank', '?')}",
            f"{entry.get('trending_score', 0):.1f}",
        )

    console.print(table)
