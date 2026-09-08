"""
Client minimal pour l'API FRED (Federal Reserve Bank of St. Louis) -- gratuite,
cle a demander sur https://fred.stlouisfed.org/docs/api/api_key.html

Sert a recuperer le taux reel americain 10 ans (serie DFII10), une des
variables les plus correlees a l'or a moyen terme : quand les taux reels
baissent, l'or est generalement soutenu (moindre cout d'opportunite a detenir
un actif sans rendement), et inversement.
"""
from dataclasses import dataclass
from typing import Optional

import httpx

from app.config import settings

FRED_URL = "https://api.stlouisfed.org/fred/series/observations"


@dataclass
class RealYieldResult:
    latest_value: Optional[float]
    change_10d: Optional[float]
    trend: str  # "rising" | "falling" | "flat" | "unknown"


def get_real_yield_trend(series_id: str = "DFII10") -> RealYieldResult:
    if not settings.FRED_API_KEY:
        return RealYieldResult(latest_value=None, change_10d=None, trend="unknown")

    params = {
        "series_id": series_id,
        "api_key": settings.FRED_API_KEY,
        "file_type": "json",
        "sort_order": "desc",
        "limit": 15,
    }
    try:
        resp = httpx.get(FRED_URL, params=params, timeout=10.0)
        resp.raise_for_status()
        data = resp.json()
    except (httpx.RequestError, httpx.HTTPStatusError, ValueError):
        return RealYieldResult(latest_value=None, change_10d=None, trend="unknown")

    obs = [o for o in data.get("observations", []) if o.get("value") not in (".", None)]
    if len(obs) < 2:
        return RealYieldResult(latest_value=None, change_10d=None, trend="unknown")

    latest = float(obs[0]["value"])
    older = float(obs[min(9, len(obs) - 1)]["value"])
    change = round(latest - older, 3)

    if change > 0.03:
        trend = "rising"
    elif change < -0.03:
        trend = "falling"
    else:
        trend = "flat"

    return RealYieldResult(latest_value=latest, change_10d=change, trend=trend)
