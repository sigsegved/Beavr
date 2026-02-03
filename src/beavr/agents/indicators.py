"""Technical indicator calculations for agent context."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pandas as pd


def calculate_indicators(bars: pd.DataFrame) -> dict[str, float]:
    """
    Calculate technical indicators from OHLCV bars.

    Args:
        bars: DataFrame with columns [open, high, low, close, volume]

    Returns:
        Dictionary of indicator values
    """
    if bars.empty or len(bars) < 14:
        return {}

    close = bars["close"].astype(float)
    high = bars["high"].astype(float)
    low = bars["low"].astype(float)
    volume = bars["volume"].astype(float)

    indicators: dict[str, float] = {}

    # Current price
    indicators["current_price"] = close.iloc[-1]

    # Simple Moving Averages
    if len(close) >= 10:
        indicators["sma_10"] = close.rolling(10).mean().iloc[-1]
    if len(close) >= 20:
        indicators["sma_20"] = close.rolling(20).mean().iloc[-1]
    if len(close) >= 50:
        indicators["sma_50"] = close.rolling(50).mean().iloc[-1]

    # RSI (14-period)
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss.replace(0, 0.001)
    rsi = 100 - (100 / (1 + rs))
    indicators["rsi_14"] = rsi.iloc[-1]

    # MACD
    if len(close) >= 26:
        ema_12 = close.ewm(span=12, adjust=False).mean()
        ema_26 = close.ewm(span=26, adjust=False).mean()
        macd_line = ema_12 - ema_26
        signal_line = macd_line.ewm(span=9, adjust=False).mean()
        indicators["macd"] = macd_line.iloc[-1]
        indicators["macd_signal"] = signal_line.iloc[-1]
        indicators["macd_histogram"] = (macd_line - signal_line).iloc[-1]

    # Bollinger Bands
    if len(close) >= 20:
        sma_20 = close.rolling(20).mean()
        std_20 = close.rolling(20).std()
        bb_upper = (sma_20 + 2 * std_20).iloc[-1]
        bb_lower = (sma_20 - 2 * std_20).iloc[-1]
        indicators["bb_upper"] = bb_upper
        indicators["bb_lower"] = bb_lower
        if bb_upper != bb_lower:
            indicators["bb_pct"] = (close.iloc[-1] - bb_lower) / (bb_upper - bb_lower)
        else:
            indicators["bb_pct"] = 0.5

    # Average True Range (volatility)
    tr = pd.concat(
        [
            high - low,
            (high - close.shift()).abs(),
            (low - close.shift()).abs(),
        ],
        axis=1,
    ).max(axis=1)
    indicators["atr_14"] = tr.rolling(14).mean().iloc[-1]

    # ATR as percentage of price
    if indicators.get("atr_14") and close.iloc[-1] > 0:
        indicators["atr_pct"] = (indicators["atr_14"] / close.iloc[-1]) * 100

    # Volume analysis
    if len(volume) >= 20:
        vol_sma = volume.rolling(20).mean().iloc[-1]
        indicators["volume_sma_20"] = vol_sma
        if vol_sma > 0:
            indicators["volume_ratio"] = volume.iloc[-1] / vol_sma
        else:
            indicators["volume_ratio"] = 1.0

    # Price vs SMAs
    if "sma_20" in indicators and indicators["sma_20"] > 0:
        indicators["price_vs_sma20"] = (
            (close.iloc[-1] / indicators["sma_20"] - 1) * 100
        )
    if "sma_50" in indicators and indicators["sma_50"] > 0:
        indicators["price_vs_sma50"] = (
            (close.iloc[-1] / indicators["sma_50"] - 1) * 100
        )

    # Recent price changes
    if len(close) >= 5:
        indicators["change_1d"] = ((close.iloc[-1] / close.iloc[-2]) - 1) * 100
        indicators["change_5d"] = ((close.iloc[-1] / close.iloc[-5]) - 1) * 100
    if len(close) >= 20:
        indicators["change_20d"] = ((close.iloc[-1] / close.iloc[-20]) - 1) * 100

    # Round all values
    return {k: round(v, 4) if isinstance(v, float) else v for k, v in indicators.items()}


def build_agent_context_indicators(
    bars_by_symbol: dict[str, pd.DataFrame],
) -> dict[str, dict[str, float]]:
    """
    Build indicators dictionary for AgentContext.

    Args:
        bars_by_symbol: Symbol -> DataFrame mapping

    Returns:
        Symbol -> indicators mapping
    """
    return {
        symbol: calculate_indicators(bars)
        for symbol, bars in bars_by_symbol.items()
        if not bars.empty
    }


def bars_to_dict_list(bars: pd.DataFrame, n: int = 10) -> list[dict[str, Any]]:
    """
    Convert recent bars to list of dicts for agent context.

    Args:
        bars: DataFrame with OHLCV data
        n: Number of recent bars to include

    Returns:
        List of bar dictionaries
    """
    if bars.empty:
        return []

    recent = bars.tail(n)
    result = []
    for idx, row in recent.iterrows():
        bar_dict = {
            "date": str(idx.date()) if hasattr(idx, "date") else str(idx),
            "open": float(row.get("open", 0)),
            "high": float(row.get("high", 0)),
            "low": float(row.get("low", 0)),
            "close": float(row.get("close", 0)),
            "volume": float(row.get("volume", 0)),
        }
        result.append(bar_dict)
    return result
