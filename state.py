"""Per-day dedupe state — so we don't re-alert the same signal twice in one day."""

import json
from datetime import datetime, timedelta
from pathlib import Path

STATE_FILE = Path("alert_state.json")


def load() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except json.JSONDecodeError:
            return {}
    return {}


def save(state: dict) -> None:
    # Prune entries older than 7 days so the file stays small
    cutoff = (datetime.utcnow() - timedelta(days=7)).strftime("%Y-%m-%d")
    pruned = {k: v for k, v in state.items() if k.split(":", 1)[-1] >= cutoff}
    STATE_FILE.write_text(json.dumps(pruned, indent=2))


def already_sent(state: dict, ticker: str, signal_key: str, day: str) -> bool:
    key = f"{ticker}:{day}"
    return signal_key in set(state.get(key, []))


def mark_sent(state: dict, ticker: str, signal_key: str, day: str) -> None:
    key = f"{ticker}:{day}"
    state.setdefault(key, [])
    if signal_key not in state[key]:
        state[key].append(signal_key)
