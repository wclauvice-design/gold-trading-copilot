"""
Point d'entree unique pour toutes les donnees de marche et macro.
Bascule automatiquement entre le mode DEMO (donnees simulees, zero configuration)
et le mode LIVE (vraies donnees OANDA + FRED) selon APP_MODE dans .env.

Tout le reste de l'application (strategies, API, frontend) ne parle qu'a ce module :
si un jour vous changez de broker ou de fournisseur de donnees, c'est le seul
fichier a adapter.
"""
from dataclasses import dataclass
from typing import List, Optional

import pandas as pd

from app.config import settings
from app.data import demo_data
from app.data.calendar_reader import RiskEvent, get_upcoming_events, is_high_risk_window
from app.data.dollar_index import UsdIndexResult, compute_usd_strength_index
from app.data.fred_client import RealYieldResult, get_real_yield_trend
from app.data.oanda_client import OandaClient, OandaError


@dataclass
class MarketSnapshot:
    mode: str  # "demo" | "live"
    price: dict
    candles: dict  # {granularity: DataFrame}
    usd_index: Optional[UsdIndexResult]
    real_yield: RealYieldResult
    risk_events: List[RiskEvent]
    high_risk_now: bool
    data_warnings: List[str]


class DataProvider:
    def __init__(self):
        self.instrument = settings.GOLD_INSTRUMENT
        self._oanda: Optional[OandaClient] = None
        if not settings.is_demo:
            if not settings.oanda_configured:
                raise RuntimeError(
                    "APP_MODE=live mais OANDA_API_KEY / OANDA_ACCOUNT_ID manquants dans .env"
                )
            self._oanda = OandaClient()

    def _get_candles(self, instrument: str, granularity: str, count: int) -> pd.DataFrame:
        if settings.is_demo:
            return demo_data.demo_candles(instrument, granularity, count)
        return self._oanda.get_candles(instrument, granularity, count)

    def get_candles(self, instrument: str, granularity: str, count: int) -> pd.DataFrame:
        """API publique -- utilisee par exemple par l'endpoint /api/candles."""
        return self._get_candles(instrument, granularity, count)

    def _get_price(self, instrument: str) -> dict:
        if settings.is_demo:
            return demo_data.demo_price(instrument)
        return self._oanda.get_price(instrument)

    def get_snapshot(self, granularities: List[str] = None) -> MarketSnapshot:
        granularities = granularities or ["M15", "H1", "H4"]
        warnings = []

        candles = {}
        for g in granularities:
            candles[g] = self._get_candles(self.instrument, g, 300)

        try:
            price = self._get_price(self.instrument)
        except OandaError as exc:
            warnings.append(f"Prix indisponible : {exc}")
            price = {"instrument": self.instrument, "bid": None, "ask": None, "mid": None, "time": None}

        try:
            usd_index = compute_usd_strength_index(self._get_candles, granularity="H1", count=60)
        except Exception as exc:
            warnings.append(f"Indice dollar indisponible : {exc}")
            usd_index = None

        if settings.is_demo:
            real_yield = RealYieldResult(latest_value=1.85, change_10d=-0.06, trend="falling")
        else:
            real_yield = get_real_yield_trend()
            if real_yield.trend == "unknown":
                warnings.append("Taux reel FRED indisponible (cle FRED_API_KEY manquante ou API injoignable).")

        if settings.is_demo:
            risk_events = []
            high_risk_now = False
        else:
            risk_events = get_upcoming_events(hours_ahead=48)
            high_risk_now = is_high_risk_window(hours_ahead=3)

        return MarketSnapshot(
            mode="demo" if settings.is_demo else "live",
            price=price,
            candles=candles,
            usd_index=usd_index,
            real_yield=real_yield,
            risk_events=risk_events,
            high_risk_now=high_risk_now,
            data_warnings=warnings,
        )


provider = DataProvider()
