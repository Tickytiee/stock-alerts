"""Data layer — cache-first access to price history.

The only module that touches yfinance. If we swap data sources later, this is
the only file that changes.
"""

from __future__ import annotations

import time
from datetime import date, datetime, timedelta

import pandas as pd
import yfinance as yf

import config
import storage


class DataFetchError(Exception):
    """Raised when we can't get usable data for a ticker."""


def _download_with_retry(ticker: str, start: date | None = None,
                         period: str | None = None) -> pd.DataFrame:
    """Call yfinance with retries + timeout. One place for all network flakiness."""
    last_err: Exception | None = None
    for attempt in range(1, config.FETCH_RETRIES + 1):
        try:
            # auto_adjust=False so prices match what users see on
            # Yahoo Finance / Robinhood / brokerages. Dividends are small
            # relative to drawdown signals, so this is the right tradeoff.
            if start:
                df = yf.download(
                    ticker, start=start.isoformat(),
                    progress=False, auto_adjust=False,
                    timeout=config.FETCH_TIMEOUT_SEC,
                )
            else:
                df = yf.download(
                    ticker, period=period or "1y",
                    progress=False, auto_adjust=False,
                    timeout=config.FETCH_TIMEOUT_SEC,
                )
            if df is None or df.empty:
                raise DataFetchError(f"{ticker}: empty response")
            # yfinance sometimes returns multi-index columns; flatten.
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            return df
        except Exception as e:
            last_err = e
            if attempt < config.FETCH_RETRIES:
                time.sleep(2 ** attempt)  # 2s, 4s backoff
    raise DataFetchError(f"{ticker}: failed after {config.FETCH_RETRIES} tries: {last_err}")


def _period_for_days(days: int) -> str:
    """Map a number of trading days to a yfinance period string."""
    if days <= 260:
        return "1y"
    if days <= 520:
        return "2y"
    if days <= 1300:
        return "5y"
    return "10y"


def _oldest_cached_date(ticker: str):
    """Return the earliest cached date for a ticker, or None."""
    import sqlite3
    with sqlite3.connect(config.DB_PATH) as c:
        row = c.execute(
            "SELECT MIN(date) FROM price_bars WHERE ticker = ?", (ticker,)
        ).fetchone()
    if not row or not row[0]:
        return None
    return datetime.strptime(row[0], "%Y-%m-%d").date()


def fetch_history(ticker: str, days: int = None) -> pd.DataFrame:
    """Return the last `days` of price data, cache-first.

    Flow:
      1. If nothing cached OR cache is very stale -> cold fetch enough history
      2. Else if cache doesn't go back far enough for the request -> expand it
      3. Else if cache is 1 day+ behind today -> fetch the gap and append
      4. Return requested slice from cache
    """
    days = days or config.HISTORY_DAYS
    latest = storage.get_latest_date(ticker)
    oldest = _oldest_cached_date(ticker)
    today = date.today()

    # How much history the caller actually wants, in calendar days
    calendar_days_needed = int(days * 1.5)  # ~1.5x to account for weekends/holidays
    needed_start = today - timedelta(days=calendar_days_needed)

    if latest is None or (today - latest).days > config.CACHE_STALE_DAYS:
        # Cold start or very stale — fetch enough for the request
        period = _period_for_days(days)
        df = _download_with_retry(ticker, period=period)
        storage.save_bars(ticker, df)
    elif oldest is not None and oldest > needed_start:
        # Cache exists but doesn't reach far enough back — re-fetch full period
        period = _period_for_days(days)
        df = _download_with_retry(ticker, period=period)
        storage.save_bars(ticker, df)
    elif latest < today - timedelta(days=1):
        # Warm cache, just fill the gap
        gap_start = latest + timedelta(days=1)
        df = _download_with_retry(ticker, start=gap_start)
        storage.save_bars(ticker, df)
    # else: cache is current and deep enough, no fetch needed

    history = storage.get_history(ticker, days)
    if history.empty or len(history) < 50:
        raise DataFetchError(f"{ticker}: not enough data in cache ({len(history)} rows)")
    return history
