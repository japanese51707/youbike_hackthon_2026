"""
警示 + 訂閱資料存取（db.alerts_repo）
======================================
alerts 表（警示狀態，acknowledged 重啟保留）+ alert_subscriptions 表（webhook 訂閱）。
取代 AlertService 的記憶體 dict。SSE 佇列仍留記憶體（那是短暫的推送緩衝，不需持久）。
"""

from __future__ import annotations
import json
from typing import Optional

from db.connection import get_connection


# ── alerts ──
def insert_alert(alert: dict) -> None:
    conn = get_connection()
    conn.execute(
        """INSERT INTO alerts
           (alert_id, level, station_id, station_name, district, message, suggested_action, triggered_at, acknowledged)
           VALUES (:alert_id, :level, :station_id, :station_name, :district, :message, :suggested_action, :triggered_at, :acknowledged)""",
        {
            "alert_id": alert["alert_id"], "level": alert["level"],
            "station_id": alert.get("station_id"), "station_name": alert.get("station_name"),
            "district": alert.get("district"), "message": alert["message"],
            "suggested_action": alert.get("suggested_action"),
            "triggered_at": alert["triggered_at"],
            "acknowledged": 1 if alert.get("acknowledged") else 0,
        },
    )
    conn.commit()


def _alert_from_row(row) -> dict:
    d = dict(row)
    d["acknowledged"] = bool(d["acknowledged"])
    return d


def get_alert(alert_id: str) -> Optional[dict]:
    conn = get_connection()
    row = conn.execute("SELECT * FROM alerts WHERE alert_id = ?", (alert_id,)).fetchone()
    return _alert_from_row(row) if row else None


def acknowledge(alert_id: str) -> Optional[dict]:
    conn = get_connection()
    cur = conn.execute("UPDATE alerts SET acknowledged = 1 WHERE alert_id = ?", (alert_id,))
    conn.commit()
    if cur.rowcount == 0:
        return None
    return get_alert(alert_id)


def list_alerts(level: Optional[str] = None,
                acknowledged: Optional[bool] = None) -> list[dict]:
    conn = get_connection()
    sql = "SELECT * FROM alerts WHERE 1=1"
    params: list = []
    if level:
        levels = level.split(",")
        sql += f" AND level IN ({','.join('?' * len(levels))})"
        params.extend(levels)
    if acknowledged is not None:
        sql += " AND acknowledged = ?"; params.append(1 if acknowledged else 0)
    return [_alert_from_row(r) for r in conn.execute(sql, params).fetchall()]


def unacked_station_levels() -> set:
    """回傳 (station_id, level) 集合中「未讀」的，供去重判斷。"""
    conn = get_connection()
    rows = conn.execute(
        "SELECT station_id, level FROM alerts WHERE acknowledged = 0").fetchall()
    return {(r["station_id"], r["level"]) for r in rows}


# ── alert_subscriptions ──
def insert_subscription(sub: dict) -> None:
    conn = get_connection()
    conn.execute(
        """INSERT INTO alert_subscriptions (subscription_id, callback_url, levels, districts, token)
           VALUES (?, ?, ?, ?, ?)""",
        (sub["subscription_id"], sub["callback_url"],
         json.dumps(sub.get("levels", []), ensure_ascii=False),
         json.dumps(sub.get("districts", []), ensure_ascii=False),
         sub.get("token")),
    )
    conn.commit()


def list_subscriptions() -> list[dict]:
    conn = get_connection()
    out = []
    for r in conn.execute("SELECT * FROM alert_subscriptions").fetchall():
        d = dict(r)
        d["levels"] = json.loads(d["levels"] or "[]")
        d["districts"] = json.loads(d["districts"] or "[]")
        out.append(d)
    return out


def count_subscriptions() -> int:
    conn = get_connection()
    return conn.execute("SELECT COUNT(*) AS c FROM alert_subscriptions").fetchone()["c"]
