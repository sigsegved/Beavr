"""Earnings calendar data fetcher.

Fetches upcoming earnings announcements from external APIs and stores
them as ``MarketEvent`` records for the orchestrator to process.

Primary source is Alpha Vantage (free REST API), with yfinance as
fallback.  Both are called lazily — only when the imports succeed.
"""

from __future__ import annotations

import csv
import io
import logging
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from beavr.models.market_event import EventImportance, EventType, MarketEvent

logger = logging.getLogger(__name__)


class EarningsCalendarFetcher:
    """Fetches upcoming earnings dates from external APIs.

    Parameters
    ----------
    events_store:
        Any object implementing the ``EventStore`` protocol
        (``save_event`` / ``get_upcoming_earnings``).
    api_key:
        Alpha Vantage API key.  Falls back to
        ``ALPHA_VANTAGE_API_KEY`` env-var when *None*.
    """

    def __init__(
        self,
        events_store: Any,
        api_key: Optional[str] = None,
    ) -> None:
        self.events_store = events_store
        self.api_key = api_key or self._env_api_key()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fetch_upcoming_earnings(
        self,
        horizon_days: int = 14,
    ) -> list[MarketEvent]:
        """Fetch earnings calendar and store as ``MarketEvent`` records.

        1. Try Alpha Vantage ``EARNINGS_CALENDAR`` (if API key set).
        2. Fall back to yfinance.
        3. De-duplicate against existing events in DB.
        4. Store new events as ``EARNINGS_UPCOMING`` type.

        Returns the *newly created* events (excludes duplicates).
        """
        raw: list[dict[str, Any]] = []

        if self.api_key:
            try:
                raw = self._fetch_alpha_vantage(horizon_days=horizon_days)
                logger.info(f"📅 Alpha Vantage: fetched {len(raw)} earnings records")
            except Exception as exc:
                logger.warning(f"Alpha Vantage fetch failed, trying yfinance: {exc}")

        if not raw:
            try:
                raw = self._fetch_yfinance_calendar(horizon_days=horizon_days)
                logger.info(f"📅 yfinance: fetched {len(raw)} earnings records")
            except Exception as exc:
                logger.warning(f"yfinance fetch failed: {exc}")

        if not raw:
            logger.info("📅 No earnings data available from any source")
            return []

        # Convert to MarketEvent and de-duplicate
        cutoff = date.today() + timedelta(days=horizon_days)
        events = self._convert_to_events(raw, cutoff)
        new_events = self._deduplicate_and_store(events)
        logger.info(f"📅 Stored {len(new_events)} new earnings events ({len(events)} total fetched)")
        return new_events

    def fetch_earnings_for_symbols(
        self,
        symbols: list[str],
    ) -> list[MarketEvent]:
        """Fetch next earnings date for specific symbols (e.g., watchlist).

        Uses yfinance per-symbol lookups.  Returns events that were
        newly created (i.e.  not already in the database).
        """
        raw: list[dict[str, Any]] = []
        try:
            raw = self._fetch_yfinance_symbols(symbols)
        except Exception as exc:
            logger.warning(f"yfinance symbol fetch failed: {exc}")
            return []

        events = self._convert_to_events(raw, cutoff=None)
        return self._deduplicate_and_store(events)

    # ------------------------------------------------------------------
    # Alpha Vantage
    # ------------------------------------------------------------------

    def _fetch_alpha_vantage(
        self,
        horizon_days: int = 14,
    ) -> list[dict[str, Any]]:
        """Call the Alpha Vantage EARNINGS_CALENDAR endpoint (CSV)."""
        import requests

        horizon_map = {
            3: "3month",
            6: "6month",
            12: "12month",
        }
        horizon_str = "3month"
        for months, label in sorted(horizon_map.items()):
            if horizon_days <= months * 30:
                horizon_str = label
                break

        url = "https://www.alphavantage.co/query"
        params = {
            "function": "EARNINGS_CALENDAR",
            "horizon": horizon_str,
            "apikey": self.api_key,
        }
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()

        reader = csv.DictReader(io.StringIO(resp.text))
        results: list[dict[str, Any]] = []
        cutoff = date.today() + timedelta(days=horizon_days)

        for row in reader:
            report_date_str = row.get("reportDate", "")
            if not report_date_str:
                continue
            try:
                report_date = date.fromisoformat(report_date_str)
            except ValueError:
                continue
            if report_date > cutoff:
                continue
            results.append({
                "symbol": row.get("symbol", ""),
                "name": row.get("name", ""),
                "earnings_date": report_date,
                "estimate_eps": row.get("estimate", ""),
                "source": "alpha_vantage",
            })

        return results

    # ------------------------------------------------------------------
    # yfinance
    # ------------------------------------------------------------------

    def _fetch_yfinance_calendar(
        self,
        _horizon_days: int = 14,
    ) -> list[dict[str, Any]]:
        """Fetch broad earnings calendar from yfinance (limited)."""
        # yfinance does not have a bulk calendar endpoint like AV,
        # but we can look up individual tickers.  For the calendar
        # use-case this is a no-op — the per-symbol fallback is
        # used via fetch_earnings_for_symbols instead.
        return []

    def _fetch_yfinance_symbols(
        self,
        symbols: list[str],
    ) -> list[dict[str, Any]]:
        """Fetch next earnings date per symbol via yfinance."""
        try:
            import yfinance as yf  # type: ignore[import-untyped]
        except ImportError:
            logger.warning("yfinance not installed — skipping fallback")
            return []

        results: list[dict[str, Any]] = []
        for symbol in symbols:
            try:
                ticker = yf.Ticker(symbol)
                cal = ticker.calendar
                if cal is None or cal.empty if hasattr(cal, "empty") else not cal:
                    continue

                # yfinance returns a dict or DataFrame depending on version
                if isinstance(cal, dict):
                    earnings_date = cal.get("Earnings Date")
                    eps_est = cal.get("EPS Estimate")
                    rev_est = cal.get("Revenue Estimate")
                else:
                    # DataFrame format
                    earnings_date = cal.iloc[0].get("Earnings Date") if len(cal) > 0 else None
                    eps_est = cal.iloc[0].get("EPS Estimate") if len(cal) > 0 else None
                    rev_est = cal.iloc[0].get("Revenue Estimate") if len(cal) > 0 else None

                if earnings_date:
                    if isinstance(earnings_date, datetime):
                        earnings_date = earnings_date.date()
                    elif isinstance(earnings_date, str):
                        earnings_date = date.fromisoformat(earnings_date)

                    results.append({
                        "symbol": symbol,
                        "name": symbol,
                        "earnings_date": earnings_date,
                        "estimate_eps": str(eps_est) if eps_est else "",
                        "estimate_revenue": str(rev_est) if rev_est else "",
                        "source": "yfinance",
                    })
            except Exception as exc:
                logger.debug(f"yfinance lookup failed for {symbol}: {exc}")

        return results

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _env_api_key() -> Optional[str]:
        """Read Alpha Vantage key from environment."""
        import os

        return os.environ.get("ALPHA_VANTAGE_API_KEY")

    def _convert_to_events(
        self,
        raw: list[dict[str, Any]],
        cutoff: Optional[date],
    ) -> list[MarketEvent]:
        """Convert raw earnings dicts to MarketEvent objects."""
        events: list[MarketEvent] = []
        for row in raw:
            symbol = row.get("symbol", "")
            if not symbol:
                continue
            earnings_date: Optional[date] = row.get("earnings_date")
            if cutoff and earnings_date and earnings_date > cutoff:
                continue

            eps_str = str(row.get("estimate_eps", "")).strip()
            estimate_eps: Optional[Decimal] = None
            if eps_str:
                try:
                    estimate_eps = Decimal(eps_str)
                except InvalidOperation:
                    pass

            rev_str = str(row.get("estimate_revenue", "")).strip()
            estimate_revenue: Optional[Decimal] = None
            if rev_str:
                try:
                    estimate_revenue = Decimal(rev_str)
                except InvalidOperation:
                    pass

            name = row.get("name", symbol)
            source = row.get("source", "earnings_calendar")

            event = MarketEvent(
                event_type=EventType.EARNINGS_UPCOMING,
                symbol=symbol,
                headline=f"Earnings upcoming: {name} ({symbol})",
                summary=(
                    f"{name} reports earnings on "
                    f"{earnings_date.isoformat() if earnings_date else 'TBD'}."
                    + (f" EPS estimate: ${estimate_eps}" if estimate_eps else "")
                ),
                source=source,
                event_date=earnings_date,
                earnings_date=earnings_date,
                importance=EventImportance.HIGH,
                estimate_eps=estimate_eps,
                estimate_revenue=estimate_revenue,
            )
            events.append(event)

        return events

    def _deduplicate_and_store(
        self,
        events: list[MarketEvent],
    ) -> list[MarketEvent]:
        """Store events, skipping duplicates (same symbol+date)."""
        if not self.events_store:
            return events

        # Get existing upcoming earnings to de-dupe
        try:
            existing = self.events_store.get_upcoming_earnings(days_ahead=90)
            existing_keys = {
                (e.symbol, e.earnings_date)
                for e in existing
                if e.symbol and e.earnings_date
            }
        except Exception:
            existing_keys = set()

        new_events: list[MarketEvent] = []
        for event in events:
            key = (event.symbol, event.earnings_date)
            if key in existing_keys:
                continue
            try:
                self.events_store.save_event(event)
                new_events.append(event)
                existing_keys.add(key)
            except Exception as exc:
                logger.warning(f"Failed to store earnings event for {event.symbol}: {exc}")

        return new_events
