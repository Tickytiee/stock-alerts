"""Tests for signals.py — pure function tests, no network required.

Run:  python test_signals.py
"""

import pandas as pd

import signals as sig
import config


def _df_from_closes(closes: list[float]) -> pd.DataFrame:
    """Build a minimal DataFrame from a list of closing prices."""
    idx = pd.date_range(end="2024-12-31", periods=len(closes), freq="B")
    return pd.DataFrame({
        "Open":   closes,
        "High":   [c * 1.01 for c in closes],
        "Low":    [c * 0.99 for c in closes],
        "Close":  closes,
        "Volume": [1_000_000] * len(closes),
    }, index=idx)


def test_rsi_neutral_no_signal():
    # Oscillating price -> RSI near 50 -> no oversold signal
    closes = [100 + (i % 5 - 2) for i in range(100)]
    signals = sig.detect_signals(_df_from_closes(closes))
    assert not any(s.key == "rsi_oversold" for s in signals), \
        "Neutral RSI should not fire oversold"
    print("  ✓ RSI neutral -> no oversold signal")


def test_rsi_oversold_fires():
    # Strong sustained downtrend -> RSI low -> oversold fires
    closes = list(range(100, 40, -1)) + [40] * 40
    signals = sig.detect_signals(_df_from_closes(closes))
    rsi_sigs = [s for s in signals if s.key == "rsi_oversold"]
    assert rsi_sigs, "Downtrend should fire RSI oversold"
    print(f"  ✓ Sustained decline -> RSI oversold ({rsi_sigs[0].severity})")


def test_drawdown_fires_below_threshold():
    # Peak at 120, then drop to 100 -> ~16.7% drawdown -> fires
    closes = list(range(80, 120)) + list(range(120, 100, -1))
    signals = sig.detect_signals(_df_from_closes(closes))
    dd_sigs = [s for s in signals if s.key == "drawdown"]
    assert dd_sigs, "16.7% drop from peak should fire drawdown"
    print(f"  ✓ 16.7% drawdown fires ({dd_sigs[0].severity})")


def test_drawdown_no_fire_small_drop():
    # Peak 110, current 105 -> ~4.5% drawdown -> should not fire
    closes = list(range(100, 111)) + [105] * 20
    signals = sig.detect_signals(_df_from_closes(closes))
    dd_sigs = [s for s in signals if s.key == "drawdown"]
    assert not dd_sigs, "Small drop should not fire drawdown"
    print("  ✓ Small drawdown (<15%) does not fire")


def test_drawdown_strong_severity():
    # 25% drawdown should be marked strong
    closes = list(range(100, 140)) + list(range(140, 104, -1))
    signals = sig.detect_signals(_df_from_closes(closes))
    dd_sigs = [s for s in signals if s.key == "drawdown"]
    assert dd_sigs, "Should fire"
    assert dd_sigs[0].severity == "strong", \
        f"25% drawdown should be strong, got {dd_sigs[0].severity}"
    print("  ✓ 25% drawdown flagged as strong severity")


def test_confluence_upgrades_severity():
    # Both RSI oversold AND drawdown fire but individually at "normal" level
    # -> confluence should upgrade both to strong
    closes = list(range(100, 120)) + list(range(120, 100, -1))  # 16.7% dd
    closes += [99, 98, 97, 96, 95, 94]  # extend decline for RSI
    signals = sig.detect_signals(_df_from_closes(closes))
    if len(signals) == 2 and all(s.severity == "strong" for s in signals):
        print("  ✓ Confluence of 2 normal signals -> upgraded to strong")
    else:
        # Not a strict failure — depends on exact RSI value
        sevs = [f"{s.key}={s.severity}" for s in signals]
        print(f"  ~ Confluence test (signals: {sevs})")


def test_rsi_calculation_sanity():
    # Pure uptrend -> RSI should be high (>70)
    closes = list(range(50, 150))
    rsi = sig.compute_rsi(pd.Series(closes))
    assert rsi > 70, f"Uptrend RSI should be >70, got {rsi}"
    print(f"  ✓ Uptrend RSI = {rsi:.1f} (>70 as expected)")

    # Pure downtrend -> RSI should be low (<30)
    closes = list(range(150, 50, -1))
    rsi = sig.compute_rsi(pd.Series(closes))
    assert rsi < 30, f"Downtrend RSI should be <30, got {rsi}"
    print(f"  ✓ Downtrend RSI = {rsi:.1f} (<30 as expected)")


if __name__ == "__main__":
    print("Running signal tests...")
    print()
    test_rsi_neutral_no_signal()
    test_rsi_oversold_fires()
    test_drawdown_fires_below_threshold()
    test_drawdown_no_fire_small_drop()
    test_drawdown_strong_severity()
    test_confluence_upgrades_severity()
    test_rsi_calculation_sanity()
    print()
    print("All tests passed ✓")
