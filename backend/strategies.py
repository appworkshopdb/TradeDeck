"""Strategien und Backtest.

Eine Strategie bekommt die Kerzen (Liste von Dicts mit time/open/high/low/close)
und liefert Signale: [{"time": <unix>, "side": "buy"|"sell", "price": <float>}].
Neue Strategien einfach als weitere Funktion hinzufügen und in main.py einhängen.
"""
from __future__ import annotations


def sma(values: list[float], n: int) -> list[float | None]:
    """Einfacher gleitender Durchschnitt; None, bis n Werte vorliegen."""
    out: list[float | None] = [None] * len(values)
    running = 0.0
    for i, v in enumerate(values):
        running += v
        if i >= n:
            running -= values[i - n]
        if i >= n - 1:
            out[i] = running / n
    return out


def sma_cross(candles: list[dict], fast: int = 20, slow: int = 50):
    """Golden/Death-Cross: Kauf, wenn der schnelle SMA den langsamen von unten
    kreuzt, Verkauf bei Kreuzung von oben. Signal wird auf dem Schlusskurs
    der Kerze ausgelöst, in der die Kreuzung bestätigt ist.

    Gibt (signale, sma_fast, sma_slow) zurück.
    """
    closes = [c["close"] for c in candles]
    f = sma(closes, fast)
    s = sma(closes, slow)
    signals: list[dict] = []
    for i in range(1, len(candles)):
        if None in (f[i], s[i], f[i - 1], s[i - 1]):
            continue
        if f[i - 1] <= s[i - 1] and f[i] > s[i]:
            signals.append({"time": candles[i]["time"], "side": "buy", "price": closes[i]})
        elif f[i - 1] >= s[i - 1] and f[i] < s[i]:
            signals.append({"time": candles[i]["time"], "side": "sell", "price": closes[i]})
    return signals, f, s


def backtest(candles: list[dict], signals: list[dict], fee: float = 0.001) -> dict:
    """Long-only-Backtest: kaufen beim Buy-Signal, verkaufen beim Sell-Signal.

    - Gebühr `fee` fällt je Kauf und je Verkauf an (0.001 = 0,1 %).
    - Keine Slippage, Einstieg/Ausstieg zum Schlusskurs der Signalkerze.
    - Eine am Ende noch offene Position zählt nicht als Trade; die
      Kennzahlen beziehen sich nur auf abgeschlossene Trades.
    """
    equity = 1.0
    peak = 1.0
    max_drawdown = 0.0
    entry: float | None = None
    returns: list[float] = []

    for sig in signals:
        if sig["side"] == "buy" and entry is None:
            entry = sig["price"]
        elif sig["side"] == "sell" and entry is not None:
            ret = (sig["price"] / entry) * (1 - fee) ** 2 - 1
            returns.append(ret)
            equity *= 1 + ret
            peak = max(peak, equity)
            max_drawdown = max(max_drawdown, (peak - equity) / peak)
            entry = None

    wins = sum(1 for r in returns if r > 0)
    buy_hold = (candles[-1]["close"] / candles[0]["close"] - 1) if len(candles) > 1 else 0.0
    return {
        "trades": len(returns),
        "win_rate_pct": round(100 * wins / len(returns), 1) if returns else None,
        "return_pct": round(100 * (equity - 1), 2),
        "buy_hold_pct": round(100 * buy_hold, 2),
        "max_drawdown_pct": round(100 * max_drawdown, 2),
        "open_position": entry is not None,
    }
