"""
空／滿緊急時計專用 SQLite（ADR-320）
====================================
與 youbike.db 分開：時計不被主庫重置、seed、或 uvicorn --reload 清掉。
路徑釘在 backend 套件旁的 data/（容器內即 /app/data），不走 PROJECT_ROOT，
避免本機把 backend 掛成 /app 時落到容器內 /backend/data（重開即丟）。

測試（YOUBIKE_DB_PATH=:memory:）仍共用主連線，不另開檔。
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Optional

_CLOCK_SCHEMA = """
CREATE TABLE IF NOT EXISTS service_problems (
    problem_id    TEXT PRIMARY KEY,
    station_id    TEXT NOT NULL,
    station_name  TEXT,
    district      TEXT,
    kind          TEXT NOT NULL,
    opened_at     TEXT NOT NULL,
    closed_at     TEXT,
    close_reason  TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_service_problems_open
    ON service_problems(station_id) WHERE closed_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_service_problems_closed
    ON service_problems(closed_at);
CREATE INDEX IF NOT EXISTS idx_service_problems_district
    ON service_problems(district, closed_at);
"""

_clock_conn: Optional[sqlite3.Connection] = None
_clock_dedicated = False


def _resolve_file_path(raw: str) -> str:
    if raw == ":memory:" or os.path.isabs(raw):
        return raw
    return str(Path(__file__).parent.parent / raw)


def clock_db_path() -> Optional[str]:
    """時計檔路徑。None 表示與主 DB 共用（測試記憶體模式）。"""
    env = os.environ.get("YOUBIKE_CLOCK_DB_PATH")
    if env:
        return env
    if os.environ.get("YOUBIKE_DB_PATH") == ":memory:":
        return None
    try:
        from config_loader import get_config
        configured = (get_config().get("service_problems", {}) or {}).get("db_path")
        if configured:
            return _resolve_file_path(str(configured))
    except Exception:
        pass
    main = os.environ.get("YOUBIKE_DB_PATH")
    if main and main != ":memory:":
        return str(Path(main).with_name("service_clock.db"))
    return str(Path(__file__).parent.parent / "data" / "service_clock.db")


def get_clock_connection() -> sqlite3.Connection:
    """取得時計連線。檔案模式 WAL，可供 API 與獨立 worker 同時讀寫。"""
    global _clock_conn, _clock_dedicated
    if _clock_conn is not None:
        return _clock_conn

    path = clock_db_path()
    if path is None:
        from db.connection import get_connection
        _clock_conn = get_connection()
        _clock_dedicated = False
        return _clock_conn

    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(
        path, check_same_thread=False, isolation_level=None, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.executescript(_CLOCK_SCHEMA)
    _clock_conn = conn
    _clock_dedicated = True
    return _clock_conn


def init_clock_db() -> None:
    """確保時計 schema 存在（worker 啟動時呼叫）。"""
    get_clock_connection()


def reset_clock_connection() -> None:
    """測試用：丢掉時計單例。共用主連線時只放掉參照，不關主連線。"""
    global _clock_conn, _clock_dedicated
    if _clock_conn is not None and _clock_dedicated:
        _clock_conn.close()
    _clock_conn = None
    _clock_dedicated = False
