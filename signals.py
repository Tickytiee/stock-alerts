"""Signal detection — pure functions, no network, no I/O.

Given price data, produces a list of (key, message, severity) tuples.
Easy to test: feed in historical data, assert expected signals.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

import config


@dataclass
class Signal:
    key: str            # e.g. "rsi_oversold" — used for dedupe
    message: str        # human-readable line
    severity: str       # "normal" | "strong"


def compute_rsi(prices: pd.Series, period: int = 14) -> float:
    """Standard 14-period RSI. Returns the most recent value."""
    delta = prices.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return float(rsi.iloc[-1])


def compute_drawdown_pct(prices: pd.Series) -> tuple[float, float]:
    """
    Returns (drawdown_pct, high_52w).
    drawdown_pct is negative: e.g. -15.3 means price is 15.3% below 52w high.
    """
    high = float(prices.max())
    current = float(prices.iloc[-1])
    dd = (current - high) / high * 100
    return dd, high


def detect_signals(history: pd.DataFrame) -> list[Signal]:
    """Return all signals currently firing for this price history."""
    signals: list[Signal] = []
    close = history["Close"]

    rsi = compute_rsi(close)
    drawdown_pct, high = compute_drawdown_pct(close)
    current_price = float(close.iloc[-1])

    # Signal 1: RSI oversold
    if rsi < config.RSI_OVERSOLD:
        severity = "strong" if rsi < config.RSI_OVERSOLD_STRONG else "normal"
        signals.append(Signal(
            key="rsi_oversold",
            message=f"🟢 RSI oversold at {rsi:.1f}",
            severity=severity,
        ))

    # Signal 2: drawdown from 52-week high
    if drawdown_pct <= -config.DRAWDOWN_PCT:
        severity = "strong" if drawdown_pct <= -config.DRAWDOWN_PCT_STRONG else "normal"
        signals.append(Signal(
            key="drawdown",
            message=f"📉 Down {drawdown_pct:.1f}% from 52w high (${high:.2f})",
            severity=severity,
        ))

    # Confluence — if BOTH fire, upgrade overall severity to strong
    if len(signals) >= 2 and all(s.severity == "normal" for s in signals):
        signals = [Signal(s.key, s.message, "strong") for s in signals]

    return signals


def summary_line(ticker: str, history: pd.DataFrame) -> str:
    """One-line readout for logs / health checks — not user-facing."""
    close = history["Close"]
    price = float(close.iloc[-1])
    rsi = compute_rsi(close)
    dd, _ = compute_drawdown_pct(close)
    return f"{ticker}: ${price:.2f} | RSI {rsi:.1f} | DD {dd:.1f}%"
