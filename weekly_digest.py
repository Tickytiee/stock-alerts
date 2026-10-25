"""Weekly DCA digest — ranks firing signals, posts top 3 to Discord.

Replaces the daily alert spam. Runs once a week (Sunday evening Bangkok time).
Reuses data.py + signals.py from Phase 1 — no new dependencies.

Scoring v2 (flipped — moderate signals favored, extremes penalized):
  Drawdown normal (15-20%):      +3   # healthy pullback
  Drawdown strong (>=20%):       -1   # falling knife, likely broken
  RSI oversold normal (25-30):   +2   # healthy pullback
  RSI oversold strong (<25):     -2   # something wrong
  Healthy confluence (both normal):  +2
  Tier 1 bonus (you own it):     +2

Rationale: backtest of v1 showed "biggest signals" strategy loses to SPY by
-5.6% at 90d — top-scored picks were catching falling knives, not opportunities.
V2 prefers mild pullbacks on healthy names (statistically better DCA zones).

Posts nothing if nothing scored >=MIN_SCORE. Silence = no good opportunities.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import config
import data
import notify
import signals as sig


TOP_N = 3            # how many picks to show
MIN_SCORE = 3        # tighter than v1 — only truly healthy setups


@dataclass
class Candidate:
    ticker: str
    tier: int
    price: float
    score: int
    signals: list
    reasoning: str


def _score(signals: list, tier: int) -> tuple[int, str]:
    """
    Compute v2 score + reasoning line.
    See module docstring for rationale behind the weights.
    """
    score = 0
    parts = []

    rsi_sigs = [s for s in signals if s.key == "rsi_oversold"]
    dd_sigs = [s for s in signals if s.key == "drawdown"]

    for s in dd_sigs:
        if s.severity == "strong":
            score -= 1
            parts.append("Deep drawdown (-1, likely broken)")
        else:
            score += 3
            parts.append("Moderate drawdown (+3, healthy pullback)")

    for s in rsi_sigs:
        if s.severity == "strong":
            score -= 2
            parts.append("Extreme RSI (-2, caution)")
        else:
            score += 2
            parts.append("Moderate RSI oversold (+2)")

    # Confluence bonus ONLY if both signals fire AND both are normal severity
    # (both extreme = double-trouble, not double-opportunity)
    if rsi_sigs and dd_sigs:
        all_normal = all(s.severity == "normal" for s in signals)
        if all_normal:
            score += 2
            parts.append("Healthy confluence (+2)")

    if tier == 1:
        score += 2
        parts.append("Tier 1 holding (+2)")

    reasoning = " + ".join(parts) if parts else "no signals"
    return score, reasoning


def _analyze_ticker(ticker: str, tier: int) -> Candidate | None:
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

    candidates.sort(key=lambda c: (-c.score, c.ticker))

    if errors:
        err_msg = "⚠️ **Digest fetch errors**\n" + "\n".join(f"• {e}" for e in errors)
        notify.send("errors", err_msg)

    return candidates


def _format_digest(candidates: list[Candidate], today: date) -> str:
    if not candidates:
        return (
            f"📊 **Weekly DCA Digest — {today.isoformat()}**\n\n"
            f"No candidates this week. Nothing hit the quality threshold.\n"
            f"Silence = no clean DCA opportunity. Hold cash or add to IVV as default."
        )

    medals = ["🥇", "🥈", "🥉"]
    lines = [f"📊 **Weekly DCA Digest — {today.isoformat()}**", ""]
    lines.append(f"Top {min(TOP_N, len(candidates))} healthy pullbacks ranked:")
    lines.append("")

    for i, c in enumerate(candidates[:TOP_N]):
        medal = medals[i] if i < len(medals) else "•"
        tier_label = "Tier 1" if c.tier == 1 else "Tier 2"
        lines.append(
            f"{medal} **{c.ticker}** — ${c.price:.2f}  (Score {c.score}, {tier_label})"
        )
        lines.append(f"    {c.reasoning}")
        lines.append("")

    rest = candidates[TOP_N:]
    if rest:
        rest_names = ", ".join(f"{c.ticker} ({c.score})" for c in rest[:5])
        more = "" if len(rest) <= 5 else f" (+{len(rest) - 5} more)"
        lines.append(f"_Also qualified:_ {rest_names}{more}")

    lines.append("")
    lines.append("_Scoring v2: prefers moderate pullbacks on healthy names, avoids falling knives._")
    return "\n".join(lines)


def main() -> None:
    today = date.today()
    print(f"=== Weekly digest {today.isoformat()} (scoring v2) ===")

    candidates = _rank_all()
    print(f"Found {len(candidates)} candidates above score {MIN_SCORE}")
    for c in candidates[:TOP_N]:
        print(f"  {c.ticker}: score {c.score} ({c.reasoning})")

    message = _format_digest(candidates, today)
    notify.send("alerts", message)
    print("=== Done ===")


if __name__ == "__main__":
    main()
