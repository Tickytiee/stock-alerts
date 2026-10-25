"""Backtest the weekly digest — did its top picks actually beat SPY?

Rewinds time: for every Sunday in the last N years, runs the same scoring
logic weekly_digest.py uses, picks the top-ranked ticker, and records what
its forward return would have been at 30/60/90 days. Compares to SPY entered
on the same date.

Run locally — this is a one-shot analytical tool, not a scheduled job.

Metrics it answers:
  1. Does the top pick beat SPY on average? (Core question.)
  2. Hit rate — what % of top picks actually beat SPY?
  3. Does rank matter? (Rank-1 vs rank-2 vs rank-3 forward returns.)
  4. Dumb baseline — biggest-drawdown-each-week vs smart ranking.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from statistics import mean, median

import pandas as pd

import config
import data
import signals as sig
from weekly_digest import _score


BACKTEST_YEARS = 2
HOLD_WINDOWS = [30, 60, 90]
MIN_SCORE = 2


@dataclass
class WeeklyResult:
    sunday: pd.Timestamp
    rank: int
    ticker: str
    score: int
    entry_price: float
    returns: dict        # {30: 0.05, 60: ..., 90: ...}
    spy_returns: dict    # SPY same-day entry, same horizons
    dumb_pick: str       # biggest-drawdown ticker that week
    dumb_returns: dict


def _forward_return(df: pd.DataFrame, entry_date: pd.Timestamp, days: int) -> float | None:
    """% change from entry close to close `days` later (next trading day on/after)."""
    try:
        entry = float(df.loc[entry_date, "Close"])
    except KeyError:
        # Find first trading day on/after entry_date
        future = df.loc[df.index >= entry_date]
        if future.empty:
            return None
        entry = float(future.iloc[0]["Close"])
        entry_date = future.index[0]

    target = entry_date + pd.Timedelta(days=days)
    future = df.loc[df.index >= target]
    if future.empty:
        return None
    exit_price = float(future.iloc[0]["Close"])
    return (exit_price - entry) / entry * 100


def _slice_to(df: pd.DataFrame, cutoff: pd.Timestamp) -> pd.DataFrame:
    """Only rows at or before cutoff — simulates what we knew that Sunday."""
    return df.loc[df.index <= cutoff]


def _rank_sunday(sunday: pd.Timestamp, all_data: dict[str, pd.DataFrame]) -> list[tuple]:
    """
    Run the digest scoring for one historical Sunday.
    Returns ranked list of (ticker, tier, score, firing_signals, drawdown_pct).
    """
    scored = []
    for ticker, df in all_data.items():
        past = _slice_to(df, sunday)
        if len(past) < 260:  # need ~1y lookback for 52w drawdown
            continue
        # Use only the last 260 rows for signal detection (same as live bot)
        lookback = past.iloc[-260:]
        firing = sig.detect_signals(lookback)
        if not firing:
            continue

        tier = 1 if ticker in config.TIER_1_HOLDINGS else 2
        score, _ = _score(firing, tier)
        if score < MIN_SCORE:
            continue

        # Also compute raw drawdown for the "dumb baseline" strategy
        dd, _ = sig.compute_drawdown_pct(lookback)

        scored.append((ticker, tier, score, firing, dd))

    # Sort by score desc, then by largest drawdown as tiebreak, then alphabetical
    scored.sort(key=lambda x: (-x[2], x[4], x[0]))
    return scored


def _dumb_pick(sunday: pd.Timestamp, all_data: dict[str, pd.DataFrame]) -> tuple[str, float] | None:
    """Baseline strategy: just pick the biggest drawdown that week, no scoring."""
    worst_dd = 0
    worst_ticker = None
    worst_price = None
    for ticker, df in all_data.items():
        past = _slice_to(df, sunday)
        if len(past) < 260:
            continue
        lookback = past.iloc[-260:]
        dd, _ = sig.compute_drawdown_pct(lookback)
        if dd < worst_dd:
            worst_dd = dd
            worst_ticker = ticker
            worst_price = float(lookback["Close"].iloc[-1])
    if worst_ticker is None:
        return None
    return worst_ticker, worst_price


def _run_backtest() -> list[WeeklyResult]:
    """Walk every Sunday, score, record forward returns."""
    print(f"Fetching {BACKTEST_YEARS} years of data for all tickers + SPY...")
    universe = config.TIER_1_HOLDINGS + config.TIER_2_WATCHLIST + ["SPY"]
    all_data: dict[str, pd.DataFrame] = {}
    for t in universe:
        try:
            df = data.fetch_history(t, days=260 * (BACKTEST_YEARS + 1))
            all_data[t] = df
            print(f"  {t}: {len(df)} rows")
        except Exception as e:
            print(f"  {t}: failed ({e})")

    spy = all_data.get("SPY")
    if spy is None or spy.empty:
        print("SPY data missing — can't compute benchmarks. Aborting.")
        return []

    # Find all Sundays in the backtest window
    end = pd.Timestamp(date.today())
    start = end - pd.Timedelta(days=365 * BACKTEST_YEARS)
    sundays = pd.date_range(start, end, freq="W-SUN")

    results: list[WeeklyResult] = []
    for sunday in sundays:
        ranked = _rank_sunday(sunday, all_data)
        if not ranked:
            continue

        dumb = _dumb_pick(sunday, all_data)

        # Record top 3 ranks for rank-correlation analysis
        for rank_idx, (ticker, tier, score, firing, dd) in enumerate(ranked[:3], start=1):
            df = all_data[ticker]
            lookback = _slice_to(df, sunday).iloc[-260:]
            entry_price = float(lookback["Close"].iloc[-1])

            returns = {w: _forward_return(df, sunday, w) for w in HOLD_WINDOWS}
            spy_returns = {w: _forward_return(spy, sunday, w) for w in HOLD_WINDOWS}

            dumb_rets = {}
            dumb_ticker = ""
            if dumb:
                dumb_ticker, _dumb_price = dumb
                dumb_df = all_data[dumb_ticker]
                dumb_rets = {w: _forward_return(dumb_df, sunday, w) for w in HOLD_WINDOWS}

            results.append(WeeklyResult(
                sunday=sunday,
                rank=rank_idx,
                ticker=ticker,
                score=score,
                entry_price=entry_price,
                returns=returns,
                spy_returns=spy_returns,
                dumb_pick=dumb_ticker,
                dumb_returns=dumb_rets,
            ))

    return results


def _summarize(results: list[WeeklyResult]) -> None:
    if not results:
        print("No results.")
        return

    print()
    print("=" * 90)
    print(f"Backtest covered {len({r.sunday for r in results})} Sundays")
    print("=" * 90)

    # --- Q1: Top pick vs SPY ---
    print("\n[Q1] Top pick vs SPY (the main question)")
    print(f"{'Horizon':<10} {'TopPick avg':>14} {'SPY avg':>12} {'Edge':>10} {'Hit rate':>12}")
    rank1 = [r for r in results if r.rank == 1]
    for w in HOLD_WINDOWS:
        picks = [r.returns[w] for r in rank1 if r.returns[w] is not None]
        spys = [r.spy_returns[w] for r in rank1 if r.spy_returns[w] is not None]
        if not picks:
            continue
        pick_avg = mean(picks)
        spy_avg = mean(spys)
        edge = pick_avg - spy_avg
        wins = sum(1 for r in rank1
                   if r.returns[w] is not None and r.spy_returns[w] is not None
                   and r.returns[w] > r.spy_returns[w])
        hit = wins / len(picks) * 100
        print(f"+{w:<9}d {pick_avg:>+13.2f}% {spy_avg:>+11.2f}% {edge:>+9.2f}% {hit:>11.1f}%")

    # --- Q2: Does rank matter? ---
    print("\n[Q2] Does rank matter? (90-day returns by rank)")
    print(f"{'Rank':<10} {'N':>5} {'Avg return':>14} {'Median':>12}")
    for r_target in [1, 2, 3]:
        rows = [r for r in results if r.rank == r_target]
        rets = [r.returns[90] for r in rows if r.returns[90] is not None]
        if not rets:
            continue
        print(f"Rank {r_target:<5} {len(rets):>5} {mean(rets):>+13.2f}% {median(rets):>+11.2f}%")

    # --- Q3: Smart vs Dumb baseline ---
    print("\n[Q3] Smart ranking vs dumb baseline (biggest-drawdown-wins)")
    print(f"{'Horizon':<10} {'Smart avg':>12} {'Dumb avg':>12} {'Edge':>10}")
    for w in HOLD_WINDOWS:
        smart = [r.returns[w] for r in rank1 if r.returns[w] is not None]
        dumb = [r.dumb_returns.get(w) for r in rank1 if r.dumb_returns.get(w) is not None]
        if not smart or not dumb:
            continue
        s_avg = mean(smart)
        d_avg = mean(dumb)
        print(f"+{w:<9}d {s_avg:>+11.2f}% {d_avg:>+11.2f}% {s_avg - d_avg:>+9.2f}%")

    # --- Interpretation guide ---
    print()
    print("Interpretation:")
    print("  Q1 edge > +2% at 90d  -> digest adds real value vs just buying SPY")
    print("  Q1 edge <= +1%        -> digest is noise, SPY wins")
    print("  Q2 rank-1 > rank-3    -> the SCORE matters, ranking logic works")
    print("  Q2 ranks ~equal       -> score is cosmetic, pick any firing signal")
    print("  Q3 smart > dumb       -> ranking beats 'just buy the biggest drop'")
    print("  Q3 smart = dumb       -> fancy scoring == naive, simplify")


def main() -> None:
    print(f"=== Weekly Digest Backtest ({BACKTEST_YEARS} years) ===")
    results = _run_backtest()
    _summarize(results)


if __name__ == "__main__":
    main()
