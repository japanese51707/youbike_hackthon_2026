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

from db.connection import get_connection
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


def create_operator(
    operator_id: str,
    name: str,
    role: str,
    password: Optional[str] = None,
) -> dict:
    """建立帳號。role 需合法；密碼（若給）經 bcrypt 雜湊後才存。"""
    if role not in _VALID_ROLES:
        raise ValueError(f"未知角色 '{role}'（合法：{sorted(_VALID_ROLES)}）")
    conn = get_connection()
    existing = conn.execute(
        "SELECT 1 FROM operators WHERE operator_id = ?", (operator_id,)).fetchone()
    if existing:
        raise ValueError(f"帳號 {operator_id} 已存在")

    pw_hash = hash_password(password) if password else None
    now = _now()
    conn.execute(
        """INSERT INTO operators
           (operator_id, name, role, password_hash, status, is_active, created_at, updated_at)
           VALUES (?, ?, ?, ?, 'off_duty', 1, ?, ?)""",
        (operator_id, name, role, pw_hash, now, now),
    )
    conn.commit()
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
    conn.commit()
    return cur.rowcount > 0


def set_password(operator_id: str, password: str) -> bool:
    """設定/重設密碼（雜湊後存）。回傳是否有更新到。"""
    conn = get_connection()
    cur = conn.execute(
        "UPDATE operators SET password_hash = ?, updated_at = ? WHERE operator_id = ?",
        (hash_password(password), _now(), operator_id))
    conn.commit()
    return cur.rowcount > 0


def seed_default_operators() -> None:
    """種入 3 個預設帳號（開發/Demo 用）。已存在則跳過。

    取代 auth.py 原本寫死的測試帳號。預設密碼供 Demo 登入，正式應改。
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
