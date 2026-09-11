"""
站點參數 + 版本資料存取（db.params_repo）
==========================================
station_params 表：主鍵 (station_id, version)，保留所有版本供回溯（FR-7 ②）。
一個站同時只有一個 is_active=1 的版本 = 當前生效版本。

param_source 只有 base / ai_optimized（③覆寫不寫參數，見 model_architecture）。
override_active 是「該站目前有無生效中③覆寫」的狀態旗標，不是參數來源。
"""

from __future__ import annotations
import datetime as _dt
import json
from typing import Optional

from db.connection import commit, get_connection


def _now() -> str:
    return _dt.datetime.now().isoformat(timespec="seconds")


def _from_row(row) -> dict:
    d = dict(row)
    d["params"] = json.loads(d.pop("params_json", "{}") or "{}")
    d["conditions"] = json.loads(d.pop("conditions_json", "[]") or "[]")
    d["override_active"] = bool(d["override_active"])
    d["is_active"] = bool(d["is_active"])
    return d


def save_version(
    station_id: str,
    params: dict,
    param_source: str,
    conditions: Optional[list] = None,
    reason: Optional[str] = None,
    make_active: bool = True,
) -> dict:
    """存一個新參數版本。make_active=True 時把該站舊的生效版本取消、這版設為生效。

    版本號用時間戳（含微秒避免同秒碰撞）。
    """
    conn = get_connection()
    version = _dt.datetime.now().strftime("%Y%m%dT%H%M%S%f")
    if make_active:
        conn.execute(
            "UPDATE station_params SET is_active = 0 WHERE station_id = ? AND is_active = 1",
            (station_id,))
    conn.execute(
        """INSERT INTO station_params
           (station_id, version, params_json, param_source, override_active, conditions_json, reason, created_at, is_active)
           VALUES (?, ?, ?, ?, 0, ?, ?, ?, ?)""",
        (station_id, version, json.dumps(params, ensure_ascii=False), param_source,
         json.dumps(conditions or [], ensure_ascii=False), reason, _now(),
         1 if make_active else 0),
    )
    commit(conn)
    return get_version(station_id, version)


def get_active(station_id: str) -> Optional[dict]:
    """該站當前生效版本。"""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM station_params WHERE station_id = ? AND is_active = 1",
        (station_id,)).fetchone()
    return _from_row(row) if row else None


def get_active_many(station_ids) -> dict:
    """ADR-124：一次取回多站的生效版本，避免逐站查詢。

    SQLite 的變數上限是 999，所以分批帶入；回傳 {station_id: 版本 dict}，查不到的站不會出現。
    """
    ids = [str(sid) for sid in dict.fromkeys(station_ids) if sid is not None and str(sid) != ""]
    if not ids:
        return {}
    conn = get_connection()
    out: dict = {}
    for start in range(0, len(ids), 900):
        batch = ids[start:start + 900]
        placeholders = ",".join("?" for _ in batch)
        rows = conn.execute(
            f"SELECT * FROM station_params WHERE is_active = 1 AND station_id IN ({placeholders})",
            batch).fetchall()
        for row in rows:
            record = _from_row(row)
            out[str(record["station_id"])] = record
    return out


def get_version(station_id: str, version: str) -> Optional[dict]:
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM station_params WHERE station_id = ? AND version = ?",
        (station_id, version)).fetchone()
    return _from_row(row) if row else None


def list_versions(station_id: str) -> list[dict]:
    """該站所有版本（新到舊），供回溯歷史檢視。"""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM station_params WHERE station_id = ? ORDER BY version DESC",
        (station_id,)).fetchall()
    return [_from_row(r) for r in rows]


def activate_version(station_id: str, version: str) -> Optional[dict]:
    """把指定版本設為當前生效（回溯用）。找不到該版本回 None。"""
    conn = get_connection()
    target = conn.execute(
        "SELECT 1 FROM station_params WHERE station_id = ? AND version = ?",
        (station_id, version)).fetchone()
    if target is None:
        return None
    conn.execute(
        "UPDATE station_params SET is_active = 0 WHERE station_id = ? AND is_active = 1",
        (station_id,))
    conn.execute(
        "UPDATE station_params SET is_active = 1 WHERE station_id = ? AND version = ?",
        (station_id, version))
    commit(conn)
    return get_active(station_id)


def set_override_active(station_id: str, active: bool) -> None:
    """更新該站生效版本的 override_active 旗標（③覆寫狀態，非參數來源）。"""
    conn = get_connection()
    conn.execute(
        "UPDATE station_params SET override_active = ? WHERE station_id = ? AND is_active = 1",
        (1 if active else 0, station_id))
    commit(conn)
