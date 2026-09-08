"""
Lecture de la structure de marche (methode "Smart Money Concepts" simplifiee) :
- swing highs / swing lows (fractales)
- tendance de structure (HH/HL haussier, LH/LL baissier)
- balayages de liquidite (liquidity sweeps / stop hunts)
- zones d'order block (dernier chandelier oppose avant un mouvement impulsif)

Ce module ne dessine rien : il transforme des bougies en une lecture
structurelle exploitable par le moteur de strategie, pour eviter d'avoir
a tracer soi-meme les niveaux a la main.
"""
from dataclasses import dataclass
from typing import List, Literal, Optional

import pandas as pd

Direction = Literal["bullish", "bearish"]


@dataclass
class SwingPoint:
    index: int
    time: pd.Timestamp
    price: float
    kind: Literal["high", "low"]


@dataclass
class LiquiditySweep:
    index: int
    time: pd.Timestamp
    swept_level: float
    close_back_price: float
    direction: Direction  # "bullish" = balayage des plus bas -> setup acheteur


@dataclass
class OrderBlock:
    start_index: int
    end_index: int
    zone_low: float
    zone_high: float
    direction: Direction


def find_swing_points(df: pd.DataFrame, window: int = 2) -> List[SwingPoint]:
    """Fractale simple : un pivot est confirme s'il est le plus haut/bas parmi
    `window` bougies avant ET apres lui."""
    swings: List[SwingPoint] = []
    highs, lows = df["high"].values, df["low"].values
    n = len(df)
    for i in range(window, n - window):
        window_highs = highs[i - window : i + window + 1]
        window_lows = lows[i - window : i + window + 1]
        if highs[i] == window_highs.max() and (window_highs == window_highs.max()).sum() == 1:
            swings.append(SwingPoint(i, df["time"].iloc[i], highs[i], "high"))
        if lows[i] == window_lows.min() and (window_lows == window_lows.min()).sum() == 1:
            swings.append(SwingPoint(i, df["time"].iloc[i], lows[i], "low"))
    return sorted(swings, key=lambda s: s.index)


def classify_trend(swings: List[SwingPoint]) -> str:
    """Regarde les 2 derniers swing highs et les 2 derniers swing lows pour
    determiner si la structure est haussiere, baissiere, ou indecise."""
    highs = [s for s in swings if s.kind == "high"][-2:]
    lows = [s for s in swings if s.kind == "low"][-2:]
    if len(highs) < 2 or len(lows) < 2:
        return "undefined"

    higher_highs = highs[-1].price > highs[-2].price
    higher_lows = lows[-1].price > lows[-2].price
    lower_highs = highs[-1].price < highs[-2].price
    lower_lows = lows[-1].price < lows[-2].price

    if higher_highs and higher_lows:
        return "bullish"
    if lower_highs and lower_lows:
        return "bearish"
    return "ranging"


def detect_liquidity_sweep(df: pd.DataFrame, swings: List[SwingPoint], lookback_bars: int = 40) -> Optional[LiquiditySweep]:
    """Cherche, dans les `lookback_bars` dernieres bougies, un chandelier qui
    "chasse" un swing high/low recent (meche au-dela) puis cloture de retour
    a l'interieur -- signature classique d'un piege a liquidite institutionnel."""
    recent = df.iloc[-lookback_bars:]
    recent_swings = [s for s in swings if s.index >= len(df) - lookback_bars]
    swing_highs = [s for s in recent_swings if s.kind == "high"]
    swing_lows = [s for s in recent_swings if s.kind == "low"]

    best: Optional[LiquiditySweep] = None
    for i in range(len(recent) - 1, max(len(recent) - 15, 0), -1):
        row = recent.iloc[i]
        idx = df.index.get_loc(recent.index[i]) if not isinstance(df.index, pd.RangeIndex) else recent.index[i]

        for sh in swing_highs:
            if sh.index < idx and row["high"] > sh.price and row["close"] < sh.price:
                candidate = LiquiditySweep(idx, row["time"], sh.price, row["close"], "bearish")
                best = best or candidate
        for sl in swing_lows:
            if sl.index < idx and row["low"] < sl.price and row["close"] > sl.price:
                candidate = LiquiditySweep(idx, row["time"], sl.price, row["close"], "bullish")
                best = best or candidate
        if best:
            break
    return best


def find_order_block(df: pd.DataFrame, sweep: LiquiditySweep, impulse_lookahead: int = 6) -> Optional[OrderBlock]:
    """A partir d'un balayage de liquidite, cherche le dernier chandelier
    "oppose" juste avant le mouvement impulsif qui suit -- c'est la zone
    d'order block ou le prix a de bonnes chances de revenir se retourner."""
    start = sweep.index
    end = min(start + impulse_lookahead, len(df) - 1)
    if end <= start:
        return None

    segment = df.iloc[start : end + 1]

    if sweep.direction == "bullish":
        # on cherche la derniere bougie baissiere (close < open) avant l'impulsion haussiere
        bearish_candles = segment[segment["close"] < segment["open"]]
        if bearish_candles.empty:
            return None
        ob_candle = bearish_candles.iloc[0]
        zone_low, zone_high = ob_candle["low"], ob_candle["open"]
        direction = "bullish"
    else:
        bullish_candles = segment[segment["close"] > segment["open"]]
        if bullish_candles.empty:
            return None
        ob_candle = bullish_candles.iloc[0]
        zone_low, zone_high = ob_candle["open"], ob_candle["high"]
        direction = "bearish"

    ob_index = df.index.get_loc(ob_candle.name) if not isinstance(df.index, pd.RangeIndex) else ob_candle.name
    return OrderBlock(ob_index, ob_index, float(zone_low), float(zone_high), direction)
