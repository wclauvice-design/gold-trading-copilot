"""
Journal de trading en SQLite (fichier local journal.db, jamais transmis nulle part).

Le flux prevu :
1. L'app affiche une recommandation -> vous cliquez "Consigner ce trade" -> une
   ligne est creee avec TOUT ce que l'app proposait (direction, entree, SL, TP,
   confiance, quelles strategies ont declenche, raisonnement complet).
2. Vous executez (ou non) reellement l'ordre chez votre broker, et vous mettez
   a jour la ligne avec votre execution reelle (prix d'entree reel, taille).
3. Quand vous cloturez la position, vous renseignez le prix de sortie -> le
   P&L et le resultat (gagnant/perdant) sont calcules automatiquement.

Ca permet de comparer, dans la duree, ce que l'app recommandait a ce que vous
avez reellement fait, et de mesurer la performance reelle de chaque strategie.
"""
import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional

from app.config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    opened_at TEXT NOT NULL,
    closed_at TEXT,
    instrument TEXT NOT NULL DEFAULT 'XAU_USD',
    direction TEXT NOT NULL,                  -- 'long' | 'short'
    triggering_strategies TEXT,                -- JSON list des strategies qui ont declenche
    confidence_at_signal REAL,
    recommended_entry REAL,
    recommended_sl REAL,
    recommended_tp REAL,
    actual_entry REAL,
    actual_sl REAL,
    actual_tp REAL,
    lot_size REAL,
    actual_exit_price REAL,
    pnl_price_diff REAL,
    pnl_amount REAL,
    result TEXT DEFAULT 'open',                -- 'open' | 'win' | 'loss' | 'breakeven'
    rationale_snapshot TEXT,
    notes TEXT
);
"""


@contextmanager
def get_conn():
    conn = sqlite3.connect(settings.DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.execute(SCHEMA)


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
        cur = conn.execute(
            """INSERT INTO trades
               (opened_at, instrument, direction, triggering_strategies, confidence_at_signal,
                recommended_entry, recommended_sl, recommended_tp, rationale_snapshot, notes, result)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'open')""",
            (
                datetime.now(timezone.utc).isoformat(),
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
        return cur.lastrowid


def update_execution(trade_id: int, actual_entry: float, actual_sl: Optional[float], actual_tp: Optional[float], lot_size: Optional[float], notes: Optional[str] = None):
    with get_conn() as conn:
        conn.execute(
            """UPDATE trades SET actual_entry=?, actual_sl=?, actual_tp=?, lot_size=?,
               notes=COALESCE(?, notes) WHERE id=?""",
            (actual_entry, actual_sl, actual_tp, lot_size, notes, trade_id),
        )


def close_trade(trade_id: int, actual_exit_price: float, notes: Optional[str] = None):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM trades WHERE id=?", (trade_id,)).fetchone()
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

        conn.execute(
            """UPDATE trades SET closed_at=?, actual_exit_price=?, pnl_price_diff=?, pnl_amount=?,
               result=?, notes=COALESCE(?, notes) WHERE id=?""",
            (
                datetime.now(timezone.utc).isoformat(),
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
        conn.execute("DELETE FROM trades WHERE id=?", (trade_id,))


def list_trades(status: Optional[str] = None) -> List[dict]:
    query = "SELECT * FROM trades"
    params = ()
    if status == "open":
        query += " WHERE result='open'"
    elif status == "closed":
        query += " WHERE result != 'open'"
    query += " ORDER BY opened_at DESC"
    with get_conn() as conn:
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]


def get_trade(trade_id: int) -> Optional[dict]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM trades WHERE id=?", (trade_id,)).fetchone()
        return dict(row) if row else None


def get_stats() -> dict:
    trades = list_trades(status="closed")
    total = len(trades)
    wins = [t for t in trades if t["result"] == "win"]
    losses = [t for t in trades if t["result"] == "loss"]

    win_rate = round(len(wins) / total * 100, 1) if total else None
    total_pnl = sum(t["pnl_amount"] for t in trades if t["pnl_amount"] is not None)

    avg_r = None
    # R moyen : pour chaque trade cloture, on exprime le P&L en multiple du risque
    # initial (entree - stop), en utilisant l'execution reelle si renseignee, sinon
    # les niveaux recommandes par l'app. Independant du nombre de gagnants/perdants.
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
    if r_values:
        avg_r = round(sum(r_values) / len(r_values), 2)

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
