"""
空／滿緊急時計專用 SQLite（ADR-326）
====================================
與 youbike.db 分開：時計不被主庫重置、seed、或 uvicorn --reload 清掉。
路徑釘在 backend 套件旁的 data/（容器內即 /app/data），不走 PROJECT_ROOT，
避免本機把 backend 掛成 /app 時落到容器內 /backend/data（重開即丟）。

測試（YOUBIKE_DB_PATH=:memory:）仍共用主連線，不另開檔。
"""

from __future__ import annotations

import os
import sqlite3
import time
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

CREATE TABLE IF NOT EXISTS station_snapshots (
    observed_at      TEXT NOT NULL,
    station_id       TEXT NOT NULL,
    station_name     TEXT,
    district         TEXT,
    status           TEXT,
    available_bikes  INTEGER,
    available_docks  INTEGER,
    total_docks      INTEGER,
    PRIMARY KEY (observed_at, station_id)
);
CREATE INDEX IF NOT EXISTS idx_station_snapshots_station
    ON station_snapshots(station_id, observed_at);
CREATE INDEX IF NOT EXISTS idx_station_snapshots_observed
    ON station_snapshots(observed_at);
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


def _sidecar_paths(path: str) -> list[Path]:
    return [Path(f"{path}-wal"), Path(f"{path}-shm"), Path(f"{path}-journal")]


def _quarantine_clock_file(path: str) -> None:
    """把壞掉的時計檔挪走，讓下一輪重建。EFS 上曾出現 file is not a database。"""
    target = Path(path)
    stamp = int(time.time())
    if target.is_dir():
        broken = target.with_name(f"{target.name}.broken-dir-{stamp}")
        target.rename(broken)
        print(f"[clock] 時計路徑是目錄，已改名 {broken}", flush=True)
    elif target.exists():
        broken = target.with_name(f"{target.name}.broken-{stamp}")
        try:
            target.replace(broken)
        except OSError:
            target.unlink()
            broken = None
        print(f"[clock] 時計檔不是資料庫，已隔離 {broken or path}", flush=True)
    for extra in _sidecar_paths(path):
        extra.unlink(missing_ok=True)


def _connect_clock_file(path: str) -> sqlite3.Connection:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(
        path, check_same_thread=False, isolation_level=None, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 8000")
    conn.execute("SELECT name FROM sqlite_master LIMIT 1")
    # EFS／NFS 上 WAL 容易弄壞檔；時計是單寫多讀，DELETE journal 較穩。
    conn.execute("PRAGMA journal_mode = DELETE")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(_CLOCK_SCHEMA)
    return conn


def get_clock_connection() -> sqlite3.Connection:
    """取得時計連線。檔案壞掉時隔離重建，不讓 API／worker 整支死掉。"""
    global _clock_conn, _clock_dedicated
    if _clock_conn is not None:
        try:
            _clock_conn.execute("SELECT 1")
            return _clock_conn
        except sqlite3.Error:
            print("[clock] 既有連線失效，重建", flush=True)
            reset_clock_connection()

    path = clock_db_path()
    if path is None:
        from db.connection import get_connection
        _clock_conn = get_connection()
        _clock_dedicated = False
        return _clock_conn

    try:
        conn = _connect_clock_file(path)
    except sqlite3.DatabaseError as exc:
        print(f"[clock] 開啟失敗（{exc}），重建", flush=True)
        try:
            _quarantine_clock_file(path)
            conn = _connect_clock_file(path)
        except sqlite3.DatabaseError:
            raise
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
