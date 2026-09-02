"""
稽核留痕資料存取（db.audit_repo）
==================================
audit_logs 表的 append-only 寫入與查詢。取代 AuditService 的記憶體 list。
"""

from __future__ import annotations
from typing import Optional

from db.connection import get_connection


def insert(log: dict) -> None:
    """寫一筆稽核（append-only）。log 為已組好的 dict。"""
    conn = get_connection()
    conn.execute(
        """INSERT INTO audit_logs
           (log_id, type, station_id, operator, action, reason, timestamp, expired_at, task_duration_minutes)
           VALUES (:log_id, :type, :station_id, :operator, :action, :reason, :timestamp, :expired_at, :task_duration_minutes)""",
        {
            "log_id": log["log_id"], "type": log["type"],
            "station_id": log.get("station_id"), "operator": log["operator"],
            "action": log["action"], "reason": log.get("reason"),
            "timestamp": log["timestamp"], "expired_at": log.get("expired_at"),
            "task_duration_minutes": log.get("task_duration_minutes"),
        },
    )
    conn.commit()


def query(type: Optional[str] = None, station_id: Optional[str] = None,
          operator: Optional[str] = None) -> list[dict]:
    conn = get_connection()
    sql = "SELECT * FROM audit_logs WHERE 1=1"
    params: list = []
    if type:
        sql += " AND type = ?"; params.append(type)
    if station_id:
        sql += " AND station_id = ?"; params.append(station_id)
    if operator:
        sql += " AND operator = ?"; params.append(operator)
    sql += " ORDER BY timestamp"
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def all_logs() -> list[dict]:
    conn = get_connection()
    return [dict(r) for r in conn.execute(
        "SELECT * FROM audit_logs ORDER BY timestamp").fetchall()]


def count() -> int:
    conn = get_connection()
    return conn.execute("SELECT COUNT(*) AS c FROM audit_logs").fetchone()["c"]
