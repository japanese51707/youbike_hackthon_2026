"""
調度員 / 帳號資料存取（db.operators_repo）
============================================
operators 表的 CRUD + 帳號驗證。密碼一律經 core.security 雜湊後才存。

職責：只做「資料存取」，不做權限判斷（權限在 auth.py）、不做業務邏輯。

對外暴露：
    create_operator(...)      # 建帳號（密碼雜湊後存）
    get_operator(id)          # 查單一（不含密碼雜湊，避免外洩）
    get_role(id)              # 查角色（auth 用；停用帳號回 None）
    verify_login(id, pw)      # 登入驗證（比對 bcrypt）
    list_operators()          # 列出（不含密碼雜湊）
    deactivate(id)            # 停用（不刪除，保留稽核關聯）
    seed_default_operators()  # 種入 3 個預設帳號（開發/Demo 用）
"""

from __future__ import annotations
import datetime as _dt
from typing import Optional

from db.connection import get_connection, commit
from core.security import hash_password, verify_password

_VALID_ROLES = {"operator", "dispatcher", "maintainer"}


def _now() -> str:
    return _dt.datetime.now().isoformat(timespec="seconds")


def _row_to_public(row) -> dict:
    """轉成對外 dict，刻意排除 password_hash（不外洩）。"""
    d = dict(row)
    d.pop("password_hash", None)
    d["is_active"] = bool(d.get("is_active", 1))
    return d


# ADR-116 營運角色 + ADR-119 depot_standby（總站待命人力，獨立資源類別，可調派各區）
_VALID_ROLE_TYPES = {"driver", "stationed", "controller", "depot_standby"}


def create_operator(
    operator_id: str,
    name: str,
    role: str,
    password: Optional[str] = None,
    role_type: Optional[str] = None,
    stationed_at: Optional[str] = None,
) -> dict:
    """建立帳號。role 需合法；密碼（若給）經 bcrypt 雜湊後才存。

    role_type（ADR-116 營運角色 driver/stationed/controller）與 role（登入權限）正交。
    stationed_at 僅 role_type=stationed 時有意義（駐守站）。
    """
    if role not in _VALID_ROLES:
        raise ValueError(f"未知角色 '{role}'（合法：{sorted(_VALID_ROLES)}）")
    if role_type is not None and role_type not in _VALID_ROLE_TYPES:
        raise ValueError(f"未知營運角色 '{role_type}'（合法：{sorted(_VALID_ROLE_TYPES)}）")
    conn = get_connection()
    existing = conn.execute(
        "SELECT 1 FROM operators WHERE operator_id = ?", (operator_id,)).fetchone()
    if existing:
        raise ValueError(f"帳號 {operator_id} 已存在")

    pw_hash = hash_password(password) if password else None
    now = _now()
    conn.execute(
        """INSERT INTO operators
           (operator_id, name, role, password_hash, status, is_active,
            role_type, stationed_at, created_at, updated_at)
           VALUES (?, ?, ?, ?, 'off_duty', 1, ?, ?, ?, ?)""",
        (operator_id, name, role, pw_hash, role_type, stationed_at, now, now),
    )
    commit(conn)
    return get_operator(operator_id)


def get_operator(operator_id: str) -> Optional[dict]:
    """查單一帳號（不含密碼雜湊）。找不到回 None。"""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM operators WHERE operator_id = ?", (operator_id,)).fetchone()
    return _row_to_public(row) if row else None


def get_role(operator_id: str) -> Optional[str]:
    """查角色（auth 用）。帳號不存在或已停用回 None。"""
    conn = get_connection()
    row = conn.execute(
        "SELECT role, is_active FROM operators WHERE operator_id = ?",
        (operator_id,)).fetchone()
    if row is None or not row["is_active"]:
        return None
    return row["role"]


def verify_login(operator_id: str, password: str) -> Optional[dict]:
    """登入驗證：帳號存在、啟用中、密碼正確才回帳號 dict，否則 None。"""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM operators WHERE operator_id = ?", (operator_id,)).fetchone()
    if row is None or not row["is_active"]:
        return None
    if not verify_password(password, row["password_hash"]):
        return None
    return _row_to_public(row)


def list_operators(active_only: bool = False) -> list[dict]:
    conn = get_connection()
    sql = "SELECT * FROM operators"
    if active_only:
        sql += " WHERE is_active = 1"
    return [_row_to_public(r) for r in conn.execute(sql).fetchall()]


def deactivate(operator_id: str) -> bool:
    """停用帳號（不刪除，保留稽核關聯）。回傳是否有更新到。"""
    conn = get_connection()
    cur = conn.execute(
        "UPDATE operators SET is_active = 0, updated_at = ? WHERE operator_id = ?",
        (_now(), operator_id))
    commit(conn)
    return cur.rowcount > 0


def set_password(operator_id: str, password: str) -> bool:
    """設定/重設密碼（雜湊後存）。回傳是否有更新到。"""
    conn = get_connection()
    cur = conn.execute(
        "UPDATE operators SET password_hash = ?, updated_at = ? WHERE operator_id = ?",
        (hash_password(password), _now(), operator_id))
    commit(conn)
    return cur.rowcount > 0


