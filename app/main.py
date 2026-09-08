"""
Backend FastAPI : expose la recommandation du moteur de decision, les bougies
pour le graphique, et le journal de trading. Sert aussi le dashboard statique.

Lancement : uvicorn app.main:app --reload --port 8000
Puis ouvrez http://localhost:8000 dans votre navigateur.
"""
import base64
import secrets
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.config import settings
from app.data.provider import provider
from app.journal import db as journal_db
from app.strategies.aggregator import build_recommendation

app = FastAPI(title="Gold Trading Copilot", version="0.1.0")


@app.middleware("http")
async def basic_auth_middleware(request: Request, call_next):
    """Protege tout le dashboard par mot de passe des que DASHBOARD_PASSWORD est
    defini (c'est le cas en production sur Vercel, ou l'URL est publique).
    En local sans DASHBOARD_PASSWORD dans .env, l'app reste ouverte."""
    if not settings.DASHBOARD_PASSWORD:
        return await call_next(request)

    auth_header = request.headers.get("authorization", "")
    valid = False
    if auth_header.startswith("Basic "):
        try:
            decoded = base64.b64decode(auth_header[6:]).decode("utf-8")
            _, _, password = decoded.partition(":")
            valid = secrets.compare_digest(password, settings.DASHBOARD_PASSWORD)
        except Exception:
            valid = False

    if not valid:
        return Response(
            status_code=401,
            headers={"WWW-Authenticate": 'Basic realm="Gold Trading Copilot"'},
        )
    return await call_next(request)


journal_db.init_db()

STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def root():
    return FileResponse(STATIC_DIR / "index.html")


# ---------------------------------------------------------------------------
# Marche & recommandation
# ---------------------------------------------------------------------------

@app.get("/api/status")
def api_status():
    return {
        "mode": "demo" if settings.is_demo else "live",
        "oanda_configured": settings.oanda_configured,
        "fred_configured": bool(settings.FRED_API_KEY),
        "instrument": settings.GOLD_INSTRUMENT,
    }


@app.get("/api/recommendation")
def api_recommendation():
    try:
        snapshot = provider.get_snapshot()
        rec = build_recommendation(snapshot)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    payload = rec.to_dict()
    payload["price"] = snapshot.price
    payload["usd_index"] = (
        {"trend": snapshot.usd_index.trend, "change_pct": snapshot.usd_index.change_pct}
        if snapshot.usd_index
        else None
    )
    payload["real_yield"] = {
        "value": snapshot.real_yield.latest_value,
        "trend": snapshot.real_yield.trend,
        "change_10d": snapshot.real_yield.change_10d,
    }
    payload["risk_events"] = [
        {"event": e.event, "currency": e.currency, "impact": e.impact, "hours_until": e.hours_until}
        for e in snapshot.risk_events
    ]
    return payload


@app.get("/api/candles")
def api_candles(granularity: str = "M15", count: int = 200):
    df = provider.get_candles(settings.GOLD_INSTRUMENT, granularity, count)
    df = df.copy()
    df["time"] = (df["time"].astype("int64") // 10**9)  # timestamp unix secondes pour lightweight-charts
    return df[["time", "open", "high", "low", "close"]].to_dict(orient="records")


# ---------------------------------------------------------------------------
# Journal de trading
# ---------------------------------------------------------------------------

class LogTradeRequest(BaseModel):
    direction: str
    triggering_strategies: List[str] = []
    confidence_at_signal: float = 0
    recommended_entry: Optional[float] = None
    recommended_sl: Optional[float] = None
    recommended_tp: Optional[float] = None
    rationale_snapshot: str = ""
    notes: str = ""


class ExecutionUpdate(BaseModel):
    actual_entry: float
    actual_sl: Optional[float] = None
    actual_tp: Optional[float] = None
    lot_size: Optional[float] = None
    notes: Optional[str] = None


class CloseTradeRequest(BaseModel):
    actual_exit_price: float
    notes: Optional[str] = None


@app.post("/api/journal/trades")
def api_create_trade(body: LogTradeRequest):
    if body.direction not in ("long", "short"):
        raise HTTPException(status_code=400, detail="direction doit etre 'long' ou 'short'")
    trade_id = journal_db.create_trade(
        direction=body.direction,
        triggering_strategies=body.triggering_strategies,
        confidence_at_signal=body.confidence_at_signal,
        recommended_entry=body.recommended_entry,
        recommended_sl=body.recommended_sl,
        recommended_tp=body.recommended_tp,
        rationale_snapshot=body.rationale_snapshot,
        notes=body.notes,
    )
    return journal_db.get_trade(trade_id)


@app.get("/api/journal/trades")
def api_list_trades(status: Optional[str] = None):
    return journal_db.list_trades(status=status)


@app.get("/api/journal/trades/{trade_id}")
def api_get_trade(trade_id: int):
    trade = journal_db.get_trade(trade_id)
    if trade is None:
        raise HTTPException(status_code=404, detail="Trade introuvable")
    return trade


@app.patch("/api/journal/trades/{trade_id}/execution")
def api_update_execution(trade_id: int, body: ExecutionUpdate):
    if journal_db.get_trade(trade_id) is None:
        raise HTTPException(status_code=404, detail="Trade introuvable")
    journal_db.update_execution(
        trade_id, body.actual_entry, body.actual_sl, body.actual_tp, body.lot_size, body.notes
    )
    return journal_db.get_trade(trade_id)


@app.patch("/api/journal/trades/{trade_id}/close")
def api_close_trade(trade_id: int, body: CloseTradeRequest):
    if journal_db.get_trade(trade_id) is None:
        raise HTTPException(status_code=404, detail="Trade introuvable")
    journal_db.close_trade(trade_id, body.actual_exit_price, body.notes)
    return journal_db.get_trade(trade_id)


@app.delete("/api/journal/trades/{trade_id}")
def api_delete_trade(trade_id: int):
    journal_db.delete_trade(trade_id)
    return {"ok": True}


@app.get("/api/journal/stats")
def api_journal_stats():
    return journal_db.get_stats()
