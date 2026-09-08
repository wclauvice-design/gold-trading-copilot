"""
Strategie 1 : Suivi de tendance intraday (EMA + RSI + MACD, filtre ATR pour le risque).

Logique :
1. Biais de tendance determine sur H1 : alignement EMA20/EMA50/EMA200 + pente de l'EMA20.
2. Confirmation optionnelle sur H4 (bonus de confiance si le H4 va dans le meme sens).
3. Declencheur d'entree sur M15 : pullback vers la zone EMA20/EMA50 avec RSI qui
   revient d'une zone de survente/surachat + histogramme MACD qui change de signe
   dans le sens de la tendance.
4. Stop loss = 1.5x ATR14(H1), take profit = 2x le risque (ratio 1:2 minimum).

C'est une approche "classique" et robuste, qui evite de trader a contre-tendance --
la grande majorite des pertes des traders debutants viennent de vouloir "pecher le
sommet ou le fond" contre une tendance etablie.
"""
from typing import Dict

import pandas as pd

from app.analysis.indicators import enrich_with_indicators
from app.strategies.base import StrategySignal

NAME = "Suivi de tendance (EMA/RSI/MACD)"


def _trend_bias(h1: pd.DataFrame) -> str:
    last = h1.iloc[-1]
    ema20_slope = h1["ema20"].iloc[-1] - h1["ema20"].iloc[-5]

    if last["close"] > last["ema50"] > last["ema200"] and ema20_slope > 0:
        return "bullish"
    if last["close"] < last["ema50"] < last["ema200"] and ema20_slope < 0:
        return "bearish"
    return "neutral"


def _entry_trigger(m15: pd.DataFrame, bias: str) -> bool:
    last, prev = m15.iloc[-1], m15.iloc[-2]
    recent_rsi_min = m15["rsi14"].iloc[-6:-1].min()
    recent_rsi_max = m15["rsi14"].iloc[-6:-1].max()

    macd_flip_up = prev["macd_hist"] <= 0 and last["macd_hist"] > 0
    macd_flip_down = prev["macd_hist"] >= 0 and last["macd_hist"] < 0

    if bias == "bullish":
        return recent_rsi_min < 42 and last["rsi14"] > recent_rsi_min and macd_flip_up
    if bias == "bearish":
        return recent_rsi_max > 58 and last["rsi14"] < recent_rsi_max and macd_flip_down
    return False


def analyze(candles: Dict[str, pd.DataFrame]) -> StrategySignal:
    h1 = enrich_with_indicators(candles["H1"])
    m15 = enrich_with_indicators(candles["M15"])
    h4 = enrich_with_indicators(candles["H4"]) if "H4" in candles else None

    bias = _trend_bias(h1)

    if bias == "neutral":
        return StrategySignal(
            name=NAME,
            direction="wait",
            confidence=20,
            rationale="Pas de tendance claire sur H1 (EMA emmelees) : le suivi de tendance "
                       "ne s'applique pas dans ce contexte de range.",
            details={"bias": bias},
        )

    last_close = h1["close"].iloc[-1]
    atr_h1 = h1["atr14"].iloc[-1]
    triggered = _entry_trigger(m15, bias)

    confidence = 45
    ema_gap = abs(h1["ema20"].iloc[-1] - h1["ema50"].iloc[-1])
    if atr_h1 > 0 and ema_gap / atr_h1 > 0.5:
        confidence += 10  # tendance H1 bien etablie, pas juste un croisement naissant

    h4_agrees = None
    if h4 is not None and len(h4) > 5:
        h4_bias = _trend_bias(h4)
        h4_agrees = h4_bias == bias
        if h4_agrees:
            confidence += 15
        elif h4_bias != "neutral":
            confidence -= 10  # H4 contredit H1, prudence

    direction = "wait"
    entry = stop_loss = take_profit = None
    rationale_parts = [f"Biais H1 {'haussier' if bias=='bullish' else 'baissier'} (prix {'au-dessus' if bias=='bullish' else 'en-dessous'} des EMA50/EMA200)."]

    if h4_agrees is True:
        rationale_parts.append("Le H4 confirme la meme direction (confluence multi-timeframe).")
    elif h4_agrees is False:
        rationale_parts.append("Attention : le H4 va dans le sens oppose, tendance H1 possiblement en fin de course.")

    if triggered:
        confidence += 15
        direction = "long" if bias == "bullish" else "short"
        entry = float(last_close)
        risk = 1.5 * atr_h1
        if direction == "long":
            stop_loss = round(entry - risk, 3)
            take_profit = round(entry + 2 * risk, 3)
        else:
            stop_loss = round(entry + risk, 3)
            take_profit = round(entry - 2 * risk, 3)
        rationale_parts.append(
            "Declencheur d'entree valide sur M15 (RSI en reprise + MACD qui bascule dans le sens de la tendance)."
        )
    else:
        rationale_parts.append(
            "Pas encore de declencheur d'entree propre sur M15 : attendre un pullback vers l'EMA20/EMA50 "
            "avec un retournement RSI/MACD avant d'entrer."
        )

    confidence = max(0, min(100, confidence))

    return StrategySignal(
        name=NAME,
        direction=direction,
        confidence=confidence,
        entry=entry,
        stop_loss=stop_loss,
        take_profit=take_profit,
        rationale=" ".join(rationale_parts),
        details={"bias": bias, "h4_agrees": h4_agrees, "triggered": triggered},
    )
