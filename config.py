"""Configuration — all the knobs in one place."""

import os

# ---------------------------------------------------------------------------
# Tickers — edit these as your portfolio evolves
# ---------------------------------------------------------------------------

# Tier 1: stocks you actually own. Any signal fires an alert.
TIER_1_HOLDINGS = [
    "NVDA",
    "MSFT",
    "GOOGL",
    "AMZN",
    "META",
    "TSLA",
    "AAPL",
    "AMD",
]

# Tier 2: watchlist — interested but don't own yet. Only STRONG signals alert.
TIER_2_WATCHLIST = [
    # AI / Semis
    "TSM", "ASML", "AVGO", "AMAT", "LRCX", "MU",
    # Hyperscale / cloud / enterprise
    "ORCL", "CRM", "NOW", "SNOW",
    # AI software / platforms / security
    "PLTR", "DDOG", "NET", "CRWD",
    # Other tech standouts
    "ARM", "SHOP",
]

# ---------------------------------------------------------------------------
# Signal thresholds (Phase 1 = fixed; Phase 3 will replace with percentile)
# ---------------------------------------------------------------------------

RSI_OVERSOLD = 30
RSI_OVERSOLD_STRONG = 25

DRAWDOWN_PCT = 15          # normal trigger
DRAWDOWN_PCT_STRONG = 20   # strong trigger

# ---------------------------------------------------------------------------
# DCA reminder settings
# ---------------------------------------------------------------------------

DCA_AMOUNT_THB = 5000
DCA_START_DAY = 1    # reminder: base allocation + opportunistic reserve
DCA_DEADLINE_DAY = 25  # reminder: deploy remaining, don't carry cash

# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

HEALTH_CHECK_WEEKDAY = 0  # Monday (0=Mon, 6=Sun) — weekly "I'm alive" ping

# ---------------------------------------------------------------------------
# Discord webhooks — loaded from environment, never hardcoded
# ---------------------------------------------------------------------------

DISCORD_ALERTS_URL = os.environ.get("DISCORD_ALERTS_URL", "")
DISCORD_CANDIDATES_URL = os.environ.get("DISCORD_CANDIDATES_URL", "")
DISCORD_ERRORS_URL = os.environ.get("DISCORD_ERRORS_URL", "")

# ---------------------------------------------------------------------------
# Data / cache
# ---------------------------------------------------------------------------

DB_PATH = "prices.db"
FETCH_RETRIES = 3
FETCH_TIMEOUT_SEC = 15
CACHE_STALE_DAYS = 7  # if cache older than this, fetch full year fresh
HISTORY_DAYS = 260    # ~1 year of trading days
