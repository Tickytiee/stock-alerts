"""SQLite cache — the only module that touches prices.db."""

import sqlite3
from contextlib import contextmanager
from datetime import date, datetime

import pandas as pd

import config


SCHEMA = """
CREATE TABLE IF NOT EXISTS price_bars (
    ticker  TEXT NOT NULL,
    date    TEXT NOT NULL,
    open    REAL,
    high    REAL,
    low     REAL,
    close   REAL,
    volume  INTEGER,
    PRIMARY KEY (ticker, date)
);
CREATE INDEX IF NOT EXISTS idx_ticker_date ON price_bars(ticker, date);
"""


@contextmanager
def _conn():
    c = sqlite3.connect(config.DB_PATH)
    try:
        c.executescript(SCHEMA)
        yield c
        c.commit()
    finally:
        c.close()


def get_latest_date(ticker: str) -> date | None:
    """Return the most recent cached date for a ticker, or None if none."""
    with _conn() as c:
        row = c.execute(
            "SELECT MAX(date) FROM price_bars WHERE ticker = ?", (ticker,)
        ).fetchone()
    if not row or not row[0]:
        return None
    return datetime.strptime(row[0], "%Y-%m-%d").date()


def get_history(ticker: str, days: int) -> pd.DataFrame:
    """Return the last `days` rows of cached price data as a DataFrame."""
    with _conn() as c:
        df = pd.read_sql_query(
            """
            SELECT date, open, high, low, close, volume
            FROM price_bars
            WHERE ticker = ?
            ORDER BY date DESC
            LIMIT ?
            """,
            c,
            params=(ticker, days),
        )
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    df.columns = [col.capitalize() for col in df.columns]  # Open, High, ...
    return df


def save_bars(ticker: str, df: pd.DataFrame) -> int:
    """Upsert bars for a ticker. Returns number of rows written."""
    if df.empty:
        return 0

    rows = []
    for idx, row in df.iterrows():
        d = idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx)[:10]
        rows.append((
            ticker, d,
            float(row.get("Open", row.get("open", 0))),
            float(row.get("High", row.get("high", 0))),
            float(row.get("Low",  row.get("low",  0))),
            float(row.get("Close", row.get("close", 0))),
            int(row.get("Volume", row.get("volume", 0))),
        ))

    with _conn() as c:
        c.executemany(
            """
            INSERT INTO price_bars (ticker, date, open, high, low, close, volume)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(ticker, date) DO UPDATE SET
                open=excluded.open, high=excluded.high, low=excluded.low,
                close=excluded.close, volume=excluded.volume
            """,
            rows,
        )
    return len(rows)


def tickers_in_cache() -> list[str]:
    with _conn() as c:
        rows = c.execute("SELECT DISTINCT ticker FROM price_bars").fetchall()
    return sorted(r[0] for r in rows)
