"""
③即時覆寫資料存取（db.overrides_repo）
========================================
覆寫狀態存 SQLite。取代 OverrideService 的記憶體 dict。

注意：schema 沒有獨立的 overrides 表（design §8 七張表未含），
覆寫是「短期狀態」，這裡用一張輕量表存生效中的覆寫。
若要嚴格對齊 design，可視為 station_params.override_active 的延伸；
但覆寫需記 reason/expire_at/operator，用獨立表更清楚。
"""

from __future__ import annotations
from typing import Optional

from db.connection import get_connection, commit

# 確保覆寫表存在（不在主 schema.sql 的七張表內，這裡補建）
_ENSURE = """
CREATE TABLE IF NOT EXISTS overrides (
    station_id     TEXT PRIMARY KEY,
    reason         TEXT NOT NULL,
    operator       TEXT NOT NULL,
    applied_at     TEXT NOT NULL,
    expire_at      TEXT NOT NULL,
    expire_minutes INTEGER
)
"""


def _ensure_table():
    conn = get_connection()
    conn.execute(_ENSURE)
    commit(conn)


def upsert(entry: dict) -> None:
    _ensure_table()
    conn = get_connection()
    conn.execute(
        """INSERT INTO overrides (station_id, reason, operator, applied_at, expire_at, expire_minutes)
           VALUES (:station_id, :reason, :operator, :applied_at, :expire_at, :expire_minutes)
           ON CONFLICT(station_id) DO UPDATE SET
             reason=excluded.reason, operator=excluded.operator,
             applied_at=excluded.applied_at, expire_at=excluded.expire_at,
             expire_minutes=excluded.expire_minutes""",
        entry,
    )
    commit(conn)


def get(station_id: str) -> Optional[dict]:
    _ensure_table()
    conn = get_connection()
    row = conn.execute("SELECT * FROM overrides WHERE station_id = ?", (station_id,)).fetchone()
    return dict(row) if row else None


def all_active() -> list[dict]:
    _ensure_table()
    conn = get_connection()
    return [dict(r) for r in conn.execute("SELECT * FROM overrides").fetchall()]


def delete(station_id: str) -> bool:
    _ensure_table()
    conn = get_connection()
    cur = conn.execute("DELETE FROM overrides WHERE station_id = ?", (station_id,))
    commit(conn)
    return cur.rowcount > 0
