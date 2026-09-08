"""
Agregateur final : combine les 3 moteurs (tendance, smart money, macro) en UNE
recommandation exploitable, avec un niveau de confiance global et une explication
en langage clair -- c'est la piece centrale du "moteur de decision".

Principe :
- Les 2 strategies techniques (tendance + smart money) doivent s'accorder pour
  qu'on parle d'un vrai signal ; si elles se contredisent, on n'a pas de trade.
- Le filtre macro ne fait que ponderer : il peut renforcer une confluence
  technique deja presente, ou au contraire la faire tomber sous le seuil
  d'exploitation si le vent macro souffle dans l'autre sens.
- Un evenement macro a risque imminent ecrase la confiance quelle que soit
  la qualite du signal technique (discipline avant tout).
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import pandas as pd

from app.data.provider import MarketSnapshot
from app.strategies import macro_filter, smart_money, trend_following
from app.strategies.base import StrategySignal

CONFIDENCE_FLOOR_FOR_TRADE = 35


@dataclass
class Recommendation:
    direction: str  # "long" | "short" | "wait"
    confidence: float
    entry: Optional[float]
    stop_loss: Optional[float]
    take_profit: Optional[float]
    plan_source: Optional[str]
    headline: str
    rationale: str
    risk_warning: bool
    strategy_signals: List[StrategySignal] = field(default_factory=list)
    macro: Optional[macro_filter.MacroFilterResult] = None
    data_warnings: List[str] = field(default_factory=list)
    mode: str = "demo"

    def to_dict(self) -> dict:
        return {
            "direction": self.direction,
            "confidence": round(self.confidence, 1),
            "entry": self.entry,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "plan_source": self.plan_source,
            "headline": self.headline,
            "rationale": self.rationale,
            "risk_warning": self.risk_warning,
            "mode": self.mode,
            "data_warnings": self.data_warnings,
            "macro": {
                "gold_bias": self.macro.gold_bias,
                "risk_warning": self.macro.risk_warning,
                "rationale": self.macro.rationale,
            } if self.macro else None,
            "strategies": [
                {
                    "name": s.name,
                    "direction": s.direction,
                    "confidence": round(s.confidence, 1),
                    "entry": s.entry,
                    "stop_loss": s.stop_loss,
                    "take_profit": s.take_profit,
                    "risk_reward": s.risk_reward(),
                    "rationale": s.rationale,
                }
                for s in self.strategy_signals
            ],
        }


def _direction_label(direction: str) -> str:
    return {"long": "ACHAT", "short": "VENTE", "wait": "ATTENTE"}[direction]


def build_recommendation(snapshot: MarketSnapshot) -> Recommendation:
    candles: Dict[str, pd.DataFrame] = snapshot.candles

    tf_signal = trend_following.analyze(candles)
    sm_signal = smart_money.analyze(candles)
    macro_result = macro_filter.analyze(
        snapshot.usd_index, snapshot.real_yield, snapshot.risk_events, snapshot.high_risk_now
    )

    conflict_note = ""
    if tf_signal.direction != "wait" and sm_signal.direction != "wait":
        if tf_signal.direction == sm_signal.direction:
            combined_direction = tf_signal.direction
            base_confidence = (tf_signal.confidence + sm_signal.confidence) / 2 + 10
        else:
            combined_direction = "wait"
            base_confidence = 15
            conflict_note = (
                "Les deux strategies techniques se contredisent (l'une propose un achat, l'autre une vente) : "
                "par prudence, aucun trade n'est recommande tant qu'elles ne s'accordent pas."
            )
    elif tf_signal.direction != "wait":
        combined_direction = tf_signal.direction
        base_confidence = tf_signal.confidence * 0.8
    elif sm_signal.direction != "wait":
        combined_direction = sm_signal.direction
        base_confidence = sm_signal.confidence * 0.8
    else:
        combined_direction = "wait"
        base_confidence = max(tf_signal.confidence, sm_signal.confidence)

    macro_bias_map = {"bullish": "long", "bearish": "short"}
    mapped_bias = macro_bias_map.get(macro_result.gold_bias)

    if combined_direction == "wait":
        final_confidence = base_confidence
    elif mapped_bias == combined_direction:
        final_confidence = base_confidence * macro_result.multiplier
    elif mapped_bias is None:
        final_confidence = base_confidence * macro_result.multiplier
    else:
        final_confidence = base_confidence * macro_result.opposing_multiplier

    final_confidence = max(0.0, min(100.0, final_confidence))

    downgrade_note = ""
    final_direction = combined_direction
    if combined_direction != "wait" and final_confidence < CONFIDENCE_FLOOR_FOR_TRADE:
        downgrade_note = (
            f"Le signal technique existe ({_direction_label(combined_direction)}) mais la confiance combinee "
            f"retombe a {final_confidence:.0f}/100 apres ponderation macro : sous le seuil de "
            f"{CONFIDENCE_FLOOR_FOR_TRADE}/100, ce n'est pas suffisant pour agir. Recommandation : attendre."
        )
        final_direction = "wait"

    entry = stop_loss = take_profit = None
    plan_source = None
    if final_direction != "wait":
        candidates = [s for s in (sm_signal, tf_signal) if s.direction == combined_direction and s.entry is not None]
        if candidates:
            chosen = candidates[0]
            entry, stop_loss, take_profit = chosen.entry, chosen.stop_loss, chosen.take_profit
            plan_source = chosen.name

    headline = (
        f"{_direction_label(final_direction)} -- confiance {final_confidence:.0f}/100"
        if final_direction != "wait"
        else f"ATTENTE -- confiance {final_confidence:.0f}/100"
    )

    rationale_parts = []
    if conflict_note:
        rationale_parts.append(conflict_note)
    else:
        rationale_parts.append(
            f"{tf_signal.name} -> {_direction_label(tf_signal.direction)} ({tf_signal.confidence:.0f}/100). "
            f"{sm_signal.name} -> {_direction_label(sm_signal.direction)} ({sm_signal.confidence:.0f}/100)."
        )
    rationale_parts.append(macro_result.rationale)
    if downgrade_note:
        rationale_parts.append(downgrade_note)
    if snapshot.data_warnings:
        rationale_parts.append("Avertissement donnees : " + " / ".join(snapshot.data_warnings))

    return Recommendation(
        direction=final_direction,
        confidence=final_confidence,
        entry=entry,
        stop_loss=stop_loss,
        take_profit=take_profit,
        plan_source=plan_source,
        headline=headline,
        rationale=" ".join(rationale_parts),
        risk_warning=macro_result.risk_warning,
        strategy_signals=[tf_signal, sm_signal],
        macro=macro_result,
        data_warnings=snapshot.data_warnings,
        mode=snapshot.mode,
    )
