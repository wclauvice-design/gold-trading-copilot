"""
Indice de force du dollar "maison", calcule a partir d'un panier de paires FX
recuperees sur OANDA (le meme compte que pour l'or -- aucune source de donnees
supplementaire a payer). Ce n'est pas le vrai DXY (qui inclut le SEK et est
calcule par ICE), mais une tres bonne approximation de son comportement, et
surtout on peut le calculer en direct avec ce qu'on a deja.

Poids approximatifs inspires des poids officiels du DXY, renormalises sur
5 paires majeures disponibles partout chez les brokers.
"""
from dataclasses import dataclass
from typing import Callable

import numpy as np
import pandas as pd


class DollarIndexError(RuntimeError):
    pass


# (instrument, poids, +1 si USD est la devise de BASE (USD_XXX), -1 si USD est la devise COTEE (XXX_USD))
BASKET = [
    ("EUR_USD", 0.62, -1),
    ("USD_JPY", 0.15, +1),
    ("GBP_USD", 0.13, -1),
    ("USD_CAD", 0.06, +1),
    ("USD_CHF", 0.04, +1),
]


@dataclass
class UsdIndexResult:
    series: pd.Series  # index synthetique, base 100
    trend: str  # "strengthening" | "weakening" | "flat"
    change_pct: float  # variation sur la fenetre analysee


def compute_usd_strength_index(
    get_candles: Callable[[str, str, int], pd.DataFrame],
    granularity: str = "H1",
    count: int = 60,
) -> UsdIndexResult:
    """
    `get_candles` est une fonction (instrument, granularity, count) -> DataFrame OHLC,
    ce qui permet de brancher indifferemment OandaClient.get_candles ou le generateur
    de donnees demo (voir app/data/demo_data.py).
    """
    returns_frames = []
    for instrument, weight, sign in BASKET:
        try:
            df = get_candles(instrument, granularity, count)
        except Exception:
            continue
        if df is None or df.empty:
            continue
        ret = np.log(df["close"]).diff().fillna(0.0) * sign * weight
        returns_frames.append(ret.reset_index(drop=True))

    if not returns_frames:
        raise DollarIndexError("Impossible de calculer l'indice dollar : aucune paire disponible.")

    combined = pd.concat(returns_frames, axis=1).sum(axis=1)
    index_series = 100 * np.exp(combined.cumsum())

    lookback = min(20, len(index_series) - 1) or 1
    change_pct = float((index_series.iloc[-1] / index_series.iloc[-lookback - 1] - 1) * 100)

    if change_pct > 0.15:
        trend = "strengthening"
    elif change_pct < -0.15:
        trend = "weakening"
    else:
        trend = "flat"

    return UsdIndexResult(series=index_series, trend=trend, change_pct=round(change_pct, 3))
