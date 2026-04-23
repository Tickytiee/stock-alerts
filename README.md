# Stock Alerts Bot — Phase 1

A self-hosted stock monitor that sends Discord alerts when technical signals fire. Free to run on GitHub Actions. Built with discipline — small, testable, extendable.

## What it does

Every weekday after US market close:
1. Fetches price data for your watchlist (cache-first — only downloads what's new)
2. Checks each ticker for **RSI oversold** and **significant drawdown**
3. Routes alerts to Discord channels based on tier
4. Reminds you about DCA on the 1st and 25th of each month
5. Pings a weekly health check so you know it's alive

## Architecture

```
config.py       — all settings in one place
storage.py      — SQLite cache (prices.db)
data.py         — yfinance wrapper, cache-first
signals.py      — pure indicator functions
notify.py       — Discord routing
state.py        — dedupe state
main.py         — daily orchestrator
backtest.py     — validate signals (run manually)
test_signals.py — unit tests
```

## Setup (~20 minutes total)

### 1. Make a Discord server with 3 channels

- `#stock-alerts` — daily signal alerts + DCA reminders
- `#stock-candidates` — future discovery screener (Phase 6, not used yet)
- `#bot-ops` — errors and weekly health pings

For each channel: **Channel settings → Integrations → Webhooks → New Webhook → copy URL**

### 2. Try it locally first

```bash
cd stock_alerts
pip install -r requirements.txt

# Set webhooks
export DISCORD_ALERTS_URL="https://discord.com/api/webhooks/..."
export DISCORD_CANDIDATES_URL="https://discord.com/api/webhooks/..."
export DISCORD_ERRORS_URL="https://discord.com/api/webhooks/..."

# Run tests
python test_signals.py

# Run the bot (will fetch ~24 tickers, takes 1-2 min the first time)
python main.py
```

You should see per-ticker summaries in terminal (price, RSI, drawdown), any alerts posted to Discord, and `prices.db` + `alert_state.json` created.

### 3. Push to GitHub and set up Actions

1. Push to a private repo
2. Settings → Secrets and variables → Actions → New repository secret
   - `DISCORD_ALERTS_URL`
   - `DISCORD_CANDIDATES_URL`
   - `DISCORD_ERRORS_URL`
3. Actions tab → enable workflows if prompted
4. Runs automatically at 21:30 UTC weekdays. Manual run available via "Run workflow" button.

The workflow commits the updated `prices.db` and `alert_state.json` back to your repo so the cache persists between runs.

## Running the backtest

Before trusting signal quality, run the backtest:

```bash
python backtest.py
```

This walks through 3 years of history, fires signals, records forward returns at 30/60/90 days, and compares to buying SPY on the same dates. Takes ~5 minutes.

**Interpretation:**
- Signal beats SPY by +2% or more → keep/tune
- Signal ≈ SPY → neutral, not helpful
- Signal loses to SPY → threshold wrong or signal is noise

Run this quarterly to check if thresholds still make sense.

## How DCA reminders work

You have 5,000 THB/month. The bot reminds you:
- **1st of month:** deploy ~3,000 base, hold ~2,000 for opportunistic dips
- **25th of month:** deploy whatever's left, no cash carried forward

The second rule is critical — cash sitting on the sidelines waiting for "the perfect dip" is the biggest DCA failure mode. The bot enforces the discipline.

## How tiering works

**Tier 1 (holdings) — any signal alerts:**
NVDA, MSFT, GOOGL, AMZN, META, TSLA, AAPL, AMD

**Tier 2 (watchlist) — only strong signals alert:**
TSM, ASML, AVGO, AMAT, LRCX, MU, ORCL, CRM, NOW, SNOW, PLTR, DDOG, NET, CRWD, ARM, SHOP

**What counts as strong:**
- RSI below 25, OR
- Drawdown 20%+ from 52-week high, OR
- Both normal signals firing together (confluence)

## Files to know

| File              | Purpose                                      | Edit? |
|-------------------|----------------------------------------------|-------|
| `config.py`       | tickers, thresholds, DCA rules              | Yes   |
| `signals.py`      | indicator logic                             | Later |
| `main.py`         | orchestrator                                | Rarely|
| `prices.db`       | SQLite cache (auto-managed)                 | No    |
| `alert_state.json`| dedupe state (auto-managed)                 | No    |

## What's next (deferred phases)

- **Phase 2:** already done — Tier 1 + Tier 2 universe
- **Phase 3:** per-ticker percentile thresholds (NVDA's "oversold" is different from MSFT's)
- **Phase 4:** already done — backtest module exists
- **Phase 6:** discovery screener — scans 200+ names weekly for new candidates, posts to `#stock-candidates`

## Things worth knowing

**yfinance is unofficial.** Free, works well, occasionally breaks when Yahoo updates their site. If it stops working, swap `data.py` to Finnhub or Alpha Vantage (both have free tiers). Only one file changes.

**Signals inform decisions, don't make them.** RSI < 30 means "oversold right now," not "buy now." Always check news and fundamentals before acting.

**Don't optimize for more alerts.** The goal is a few high-quality signals per month, not a dashboard full of noise. If you're getting too many alerts, raise the thresholds in `config.py`.

**The real lever for your 15M THB goal is your contribution rate.** This bot improves DCA timing at the margins. Doubling your monthly contribution in a few years will do more than any signal tuning ever will.
