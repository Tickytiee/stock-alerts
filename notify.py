"""Discord notification layer — routes to the right channel."""

import requests

import config


_CHANNEL_URLS = {
    "alerts":     lambda: config.DISCORD_ALERTS_URL,
    "candidates": lambda: config.DISCORD_CANDIDATES_URL,
    "errors":     lambda: config.DISCORD_ERRORS_URL,
}


def send(channel: str, message: str) -> None:
    """Send a message to the named channel. Fails loudly via print, never crashes."""
    if channel not in _CHANNEL_URLS:
        print(f"[notify] unknown channel: {channel}")
        return

    url = _CHANNEL_URLS[channel]()
    if not url:
        print(f"[notify] no webhook configured for '{channel}' — printing instead:")
        print(message)
        return

    try:
        resp = requests.post(url, json={"content": message}, timeout=10)
        if resp.status_code >= 300:
            print(f"[notify] '{channel}' returned {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        # Don't raise — a failed notification must not crash the bot
        print(f"[notify] '{channel}' send failed: {e}")


def format_ticker_alert(ticker: str, price: float, signals: list) -> str:
    """Format one ticker's signals into a Discord message block."""
    lines = [f"**{ticker}** — ${price:.2f}"]
    for s in signals:
        tag = "⭐" if s.severity == "strong" else "•"
        lines.append(f"  {tag} {s.message}")
    return "\n".join(lines)
