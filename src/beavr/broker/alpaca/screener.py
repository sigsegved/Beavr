"""Alpaca screener adapter implementing ScreenerProvider protocol."""

from __future__ import annotations

import logging
from decimal import Decimal

from beavr.broker.models import BrokerError

logger = logging.getLogger(__name__)


class AlpacaScreener:
    """ScreenerProvider implementation for Alpaca."""

    def __init__(self, api_key: str, api_secret: str) -> None:
        try:
            from alpaca.data import (
                MarketMoversRequest,
                MostActivesBy,
                MostActivesRequest,
                ScreenerClient,
            )

            self._client = ScreenerClient(api_key, api_secret)
            self._MarketMoversRequest = MarketMoversRequest
            self._MostActivesRequest = MostActivesRequest
            self._MostActivesBy = MostActivesBy
        except ImportError as err:
            raise ImportError("alpaca-py required for screener") from err

    def get_market_movers(self, top: int = 10) -> list[dict]:
        """Return top gainers and losers."""
        try:
            response = self._client.get_market_movers(
                self._MarketMoversRequest(top=top)
            )
            result: list[dict] = []
            for mover in response.gainers[:top]:
                result.append(
                    {
                        "symbol": mover.symbol,
                        "price": Decimal(str(mover.price)),
                        "percent_change": float(mover.percent_change),
                        "type": "gainer",
                    }
                )
            for mover in response.losers[:top]:
                result.append(
                    {
                        "symbol": mover.symbol,
                        "price": Decimal(str(mover.price)),
                        "percent_change": float(mover.percent_change),
                        "type": "loser",
                    }
                )
            return result
        except Exception as e:
            raise BrokerError(
                error_code="screener_error",
                message=f"Failed to get market movers: {e}",
                broker_name="alpaca",
            ) from e

    def get_most_actives(self, top: int = 20) -> list[dict]:
        """Return most actively traded stocks by volume."""
        try:
            response = self._client.get_most_actives(
                self._MostActivesRequest(
                    top=top, by=self._MostActivesBy.VOLUME
                )
            )
            return [
                {
                    "symbol": a.symbol,
                    "volume": int(a.volume) if a.volume else None,
                    "trade_count": (
                        int(a.trade_count) if a.trade_count else None
                    ),
                }
                for a in response.most_actives[:top]
            ]
        except Exception as e:
            raise BrokerError(
                error_code="screener_error",
                message=f"Failed to get most actives: {e}",
                broker_name="alpaca",
            ) from e
