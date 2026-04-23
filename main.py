"""Main orchestrator — the only entry point for the daily run."""

from __future__ import annotations

from datetime import date, datetime

import config
import data
import notify
import signals as sig
import state as st


def _process_tier(tickers: list[str], tier: str, today: str,
                  state: dict) -> tuple[list[str], list[str]]:
    """
    Process one tier of tickers.
    Returns (alerts_to_send, errors_encountered).
    """
    alerts: list[str] = []
    errors: list[str] = []

    for ticker in tickers:
        try:
            history = data.fetch_history(ticker)
        except data.DataFetchError as e:
            errors.append(f"{ticker}: {e}")
            continue

        print(sig.summary_line(ticker, history))

        signals = sig.detect_signals(history)
        if not signals:
            continue

        # Tier 2 only alerts on strong signals
        if tier == "tier2":
            signals = [s for s in signals if s.severity == "strong"]
            if not signals:
                continue

        # Dedupe — drop signals already sent today
        fresh = [s for s in signals
                 if not st.already_sent(state, ticker, s.key, today)]
        if not fresh:
            continue

        price = float(history["Close"].iloc[-1])
        alerts.append(notify.format_ticker_alert(ticker, price, fresh))

        for s in fresh:
            st.mark_sent(state, ticker, s.key, today)

    return alerts, errors


def _dca_reminder(today_date: date) -> str | None:
    """Return a DCA reminder message if today is the 1st or 25th, else None."""
    day = today_date.day

    if day == config.DCA_START_DAY:
        return (
            f"💰 **DCA Day — Month Start**\n"
            f"Deploy base allocation: ~3,000 THB\n"
            f"Reserve ~2,000 THB for opportunistic dips this month\n"
            f"(Remember: the 25th is the deadline — no cash carried over)"
        )

    if day == config.DCA_DEADLINE_DAY:
        return (
            f"⏰ **DCA Deadline — Month End Approaching**\n"
            f"If you haven't deployed the full {config.DCA_AMOUNT_THB:,} THB yet, "
            f"deploy the rest now. Don't carry cash into next month."
        )

    return None


def _health_check(today_date: date) -> str | None:
    """Return a weekly 'alive' message on the configured weekday."""
    if today_date.weekday() != config.HEALTH_CHECK_WEEKDAY:
        return None
    return (
        f"✅ **Weekly health check** — {today_date.isoformat()}\n"
        f"Bot is running. Watchlist: "
        f"{len(config.TIER_1_HOLDINGS)} holdings + "
        f"{len(config.TIER_2_WATCHLIST)} watchlist = "
        f"{len(config.TIER_1_HOLDINGS) + len(config.TIER_2_WATCHLIST)} tickers."
    )


def main() -> None:
    today_date = date.today()
    today = today_date.isoformat()
    state = st.load()

    print(f"=== Stock alerts run {datetime.utcnow().isoformat()} UTC ===")

    # Process each tier
    t1_alerts, t1_errors = _process_tier(
        config.TIER_1_HOLDINGS, "tier1", today, state
    )
    t2_alerts, t2_errors = _process_tier(
        config.TIER_2_WATCHLIST, "tier2", today, state
    )

    # Send alerts
    all_alerts = t1_alerts + t2_alerts
    if all_alerts:
        header = f"📈 **Stock Alerts — {today}**\n\n"
        notify.send("alerts", header + "\n\n".join(all_alerts))
    else:
        print("No new alerts.")

    # Send DCA reminder if applicable
    dca_msg = _dca_reminder(today_date)
    if dca_msg:
        notify.send("alerts", dca_msg)

    # Send weekly health check
    health_msg = _health_check(today_date)
    if health_msg:
        notify.send("errors", health_msg)  # errors channel doubles as "ops"

    # Send consolidated errors
    all_errors = t1_errors + t2_errors
    if all_errors:
        err_msg = (
            f"⚠️ **Data fetch errors — {today}**\n"
            + "\n".join(f"• {e}" for e in all_errors)
        )
        notify.send("errors", err_msg)

    st.save(state)
    print(f"=== Done. Alerts: {len(all_alerts)}, Errors: {len(all_errors)} ===")


if __name__ == "__main__":
    main()
