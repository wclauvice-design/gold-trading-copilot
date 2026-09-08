"""
Client OANDA v20 REST API.
Recupere des bougies OHLC pour n'importe quel instrument (or, paires FX...).
Utilise directement depuis votre machine avec votre propre cle API -- rien ne transite ailleurs.
Doc officielle: https://developer.oanda.com/rest-live-v20/instrument-ep/
"""
from datetime import datetime, timezone
from typing import Optional

import httpx
import pandas as pd

from app.config import settings


class OandaError(RuntimeError):
    pass


class OandaClient:
    def __init__(self):
        self.base_url = settings.oanda_base_url
        self.headers = {
            "Authorization": f"Bearer {settings.OANDA_API_KEY}",
            "Accept-Datetime-Format": "RFC3339",
        }

    def _get(self, path: str, params: dict) -> dict:
        url = f"{self.base_url}{path}"
        try:
            resp = httpx.get(url, headers=self.headers, params=params, timeout=10.0)
        except httpx.RequestError as exc:
            raise OandaError(f"Impossible de contacter OANDA: {exc}") from exc
        if resp.status_code != 200:
            raise OandaError(f"OANDA a repondu {resp.status_code}: {resp.text[:300]}")
        return resp.json()

    def get_candles(self, instrument: str, granularity: str = "M15", count: int = 300) -> pd.DataFrame:
        """
        granularity: S5,S10,S15,S30,M1,M2,M4,M5,M10,M15,M30,H1,H2,H3,H4,H6,H8,H12,D,W,M
        Retourne un DataFrame avec colonnes: time, open, high, low, close, volume, complete
        """
        data = self._get(
            f"/v3/instruments/{instrument}/candles",
            {"granularity": granularity, "count": count, "price": "M"},
        )
        rows = []
        for c in data.get("candles", []):
            mid = c["mid"]
            rows.append(
                {
                    "time": pd.to_datetime(c["time"]),
                    "open": float(mid["o"]),
                    "high": float(mid["h"]),
                    "low": float(mid["l"]),
                    "close": float(mid["c"]),
                    "volume": int(c.get("volume", 0)),
                    "complete": bool(c.get("complete", True)),
                }
            )
        df = pd.DataFrame(rows)
        return df

    def get_price(self, instrument: str) -> Optional[dict]:
        """Prix bid/ask instantane."""
        data = self._get("/v3/accounts/" + settings.OANDA_ACCOUNT_ID + "/pricing", {"instruments": instrument})
        prices = data.get("prices", [])
        if not prices:
            return None
        p = prices[0]
        bid = float(p["bids"][0]["price"]) if p.get("bids") else None
        ask = float(p["asks"][0]["price"]) if p.get("asks") else None
        return {
            "instrument": instrument,
            "bid": bid,
            "ask": ask,
            "mid": (bid + ask) / 2 if bid and ask else None,
            "time": p.get("time"),
        }
