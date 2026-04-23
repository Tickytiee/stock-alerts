"""Data layer — cache-first access to price history.

The only module that touches yfinance. If we swap data sources later, this is
the only file that changes.
"""

from __future__ import annotations

import time
from datetime import date, timedelta

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
            if start:
                df = yf.download(
                    ticker, start=start.isoformat(),
                    progress=False, auto_adjust=True,
                    timeout=config.FETCH_TIMEOUT_SEC,
                )
            else:
                df = yf.download(
                    ticker, period=period or "1y",
                    progress=False, auto_adjust=True,
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


def fetch_history(ticker: str, days: int = None) -> pd.DataFrame:
    """Return the last `days` of price data, cache-first.

    Flow:
      1. If nothing cached OR cache is very stale -> cold fetch full history
      2. Else if cache is 1 day+ behind -> fetch only the gap and append
      3. Return requested slice from cache
    """
    days = days or config.HISTORY_DAYS
    latest = storage.get_latest_date(ticker)
    today = date.today()

    if latest is None or (today - latest).days > config.CACHE_STALE_DAYS:
        # Cold start or very stale — fetch full year
        df = _download_with_retry(ticker, period="1y")
        storage.save_bars(ticker, df)
    elif latest < today - timedelta(days=1):
        # Warm cache, just fill the gap. We fetch from day after `latest`.
        gap_start = latest + timedelta(days=1)
        df = _download_with_retry(ticker, start=gap_start)
        storage.save_bars(ticker, df)
    # else: cache is current, no fetch needed

    history = storage.get_history(ticker, days)
    if history.empty or len(history) < 50:
        raise DataFetchError(f"{ticker}: not enough data in cache ({len(history)} rows)")
    return history
