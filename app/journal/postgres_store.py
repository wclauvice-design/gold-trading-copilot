"""
Meme journal que sqlite_store.py, mais sur Postgres (utilise en production sur
Vercel, qui n'offre pas de disque persistant pour un fichier SQLite).

Active automatiquement des que DATABASE_URL (ou POSTGRES_URL, injecte par
Vercel Postgres) est present dans l'environnement -- voir app/journal/db.py.
"""
import json
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import List, Optional

import psycopg2
import psycopg2.extras

from app.config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS trades (
    id SERIAL PRIMARY KEY,
    opened_at TIMESTAMPTZ NOT NULL,
    closed_at TIMESTAMPTZ,
    instrument TEXT NOT NULL DEFAULT 'XAU_USD',
    direction TEXT NOT NULL,
    triggering_strategies TEXT,
    confidence_at_signal DOUBLE PRECISION,
    recommended_entry DOUBLE PRECISION,
    recommended_sl DOUBLE PRECISION,
    recommended_tp DOUBLE PRECISION,
    actual_entry DOUBLE PRECISION,
    actual_sl DOUBLE PRECISION,
    actual_tp DOUBLE PRECISION,
    lot_size DOUBLE PRECISION,
    actual_exit_price DOUBLE PRECISION,
    pnl_price_diff DOUBLE PRECISION,
    pnl_amount DOUBLE PRECISION,
    result TEXT DEFAULT 'open',
    rationale_snapshot TEXT,
    notes TEXT
);
"""


@contextmanager
def get_conn():
    conn = psycopg2.connect(settings.database_url, cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(SCHEMA)


def _row_to_dict(row) -> dict:
    d = dict(row)
    for key in ("opened_at", "closed_at"):
        if d.get(key) is not None and not isinstance(d[key], str):
            d[key] = d[key].isoformat()
    return d


def create_trade(
    direction: str,
    triggering_strategies: List[str],
    confidence_at_signal: float,
    recommended_entry: Optional[float],
    recommended_sl: Optional[float],
    recommended_tp: Optional[float],
    rationale_snapshot: str,
    instrument: str = "XAU_USD",
    notes: str = "",
) -> int:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO trades
                   (opened_at, instrument, direction, triggering_strategies, confidence_at_signal,
                    recommended_entry, recommended_sl, recommended_tp, rationale_snapshot, notes, result)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'open') RETURNING id""",
                (
                    datetime.now(timezone.utc),
                    instrument,
                    direction,
                    json.dumps(triggering_strategies),
                    confidence_at_signal,
                    recommended_entry,
                    recommended_sl,
                    recommended_tp,
                    rationale_snapshot,
                    notes,
                ),
            )
            return cur.fetchone()["id"]


def update_execution(trade_id: int, actual_entry: float, actual_sl: Optional[float], actual_tp: Optional[float], lot_size: Optional[float], notes: Optional[str] = None):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE trades SET actual_entry=%s, actual_sl=%s, actual_tp=%s, lot_size=%s,
                   notes=COALESCE(%s, notes) WHERE id=%s""",
                (actual_entry, actual_sl, actual_tp, lot_size, notes, trade_id),
            )


def close_trade(trade_id: int, actual_exit_price: float, notes: Optional[str] = None):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM trades WHERE id=%s", (trade_id,))
            row = cur.fetchone()
            if row is None:
                raise ValueError(f"Trade {trade_id} introuvable")

            entry = row["actual_entry"] if row["actual_entry"] is not None else row["recommended_entry"]
            lot_size = row["lot_size"] or 1.0
            direction_mult = 1 if row["direction"] == "long" else -1

            pnl_price_diff = (actual_exit_price - entry) * direction_mult if entry is not None else None
            pnl_amount = pnl_price_diff * lot_size if pnl_price_diff is not None else None

            if pnl_price_diff is None:
                result = "open"
            elif abs(pnl_price_diff) < 1e-9:
                result = "breakeven"
            elif pnl_price_diff > 0:
                result = "win"
            else:
                result = "loss"

            cur.execute(
                """UPDATE trades SET closed_at=%s, actual_exit_price=%s, pnl_price_diff=%s, pnl_amount=%s,
                   result=%s, notes=COALESCE(%s, notes) WHERE id=%s""",
                (
                    datetime.now(timezone.utc),
                    actual_exit_price,
                    pnl_price_diff,
                    pnl_amount,
                    result,
                    notes,
                    trade_id,
                ),
            )


def delete_trade(trade_id: int):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM trades WHERE id=%s", (trade_id,))


def list_trades(status: Optional[str] = None) -> List[dict]:
    query = "SELECT * FROM trades"
    if status == "open":
        query += " WHERE result='open'"
    elif status == "closed":
        query += " WHERE result != 'open'"
    query += " ORDER BY opened_at DESC"
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(query)
            return [_row_to_dict(r) for r in cur.fetchall()]


def get_trade(trade_id: int) -> Optional[dict]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM trades WHERE id=%s", (trade_id,))
            row = cur.fetchone()
            return _row_to_dict(row) if row else None


def get_stats() -> dict:
    trades = list_trades(status="closed")
    total = len(trades)
    wins = [t for t in trades if t["result"] == "win"]

    win_rate = round(len(wins) / total * 100, 1) if total else None
    total_pnl = sum(t["pnl_amount"] for t in trades if t["pnl_amount"] is not None)

    r_values = []
    for t in trades:
        if t["pnl_price_diff"] is None:
            continue
        entry = t["actual_entry"] if t["actual_entry"] is not None else t["recommended_entry"]
        sl = t["actual_sl"] if t["actual_sl"] is not None else t["recommended_sl"]
        if entry is None or sl is None or entry == sl:
            continue
        risk_unit = abs(entry - sl)
        r_values.append(t["pnl_price_diff"] / risk_unit)
    avg_r = round(sum(r_values) / len(r_values), 2) if r_values else None

    per_strategy: dict = {}
    for t in trades:
        try:
            strategies = json.loads(t["triggering_strategies"] or "[]")
        except json.JSONDecodeError:
            strategies = []
        key = " + ".join(strategies) if strategies else "inconnu"
        bucket = per_strategy.setdefault(key, {"total": 0, "wins": 0})
        bucket["total"] += 1
        if t["result"] == "win":
            bucket["wins"] += 1
    for key, bucket in per_strategy.items():
        bucket["win_rate"] = round(bucket["wins"] / bucket["total"] * 100, 1) if bucket["total"] else None

    equity_curve = []
    running = 0.0
    for t in sorted(trades, key=lambda x: x["closed_at"] or ""):
        if t["pnl_amount"] is not None:
            running += t["pnl_amount"]
            equity_curve.append({"closed_at": t["closed_at"], "equity": round(running, 2)})

    return {
        "total_closed_trades": total,
        "win_rate": win_rate,
        "total_pnl": round(total_pnl, 2) if trades else 0,
        "avg_r_multiple": avg_r,
        "per_strategy": per_strategy,
        "equity_curve": equity_curve,
    }
