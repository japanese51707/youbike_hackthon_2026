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
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
from threading import RLock
from pathlib import Path
from typing import Optional

_SCHEMA_PATH = Path(__file__).parent / "schema.sql"

# 記憶體 DB 需共用同一連線（否則每次連線是不同的空 DB）
_memory_conn: Optional[sqlite3.Connection] = None
# 檔案 DB 也共用單一連線：避免多連線各自持有讀交易 snapshot，造成
# 「A 連線寫入 commit、B 連線 SELECT 卻讀到舊資料」的可見性不一致
# （警報清理後仍讀到已刪警報即此問題）。黑客松規模流量小，單連線 + GIL 足夠。
_shared_conn: Optional[sqlite3.Connection] = None
_transaction_conn = ContextVar("dispatch_transaction_connection", default=None)
_transaction_lock = RLock()


@contextmanager
def transaction():
    """ADR-302：巢狀服務共用交易；最外層才提交，失敗全部回滾。"""
    active = _transaction_conn.get()
    if active is not None:
        yield active
        return
    with _transaction_lock:
        conn = get_connection()
        token = _transaction_conn.set(conn)
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            _transaction_conn.reset(token)
            # 共用連線（記憶體 / 檔案）不關閉，維持單例避免 snapshot 不一致。
            if conn is not _memory_conn and conn is not _shared_conn:
                conn.close()


def atomic(fn):
    """核心服務的交易邊界；Repository 維持原介面。"""
    @wraps(fn)
    def wrapped(*args, **kwargs):
        with transaction():
            return fn(*args, **kwargs)
    return wrapped


def commit(conn):
    """交易內禁止 Repository 提前提交。"""
    if _transaction_conn.get() is not conn:
        conn.commit()


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
    active = _transaction_conn.get()
    if active is not None:
        return active
    path = _db_path()

    if path == ":memory:":
        if _memory_conn is None:
            _memory_conn = sqlite3.connect(":memory:", check_same_thread=False)
            _memory_conn.row_factory = sqlite3.Row
            _memory_conn.execute("PRAGMA foreign_keys = ON")
            _init_schema(_memory_conn)
        return _memory_conn

    # 檔案模式：共用單一連線（避免多連線 snapshot 不一致，見上方說明）。
    global _shared_conn
    if _shared_conn is None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        # isolation_level=None（autocommit）：SELECT 不會開啟並 pin 住持久讀交易，
        # 每個語句自動提交，避免單一長命連線一直讀到啟動當下的舊 snapshot
        # （警報已刪卻仍讀到即此問題）。明確的多步寫入交易由 transaction() 用 BEGIN 管理。
        conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        _shared_conn = conn
    return _shared_conn


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
    ("operators", "role_type", "TEXT"),          # ADR-116 營運角色 driver/stationed/controller
    ("operators", "stationed_at", "TEXT"),       # ADR-116 駐點人員駐守站(僅 stationed)
    ("vehicles", "is_depot", "INTEGER"),         # ADR-119 總站待命車(1=總站待命,可調派各區)
    ("tasks", "resources_released", "INTEGER DEFAULT 0"),
    ("tasks", "vehicle_return_status", "TEXT"),  # ADR-302 預備車結案恢復 standby
    ("vehicles", "onboard_bikes", "INTEGER"),        # ADR-123 車上現有台數（NULL=未知）
    ("vehicles", "onboard_source", "TEXT"),          # ADR-123 載量來源（可追溯）
    ("vehicles", "onboard_observed_at", "TEXT"),     # ADR-123 載量觀測時間
    ("tasks", "onboard_start", "INTEGER"),           # ADR-123 出車載量
    ("tasks", "onboard_planned_end", "INTEGER"),     # ADR-123 計畫收車載量
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
    # 共用單一連線：初始化後不關閉（後續請求沿用同一連線，確保 snapshot 一致）。
    _init_schema(get_connection())


def reset_memory_db() -> None:
    """測試用：清掉記憶體/檔案 DB 單例（下次 get_connection 會重建）。"""
    global _memory_conn, _shared_conn
    if _memory_conn is not None:
        _memory_conn.close()
        _memory_conn = None
    if _shared_conn is not None:
        _shared_conn.close()
        _shared_conn = None
