"""
Lecteur du calendrier de risque local (data/risk_calendar.json).

Pourquoi un fichier local plutot qu'une API de calendrier economique ?
Les calendriers "gratuits" les plus complets (ForexFactory, Investing.com)
interdisent le scraping automatise dans leurs conditions d'utilisation.
Les API officielles (Trading Economics, etc.) sont payantes des qu'on
depasse un usage minimal. Pour un usage personnel, la solution la plus
fiable et 100% legale est de maintenir soi-meme une liste des evenements
a haut impact (2 minutes chaque dimanche soir) -- ce module se charge
ensuite de vous avertir automatiquement quand un evenement approche.

Vous pourrez brancher une vraie API payante plus tard sans rien changer
au reste de l'application : il suffira de remplacer get_upcoming_events().
"""
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import List

from app.config import settings


@dataclass
class RiskEvent:
    datetime_utc: datetime
    event: str
    currency: str
    impact: str
    hours_until: float


def _load_raw_events() -> list:
    if not settings.CALENDAR_PATH.exists():
        return []
    with open(settings.CALENDAR_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def get_upcoming_events(hours_ahead: int = 48) -> List[RiskEvent]:
    now = datetime.now(timezone.utc)
    horizon = now + timedelta(hours=hours_ahead)
    events = []
    for raw in _load_raw_events():
        try:
            dt = datetime.fromisoformat(raw["datetime_utc"]).replace(tzinfo=timezone.utc)
        except (KeyError, ValueError):
            continue
        if now <= dt <= horizon:
            hours_until = (dt - now).total_seconds() / 3600
            events.append(
                RiskEvent(
                    datetime_utc=dt,
                    event=raw.get("event", "Evenement"),
                    currency=raw.get("currency", "USD"),
                    impact=raw.get("impact", "medium"),
                    hours_until=round(hours_until, 1),
                )
            )
    return sorted(events, key=lambda e: e.datetime_utc)


def is_high_risk_window(hours_ahead: int = 3) -> bool:
    """True si un evenement a fort impact tombe dans les prochaines `hours_ahead` heures."""
    return any(e.impact == "high" for e in get_upcoming_events(hours_ahead))
