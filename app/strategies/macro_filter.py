"""
Strategie 3 : Filtre macro / fondamental -- ne genere pas de signal directionnel
propre, mais pondere la confiance des strategies techniques (1 et 2), comme le
font la plupart des desks professionnels : le fondamental donne le "vent" (favorable,
contraire, ou neutre), le technique donne le point d'entree precis.

Logique :
- Dollar faible + taux reels US en baisse -> vent favorable a l'or (bullish).
- Dollar fort + taux reels en hausse -> vent defavorable a l'or (bearish).
- Signaux mixtes -> neutre, on ne booste ni ne penalise.
- Evenement macro a fort impact dans les prochaines heures (NFP, FOMC, CPI...)
  -> avertissement et forte reduction de la confiance globale, quelle que soit
  la direction (la volatilite autour de ces publications rend les stops peu fiables).
"""
from dataclasses import dataclass
from typing import List, Optional

from app.data.calendar_reader import RiskEvent
from app.data.dollar_index import UsdIndexResult
from app.data.fred_client import RealYieldResult

NAME = "Filtre macro (dollar & taux reels)"


@dataclass
class MacroFilterResult:
    gold_bias: str  # "bullish" | "bearish" | "neutral"
    multiplier: float  # applique a la confiance des strategies techniques alignees
    opposing_multiplier: float  # applique si une strategie technique va a CONTRE-SENS du biais macro
    risk_warning: bool
    rationale: str


def analyze(usd_index: Optional[UsdIndexResult], real_yield: RealYieldResult, risk_events: List[RiskEvent], high_risk_now: bool) -> MacroFilterResult:
    parts = []

    usd_trend = usd_index.trend if usd_index else "unknown"
    yield_trend = real_yield.trend

    if usd_trend == "weakening" and yield_trend in ("falling", "flat"):
        bias = "bullish"
        multiplier, opposing = 1.20, 0.55
        parts.append(f"Dollar en affaiblissement ({usd_index.change_pct:+.2f}% recemment) et taux reels US "
                     f"{'en baisse' if yield_trend=='falling' else 'stables'} : vent macro favorable a l'or.")
    elif usd_trend == "strengthening" and yield_trend in ("rising", "flat"):
        bias = "bearish"
        multiplier, opposing = 1.20, 0.55
        parts.append(f"Dollar en renforcement ({usd_index.change_pct:+.2f}% recemment) et taux reels US "
                     f"{'en hausse' if yield_trend=='rising' else 'stables'} : vent macro defavorable a l'or.")
    elif usd_trend == "unknown" and yield_trend == "unknown":
        bias = "neutral"
        multiplier, opposing = 1.0, 1.0
        parts.append("Donnees macro indisponibles (cle FRED manquante ?) : filtre neutre, ne se base que sur le technique.")
    else:
        bias = "neutral"
        multiplier, opposing = 0.9, 0.9
        parts.append(f"Signaux macro mixtes (dollar {usd_trend}, taux reels {yield_trend}) : "
                     "pas de vent dominant, legere prudence sur toutes les directions.")

    risk_warning = False
    if high_risk_now:
        risk_warning = True
        multiplier *= 0.6
        opposing *= 0.6
        next_events = ", ".join(f"{e.event} dans {e.hours_until:.1f}h" for e in risk_events if e.impact == "high")
        parts.append(f"ATTENTION : evenement macro a fort impact imminent ({next_events}). "
                     "Reduisez la taille de position ou attendez la publication : la volatilite va rendre "
                     "les stops peu fiables sur les minutes qui entourent l'annonce.")
    elif risk_events:
        next_event = risk_events[0]
        parts.append(f"A noter : {next_event.event} prevu dans {next_event.hours_until:.1f}h -- "
                     "gardez un oeil sur l'horaire si vous gardez une position ouverte.")

    return MacroFilterResult(
        gold_bias=bias,
        multiplier=round(multiplier, 3),
        opposing_multiplier=round(opposing, 3),
        risk_warning=risk_warning,
        rationale=" ".join(parts),
    )
