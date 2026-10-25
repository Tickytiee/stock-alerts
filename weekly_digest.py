"""Weekly DCA digest — ranks firing signals, posts top 3 to Discord.

Replaces the daily alert spam. Runs once a week (Sunday evening Bangkok time).
Reuses data.py + signals.py from Phase 1 — no new dependencies.

Scoring (max ~10):
  RSI oversold strong (<25):     +4
  RSI oversold normal (25-30):   +2
  Drawdown strong (>=20%):       +3
  Drawdown normal (15-20%):      +2
  Confluence bonus (both fire):  +2
  Tier 1 bonus (you own it):     +1

Posts nothing if nothing scored >=2. Silence = no good opportunities this week.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import config
import data
import notify
import signals as sig


TOP_N = 3            # how many picks to show
MIN_SCORE = 2        # ignore anything scoring below this


@dataclass
class Candidate:
    ticker: str
    tier: int           # 1 or 2
    price: float
    score: int
    signals: list       # list of Signal objects
    reasoning: str      # one-line explanation


def _score(signals: list, tier: int) -> tuple[int, str]:
    """Compute score + reasoning line for a ticker's firing signals."""
    score = 0
    parts = []

    for s in signals:
        if s.key == "rsi_oversold":
            if s.severity == "strong":
                score += 4
                parts.append("RSI oversold strong")
            else:
                score += 2
                parts.append("RSI oversold")
        elif s.key == "drawdown":
            if s.severity == "strong":
                score += 3
                parts.append("Drawdown strong")
            else:
                score += 2
                parts.append("Drawdown")

    # Confluence: both signal types fired
    keys = {s.key for s in signals}
    if "rsi_oversold" in keys and "drawdown" in keys:
        score += 2
        parts.append("Confluence")

    # Tier 1 bonus
    if tier == 1:
        score += 1
        parts.append("Tier 1 holding")

    reasoning = " + ".join(parts) if parts else "no signals"
    return score, reasoning


def _analyze_ticker(ticker: str, tier: int) -> Candidate | None:
    """Fetch, detect signals, score. Returns None if no signals or below threshold."""
    try:
        history = data.fetch_history(ticker)
    except data.DataFetchError:
        return None

    firing = sig.detect_signals(history)
    if not firing:
        return None

    score, reasoning = _score(firing, tier)
    if score < MIN_SCORE:
        return None

    return Candidate(
        ticker=ticker,
        tier=tier,
        price=float(history["Close"].iloc[-1]),
        score=score,
        signals=firing,
        reasoning=reasoning,
    )


def _rank_all() -> list[Candidate]:
    """Score every ticker, return ranked list (highest score first)."""
    candidates: list[Candidate] = []
    errors: list[str] = []

    for ticker in config.TIER_1_HOLDINGS:
        try:
            c = _analyze_ticker(ticker, tier=1)
            if c:
                candidates.append(c)
        except Exception as e:
            errors.append(f"{ticker}: {e}")

    for ticker in config.TIER_2_WATCHLIST:
        try:
            c = _analyze_ticker(ticker, tier=2)
            if c:
                candidates.append(c)
        except Exception as e:
            errors.append(f"{ticker}: {e}")

    # Sort by score desc, then by ticker for stable output
    candidates.sort(key=lambda c: (-c.score, c.ticker))

    if errors:
        err_msg = "⚠️ **Digest fetch errors**\n" + "\n".join(f"• {e}" for e in errors)
        notify.send("errors", err_msg)

    return candidates


def _format_digest(candidates: list[Candidate], today: date) -> str:
    """Build the Discord message. candidates is already ranked."""
    if not candidates:
        return (
            f"📊 **Weekly DCA Digest — {today.isoformat()}**\n\n"
            f"No candidates this week. Nothing in your universe hit the score threshold.\n"
            f"Silence = no good opportunities. Hold cash for next week, or consider "
            f"adding to any existing Tier 1 position if the 25th is close."
        )

    medals = ["🥇", "🥈", "🥉"]
    lines = [f"📊 **Weekly DCA Digest — {today.isoformat()}**", ""]
    lines.append(f"Top {min(TOP_N, len(candidates))} ranked by signal strength:")
    lines.append("")

    for i, c in enumerate(candidates[:TOP_N]):
        medal = medals[i] if i < len(medals) else "•"
        tier_label = "Tier 1" if c.tier == 1 else "Tier 2"
        lines.append(
            f"{medal} **{c.ticker}** — ${c.price:.2f}  (Score {c.score}/10, {tier_label})"
        )
        lines.append(f"    {c.reasoning}")
        lines.append("")

    # Mention the rest if there are more
    rest = candidates[TOP_N:]
    if rest:
        rest_names = ", ".join(f"{c.ticker} ({c.score})" for c in rest[:5])
        more = "" if len(rest) <= 5 else f" (+{len(rest) - 5} more)"
        lines.append(f"_Also firing but lower rank:_ {rest_names}{more}")

    lines.append("")
    lines.append("_Pick one. Research the catalyst. Then DCA._")
    return "\n".join(lines)


def main() -> None:
    today = date.today()
    print(f"=== Weekly digest {today.isoformat()} ===")

    candidates = _rank_all()
    print(f"Found {len(candidates)} candidates above score {MIN_SCORE}")
    for c in candidates[:TOP_N]:
        print(f"  {c.ticker}: score {c.score} ({c.reasoning})")

    message = _format_digest(candidates, today)
    notify.send("alerts", message)
    print("=== Done ===")


if __name__ == "__main__":
    main()
