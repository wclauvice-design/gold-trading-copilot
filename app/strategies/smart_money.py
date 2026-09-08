"""
Strategie 2 : Structure de marche / Smart Money Concepts simplifie.

Logique :
1. Determine la structure de fond sur H1 (HH/HL haussier, LH/LL baissier, ou range).
2. Cherche sur M15 un balayage de liquidite recent (meche au-dela d'un swing high/low
   recent puis cloture de retour a l'interieur = piege a stop-loss classique).
3. Identifie la zone d'order block laissee par le dernier chandelier oppose avant
   le mouvement impulsif qui suit le balayage.
4. Signal fort si le prix est actuellement revenu dans cette zone ET que la
   direction du balayage est coherente avec la structure H1.

Cette approche cible specifiquement le comportement institutionnel tres present
sur l'or (mouvements de chasse aux stops autour des niveaux evidents, avant les
vrais mouvements directionnels) -- complementaire au suivi de tendance classique.
"""
from typing import Dict

import pandas as pd

from app.analysis.structure import (
    classify_trend,
    detect_liquidity_sweep,
    find_order_block,
    find_swing_points,
)
from app.strategies.base import StrategySignal

NAME = "Structure & Smart Money (balayage de liquidite + order block)"

ZONE_BUFFER_ATR_MULT = 0.15


def analyze(candles: Dict[str, pd.DataFrame]) -> StrategySignal:
    from app.analysis.indicators import atr  # import local pour eviter un cycle

    h1 = candles["H1"]
    m15 = candles["M15"]

    h1_swings = find_swing_points(h1, window=2)
    h1_trend = classify_trend(h1_swings)

    m15_swings = find_swing_points(m15, window=2)
    sweep = detect_liquidity_sweep(m15, m15_swings)

    if sweep is None:
        return StrategySignal(
            name=NAME,
            direction="wait",
            confidence=20,
            rationale="Aucun balayage de liquidite net detecte recemment sur M15 : "
                       "pas de signature institutionnelle claire pour le moment.",
            details={"h1_trend": h1_trend},
        )

    order_block = find_order_block(m15, sweep)
    if order_block is None:
        return StrategySignal(
            name=NAME,
            direction="wait",
            confidence=35,
            rationale=f"Balayage de liquidite {sweep.direction} detecte vers {sweep.swept_level:.2f}, "
                      "mais impossible d'identifier une zone d'order block exploitable derriere.",
            details={"h1_trend": h1_trend, "sweep_direction": sweep.direction},
        )

    current_price = float(m15["close"].iloc[-1])
    m15_atr = float(atr(m15, 14).iloc[-1])
    buffer = ZONE_BUFFER_ATR_MULT * m15_atr
    zone_low, zone_high = order_block.zone_low - buffer, order_block.zone_high + buffer
    in_zone = zone_low <= current_price <= zone_high

    direction_map = {"bullish": "long", "bearish": "short"}
    proposed_direction = direction_map[order_block.direction]

    aligned_with_h1 = (h1_trend == order_block.direction) or h1_trend == "ranging"

    confidence = 45
    if aligned_with_h1 and h1_trend != "ranging":
        confidence += 20
    elif h1_trend not in ("undefined", "ranging") and h1_trend != order_block.direction:
        confidence -= 15  # sweep a contre-tendance H1

    rationale_parts = [
        f"Balayage de liquidite {('haussier' if sweep.direction=='bullish' else 'baissier')} repere autour de "
        f"{sweep.swept_level:.2f}, avec cloture de retour a l'interieur (piege a stop-loss)."
    ]
    if h1_trend != "ranging" and h1_trend != "undefined":
        rationale_parts.append(
            f"Structure H1 {'haussiere' if h1_trend=='bullish' else 'baissiere'} "
            f"{'coherente avec' if aligned_with_h1 else 'a CONTRE-SENS de'} ce balayage."
        )

    entry = stop_loss = take_profit = None
    if in_zone:
        confidence += 15
        entry = current_price
        if order_block.direction == "bullish":
            stop_loss = round(sweep.swept_level - buffer, 3)
            risk = entry - stop_loss
            take_profit = round(entry + 2 * risk, 3)
        else:
            stop_loss = round(sweep.swept_level + buffer, 3)
            risk = stop_loss - entry
            take_profit = round(entry - 2 * risk, 3)
        direction = proposed_direction
        rationale_parts.append(
            f"Le prix est actuellement DANS la zone d'order block ({zone_low:.2f} - {zone_high:.2f}) : "
            "fenetre d'entree valide des maintenant."
        )
    else:
        direction = "wait"
        rationale_parts.append(
            f"Attendre un retour du prix dans la zone d'order block ({zone_low:.2f} - {zone_high:.2f}) "
            f"avant d'envisager une entree {('acheteuse' if proposed_direction=='long' else 'vendeuse')}."
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
        details={
            "h1_trend": h1_trend,
            "sweep_direction": sweep.direction,
            "sweep_level": sweep.swept_level,
            "order_block_zone": [zone_low, zone_high],
            "in_zone": in_zone,
            "proposed_direction": proposed_direction,
        },
    )
