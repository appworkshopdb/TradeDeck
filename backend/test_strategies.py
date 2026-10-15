"""Schneller Check der Strategie-Logik: python test_strategies.py"""
from strategies import backtest, sma, sma_cross


def make(closes):
    return [
        {"time": 1000 + i * 60, "open": c, "high": c, "low": c, "close": c}
        for i, c in enumerate(closes)
    ]


def test_sma():
    assert sma([1, 2, 3, 4], 2) == [None, 1.5, 2.5, 3.5]


def test_cross_and_backtest():
    # fällt, steigt (Buy-Cross), fällt wieder (Sell-Cross)
    closes = [10, 9, 8, 7, 6, 7, 9, 12, 15, 18, 15, 11, 7, 4]
    candles = make(closes)
    signals, _, _ = sma_cross(candles, fast=2, slow=4)
    sides = [s["side"] for s in signals]
    assert sides == ["buy", "sell"], sides
    assert signals[0]["time"] < signals[1]["time"]

    stats = backtest(candles, signals, fee=0.0)
    buy, sell = signals[0]["price"], signals[1]["price"]
    assert stats["trades"] == 1
    assert abs(stats["return_pct"] - round(100 * (sell / buy - 1), 2)) < 0.01
    assert stats["open_position"] is False


def test_open_position_not_counted():
    candles = make([10, 9, 8, 7, 6, 7, 9, 12, 15, 18])
    signals, _, _ = sma_cross(candles, fast=2, slow=4)
    stats = backtest(candles, signals)
    assert stats["trades"] == 0 and stats["open_position"] is True


if __name__ == "__main__":
    test_sma()
    test_cross_and_backtest()
    test_open_position_not_counted()
    print("OK")
