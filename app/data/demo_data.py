"""
Generateur de donnees simulees pour le mode DEMO.
Permet de lancer et tester tout le dashboard (interface, strategies, journal)
sans avoir encore configure de compte OANDA ni de cle FRED.

Le prix simule suit une marche aleatoire avec une legere derive et des
"regimes" de tendance qui alternent, pour que les strategies aient vraiment
quelque chose a analyser (et pas juste du bruit pur).
"""
import numpy as np
import pandas as pd

_RNG = np.random.default_rng(seed=42)


def _random_walk_ohlc(base_price: float, count: int, vol: float, freq_minutes: int) -> pd.DataFrame:
    n_regimes = 4
    regime_len = max(count // n_regimes, 1)
    drift_per_regime = _RNG.uniform(-0.00015, 0.00015, size=n_regimes)

    closes = [base_price]
    for i in range(1, count):
        regime = min(i // regime_len, n_regimes - 1)
        shock = _RNG.normal(loc=drift_per_regime[regime], scale=vol)
        closes.append(closes[-1] * (1 + shock))

    now = pd.Timestamp.utcnow().floor("min")
    times = [now - pd.Timedelta(minutes=freq_minutes * (count - i)) for i in range(count)]

    rows = []
    for i, c in enumerate(closes):
        o = closes[i - 1] if i > 0 else c
        high = max(o, c) * (1 + abs(_RNG.normal(0, vol / 2)))
        low = min(o, c) * (1 - abs(_RNG.normal(0, vol / 2)))
        rows.append(
            {
                "time": times[i],
                "open": round(o, 3),
                "high": round(high, 3),
                "low": round(low, 3),
                "close": round(c, 3),
                "volume": int(_RNG.integers(50, 500)),
                "complete": True,
            }
        )
    return pd.DataFrame(rows)


GRANULARITY_MINUTES = {
    "M1": 1, "M5": 5, "M15": 15, "M30": 30,
    "H1": 60, "H4": 240, "D": 1440,
}

# Prix de base par instrument (ordre de grandeur realiste pour se reperer en mode demo)
BASE_PRICES = {
    "XAU_USD": 3650.0,
    "EUR_USD": 1.09,
    "USD_JPY": 152.0,
    "GBP_USD": 1.27,
    "USD_CAD": 1.36,
    "USD_CHF": 0.885,
}


def demo_candles(instrument: str, granularity: str = "M15", count: int = 300) -> pd.DataFrame:
    base = BASE_PRICES.get(instrument, 100.0)
    freq = GRANULARITY_MINUTES.get(granularity, 15)
    vol = 0.0009 if instrument == "XAU_USD" else 0.0004
    return _random_walk_ohlc(base, count, vol, freq)


def demo_price(instrument: str) -> dict:
    df = demo_candles(instrument, "M1", 2)
    last = df.iloc[-1]
    spread = last["close"] * 0.0002
    return {
        "instrument": instrument,
        "bid": round(last["close"] - spread / 2, 3),
        "ask": round(last["close"] + spread / 2, 3),
        "mid": round(last["close"], 3),
        "time": str(last["time"]),
    }
