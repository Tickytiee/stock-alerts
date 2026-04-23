"""Backtest module — validates whether our signals actually lead to good outcomes.

Run manually:  python backtest.py

For each ticker in Tier 1 + Tier 2, walks through the last N years of daily
data, fires signals using current thresholds, and records forward returns at
+30, +60, +90 days. Compares each entry to buying SPY on the same date.

Output: a summary table printed to stdout. Interpret:
  - If avg signal return BEATS SPY by >2% -> signal is earning its keep.
  - If it matches SPY -> neutral, probably not adding value.
  - If it loses to SPY -> threshold is wrong OR signal is noise.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from statistics import mean

import pandas as pd

import config
import data
import signals as sig


BACKTEST_YEARS = 3
HOLD_WINDOWS = [30, 60, 90]   # days held after signal fires


@dataclass
class Trade:
    ticker: str
    entry_date: pd.Timestamp
    entry_price: float
    signal_key: str
    severity: str
    returns: dict    # {30: 0.05, 60: 0.08, 90: 0.12}
    spy_returns: dict


def _forward_return(df: pd.DataFrame, entry_date: pd.Timestamp, days: int) -> float | None:
    """Return the % price change from entry_date to entry_date + `days`."""
    try:
        entry = float(df.loc[entry_date, "Close"])
    except KeyError:
        return None
    target_date = entry_date + pd.Timedelta(days=days)
    future = df.loc[df.index >= target_date]
    if future.empty:
        return None
    exit_price = float(future.iloc[0]["Close"])
    return (exit_price - entry) / entry * 100


def _run_ticker(ticker: str, spy: pd.DataFrame) -> list[Trade]:
    """Walk through one ticker's history, fire signals, record forward returns."""
    # We need more than HISTORY_DAYS for backtest. Fetch fresh full history.
    df = data.fetch_history(ticker, days=260 * BACKTEST_YEARS)
    if df.empty or len(df) < 260:
        print(f"[{ticker}] skipped — not enough history")
        return []

    trades: list[Trade] = []
    # Walk day by day, starting at index 252 so we have a full year of lookback
    # for the 52-week drawdown calculation.
    for i in range(252, len(df) - max(HOLD_WINDOWS)):
        window = df.iloc[:i + 1]
        # Only look at 52 weeks of prior data for drawdown / RSI
        lookback = window.iloc[-252:]
        s = sig.detect_signals(lookback)
        if not s:
            continue

        entry_date = df.index[i]
        entry_price = float(df.iloc[i]["Close"])

        for signal in s:
            returns = {}
            spy_rets = {}
            for w in HOLD_WINDOWS:
                returns[w] = _forward_return(df, entry_date, w)
                spy_rets[w] = _forward_return(spy, entry_date, w)
            trades.append(Trade(
                ticker=ticker,
                entry_date=entry_date,
                entry_price=entry_price,
                signal_key=signal.key,
                severity=signal.severity,
                returns=returns,
                spy_returns=spy_rets,
            ))
    return trades


def _summarize(trades: list[Trade]) -> None:
    """Print a summary table grouped by (signal_key, severity)."""
    if not trades:
        print("No signals fired across the backtest period.")
        return

    groups: dict[tuple[str, str], list[Trade]] = {}
    for t in trades:
        groups.setdefault((t.signal_key, t.severity), []).append(t)

    print()
    print(f"{'Signal':<25} {'Sev':<8} {'N':>5} "
          f"{'+30d':>10} {'SPY +30d':>10} "
          f"{'+60d':>10} {'SPY +60d':>10} "
          f"{'+90d':>10} {'SPY +90d':>10}")
    print("-" * 110)

    for (key, sev), ts in sorted(groups.items()):
        n = len(ts)
        row = [f"{key:<25}", f"{sev:<8}", f"{n:>5}"]
        for w in HOLD_WINDOWS:
            vals = [t.returns[w] for t in ts if t.returns[w] is not None]
            spys = [t.spy_returns[w] for t in ts if t.spy_returns[w] is not None]
            avg = mean(vals) if vals else 0.0
            spy_avg = mean(spys) if spys else 0.0
            row.extend([f"{avg:>+9.2f}%", f"{spy_avg:>+9.2f}%"])
        print(" ".join(row))

    print()
    print("Interpretation:")
    print("  * If signal return beats SPY by >2% at 60-90d -> signal is useful")
    print("  * If signal return ≈ SPY -> neutral, not adding alpha")
    print("  * If signal return < SPY -> threshold too loose OR signal is noise")


def main() -> None:
    print(f"Backtesting {BACKTEST_YEARS} years, holds {HOLD_WINDOWS}...")
    spy = data.fetch_history("SPY", days=260 * BACKTEST_YEARS + 30)

    universe = config.TIER_1_HOLDINGS + config.TIER_2_WATCHLIST
    all_trades: list[Trade] = []
    for t in universe:
        try:
            trades = _run_ticker(t, spy)
            print(f"[{t}] {len(trades)} signals")
            all_trades.extend(trades)
        except Exception as e:
            print(f"[{t}] backtest failed: {e}")

    _summarize(all_trades)


if __name__ == "__main__":
    main()
