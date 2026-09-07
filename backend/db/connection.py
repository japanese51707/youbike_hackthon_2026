"""
SQLite 連線管理（core 持久層底座）
====================================
職責：提供 SQLite 連線、初始化 schema、共用的查詢輔助。
上層（operators/tasks/audit... repository）都透過這裡取得連線，不各自開檔。

設計：
  - DB 路徑從 config.yaml 的 database.path 讀（可用環境變數 YOUBIKE_DB_PATH 覆寫）
  - 連線設 row_factory=Row，讓查詢結果可用欄位名存取（像 dict）
  - 啟動時自動執行 schema.sql（IF NOT EXISTS，重跑安全）
  - 支援 :memory: 模式（測試用，config 設 ":memory:" 或環境變數）

注意：SQLite 預設同一連線不可跨執行緒；FastAPI 用 check_same_thread=False + 短連線。
黑客松規模流量小，這樣夠用；正式高併發應換連線池或 PostgreSQL。
"""

from __future__ import annotations
import os
import sqlite3
from pathlib import Path
from typing import Optional

_SCHEMA_PATH = Path(__file__).parent / "schema.sql"

# 記憶體 DB 需共用同一連線（否則每次連線是不同的空 DB）
_memory_conn: Optional[sqlite3.Connection] = None


# 專案根（backend/ 的上一層），用來把 config 的相對路徑解析成絕對路徑，
# 避免因啟動工作目錄不同（專案根 vs backend/）而疊出 backend/backend/data。
_PROJECT_ROOT = Path(__file__).parent.parent.parent


def _db_path() -> str:
    """DB 路徑：環境變數 > config.database.path（相對於專案根）> 預設 backend/data/youbike.db。"""
    env = os.environ.get("YOUBIKE_DB_PATH")
    if env:
        return env
    try:
        from config_loader import get_config
        p = get_config().get("database", {}).get("path")
        if p:
            if p == ":memory:" or os.path.isabs(p):
                return p
            # 相對路徑一律相對於專案根，不受啟動工作目錄影響
            return str(_PROJECT_ROOT / p)
    except Exception:
        pass
    return str(Path(__file__).parent.parent / "data" / "youbike.db")


def get_connection() -> sqlite3.Connection:
    """取得 SQLite 連線（row_factory=Row）。記憶體模式共用單一連線。"""
    global _memory_conn
    path = _db_path()

    if path == ":memory:":
        if _memory_conn is None:
            _memory_conn = sqlite3.connect(":memory:", check_same_thread=False)
            _memory_conn.row_factory = sqlite3.Row
            _init_schema(_memory_conn)
        return _memory_conn

    # 檔案模式：確保目錄存在
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(_SCHEMA_PATH.read_text(encoding="utf-8"))
    _apply_migrations(conn)
    conn.commit()


# 輕量 migration：既有 DB 的表已存在，schema.sql 的 IF NOT EXISTS 不會補新欄位，
# 這裡用 PRAGMA 檢查後 ADD COLUMN（SQLite 無 ADD COLUMN IF NOT EXISTS）。冪等、重跑安全。
_MIGRATIONS = [
    ("operators", "current_district", "TEXT"),   # ADR-114
    ("tasks", "district", "TEXT"),               # ADR-114
    ("tasks", "assigned_vehicle", "TEXT"),       # ADR-114
]


def _apply_migrations(conn: sqlite3.Connection) -> None:
    for table, col, coltype in _MIGRATIONS:
        cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if col not in cols:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {coltype}")


def init_db() -> None:
    """初始化 schema（啟動時呼叫）。IF NOT EXISTS，重跑安全。"""
    path = _db_path()
    if path == ":memory:":
        get_connection()   # 記憶體模式在建連線時已初始化
        return
    conn = get_connection()
    try:
        _init_schema(conn)
    finally:
        conn.close()


def reset_memory_db() -> None:
    """測試用：清掉記憶體 DB 單例（下次 get_connection 會重建空 DB）。"""
    global _memory_conn
    if _memory_conn is not None:
        _memory_conn.close()
        _memory_conn = None