# ── ADR-114：動態 current_district（隨任務指派變動，非綁定責任區）──
def assign_district(operator_id: str, district: str, task_id: Optional[str] = None) -> bool:
    """指派時回寫調度員當前作業行政區（+任務），狀態轉 busy。回傳是否有更新到。"""
    conn = get_connection()
    cur = conn.execute(
        """UPDATE operators SET current_district = ?, current_task_id = ?,
           status = 'busy', updated_at = ? WHERE operator_id = ?""",
        (district, task_id, _now(), operator_id))
    commit(conn)
    return cur.rowcount > 0


def clear_assignment(operator_id: str) -> bool:
    """任務結束：清空 current_district/current_task_id，狀態回 on_duty。回傳是否有更新到。"""
    conn = get_connection()
    cur = conn.execute(
        """UPDATE operators SET current_district = NULL, current_task_id = NULL,
           status = 'on_duty', updated_at = ? WHERE operator_id = ?""",
        (_now(), operator_id))
    commit(conn)
    return cur.rowcount > 0


def update_status(operator_id: str, status: str) -> bool:
    conn = get_connection()
    cur = conn.execute("UPDATE operators SET status = ?, updated_at = ? WHERE operator_id = ?",
                       (status, _now(), operator_id))
    commit(conn)
    return cur.rowcount > 0


def set_stationed_at(operator_id: str, station_id: Optional[str]) -> bool:
    """設定駐點人員駐守站（ADR-116；station_id=None 表示解除駐守）。回傳是否有更新到。"""
    conn = get_connection()
    cur = conn.execute(
        "UPDATE operators SET stationed_at = ?, updated_at = ? WHERE operator_id = ?",
        (station_id, _now(), operator_id))
    commit(conn)
    return cur.rowcount > 0


def list_by_role_type(role_type: str, active_only: bool = True) -> list[dict]:
    """依營運角色列出（ADR-116：driver/stationed/controller）。"""
    conn = get_connection()
    sql = "SELECT * FROM operators WHERE role_type = ?"
    params: list = [role_type]
    if active_only:
        sql += " AND is_active = 1"
    return [_row_to_public(r) for r in conn.execute(sql, params).fetchall()]


def seed_default_operators() -> None:
    """種入 3 個預設帳號（開發/Demo 用）。已存在則跳過。

    取代 auth.py 原本寫死的測試帳號。預設密碼供 Demo 登入，正式應改。
    OP-001~003 為具名登入帳號（有角色/密碼）；大量調度員清單見 seed_dispatch_operators()。
    """
    defaults = [
        ("OP-001", "王小明", "operator", "youbike-op"),
        ("OP-002", "李主任", "dispatcher", "youbike-dp"),
        ("OP-003", "陳工程師", "maintainer", "youbike-mt"),
    ]
    conn = get_connection()
    for oid, name, role, pw in defaults:
        exists = conn.execute(
            "SELECT 1 FROM operators WHERE operator_id = ?", (oid,)).fetchone()
        if not exists:
            create_operator(oid, name, role, pw)


def seed_dispatch_operators(total: int = 350) -> None:
    """種入調度車人員清單（ADR-114/116：官方 350 名，純流水號無真名，role_type=driver）。已存在則跳過。

    OP-001~003 由 seed_default_operators() 建為具名登入帳號；本函式補到 total 名
    （OP-004 ~ OP-{total}），role=operator、role_type=driver、無密碼（純調度人力，非登入帳號）。
    name 用流水號字串（無真實人名）。seed 只是開發/demo 起始值，未來由 YouBike 人力 API 覆蓋。
    """
    conn = get_connection()
    for i in range(1, total + 1):
        oid = f"OP-{i:03d}"
        exists = conn.execute(
            "SELECT 1 FROM operators WHERE operator_id = ?", (oid,)).fetchone()
        if not exists:
            # 純流水號調度車人員（無真名、無密碼、無登入權限），僅供調度指派用
            create_operator(oid, name=oid, role="operator", password=None, role_type="driver")


def seed_depot_standby_operators(total: int = 10) -> None:
    """種入總站待命人力（ADR-119：DEP-001~0NN，role_type=depot_standby，可調派各區）。已存在則跳過。

    總站待命為獨立資源類別（非一般 driver），供派工單三入口在「該區無閒置人力」時調派支援。
    """
    conn = get_connection()
    for i in range(1, total + 1):
        oid = f"DEP-{i:03d}"
        exists = conn.execute(
            "SELECT 1 FROM operators WHERE operator_id = ?", (oid,)).fetchone()
        if not exists:
            create_operator(oid, name=oid, role="operator", password=None,
                            role_type="depot_standby")


def seed_stationed_operators(total: int = 30) -> None:
    """種入駐點人員清單（ADR-116：守熱門站現場調節，role_type=stationed）。已存在則跳過。

    ST-001 ~ ST-{total}，純流水號、無真名無密碼。stationed_at（駐守站）先留空，
    由後台指派或後續依 dispatch_ops_analysis 的駐點候選站分配。
    """
    conn = get_connection()
    for i in range(1, total + 1):
        oid = f"ST-{i:03d}"
        exists = conn.execute(
            "SELECT 1 FROM operators WHERE operator_id = ?", (oid,)).fetchone()
        if not exists:
            create_operator(oid, name=oid, role="operator", password=None, role_type="stationed")
