"""
調度車主檔資料存取（db.vehicles_repo）— ADR-114
================================================
vehicles 表的 CRUD。比照 operators_repo 結構。

職責：只做「資料存取」，不做業務邏輯（指派/切趟在 dispatcher）。
載運量（max_capacity）逐台可不同、可改（車種差異）；current_district 為動態狀態
（隨每次任務指派變動，非綁定責任區）。停用取代刪除，保留稽核關聯。

對外暴露：
    create_vehicle(...)        # 建車
    get_vehicle(id)            # 查單一
    list_vehicles(...)         # 列出（可篩狀態/啟用）
    update_vehicle(id, **kw)   # 改欄位（載運量/狀態/current_district 等）
    set_status(id, status)     # 改狀態捷徑
    assign_district(id, d, task_id)  # 指派時回寫當前作業區 + 任務
    clear_assignment(id)       # 任務結束清空 current_district/task
    deactivate(id)             # 停用（不刪除）
    seed_default_vehicles(n)   # 種入 n 台預設車（ADR-114：41 台 × 載運量 15）
"""

from __future__ import annotations
import datetime as _dt
from typing import Optional

from db.connection import get_connection

_VALID_STATUS = {"available", "dispatched", "maintenance", "off_duty", "standby"}
# 可由 update_vehicle 更新的欄位（白名單，避免任意欄位注入）
_UPDATABLE = {"max_capacity", "status", "current_district", "current_task_id", "is_active"}


def _now() -> str:
    return _dt.datetime.now().isoformat(timespec="seconds")


def _row_to_public(row) -> dict:
    d = dict(row)
    d["is_active"] = bool(d.get("is_active", 1))
    return d


def create_vehicle(
    vehicle_id: str,
    max_capacity: int = 15,
    status: str = "available",
) -> dict:
    """建立調度車。max_capacity 預設 15（ADR-114，依車種可改）。"""
    if status not in _VALID_STATUS:
        raise ValueError(f"未知狀態 '{status}'（合法：{sorted(_VALID_STATUS)}）")
    if int(max_capacity) <= 0:
        raise ValueError("max_capacity 必須為正整數")
    conn = get_connection()
    existing = conn.execute(
        "SELECT 1 FROM vehicles WHERE vehicle_id = ?", (vehicle_id,)).fetchone()
    if existing:
        raise ValueError(f"調度車 {vehicle_id} 已存在")
    now = _now()
    conn.execute(
        """INSERT INTO vehicles
           (vehicle_id, max_capacity, status, current_district, current_task_id,
            is_active, created_at, updated_at)
           VALUES (?, ?, ?, NULL, NULL, 1, ?, ?)""",
        (vehicle_id, int(max_capacity), status, now, now),
    )
    conn.commit()
    return get_vehicle(vehicle_id)


def get_vehicle(vehicle_id: str) -> Optional[dict]:
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM vehicles WHERE vehicle_id = ?", (vehicle_id,)).fetchone()
    return _row_to_public(row) if row else None


def list_vehicles(status: Optional[str] = None, active_only: bool = False) -> list[dict]:
    conn = get_connection()
    sql = "SELECT * FROM vehicles WHERE 1=1"
    params: list = []
    if active_only:
        sql += " AND is_active = 1"
    if status:
        sql += " AND status = ?"
        params.append(status)
    return [_row_to_public(r) for r in conn.execute(sql, params).fetchall()]


def update_vehicle(vehicle_id: str, **fields) -> Optional[dict]:
    """更新白名單欄位（載運量/狀態/current_district/current_task_id/is_active）。"""
    updates = {k: v for k, v in fields.items() if k in _UPDATABLE}
    if not updates:
        return get_vehicle(vehicle_id)
    if "status" in updates and updates["status"] not in _VALID_STATUS:
        raise ValueError(f"未知狀態 '{updates['status']}'（合法：{sorted(_VALID_STATUS)}）")
    if "max_capacity" in updates and int(updates["max_capacity"]) <= 0:
        raise ValueError("max_capacity 必須為正整數")
    conn = get_connection()
    updates["updated_at"] = _now()
    sets = ", ".join(f"{c} = ?" for c in updates)
    conn.execute(
        f"UPDATE vehicles SET {sets} WHERE vehicle_id = ?",
        [*updates.values(), vehicle_id])
    conn.commit()
    return get_vehicle(vehicle_id)


def set_status(vehicle_id: str, status: str) -> Optional[dict]:
    return update_vehicle(vehicle_id, status=status)


def assign_district(vehicle_id: str, district: str, task_id: Optional[str] = None) -> Optional[dict]:
    """指派時回寫當前作業行政區 + 任務，狀態轉 dispatched（ADR-114 動態 current_district）。"""
    return update_vehicle(
        vehicle_id, current_district=district, current_task_id=task_id, status="dispatched")


def clear_assignment(vehicle_id: str) -> Optional[dict]:
    """任務結束：清空 current_district/current_task_id，狀態回 available。"""
    return update_vehicle(
        vehicle_id, current_district=None, current_task_id=None, status="available")


def deactivate(vehicle_id: str) -> bool:
    """停用調度車（不刪除，保留稽核關聯）。回傳是否有更新到。"""
    conn = get_connection()
    cur = conn.execute(
        "UPDATE vehicles SET is_active = 0, updated_at = ? WHERE vehicle_id = ?",
        (_now(), vehicle_id))
    conn.commit()
    return cur.rowcount > 0


def list_standby() -> list[dict]:
    """列出待命預備車（ADR-118：status=standby，不參與常態派單，緊急救火才動用）。"""
    return [v for v in list_vehicles(active_only=True) if v.get("status") == "standby"]


def set_reserve_fleet(reserve_ratio: float = 0.12) -> int:
    """ADR-118 車隊靜態保留率：把車隊末端一定比例的車標為 standby（不參與常態派單）。

    以 vehicle_id 排序取末段 ceil(總數×比例) 台設為 standby，其餘設回 available（冪等）。
    回傳設為 standby 的車數。
    """
    import math
    all_v = sorted(list_vehicles(active_only=True), key=lambda v: v["vehicle_id"])
    n_reserve = math.ceil(len(all_v) * reserve_ratio)
    reserve_ids = {v["vehicle_id"] for v in all_v[-n_reserve:]} if n_reserve > 0 else set()
    for v in all_v:
        want = "standby" if v["vehicle_id"] in reserve_ids else "available"
        # 只動 available/standby 的車，不覆蓋 dispatched/maintenance（正在用的不要亂改）
        if v.get("status") in ("available", "standby") and v.get("status") != want:
            update_vehicle(v["vehicle_id"], status=want)
    return len(reserve_ids)


def activate_reserve(vehicle_id: str, district: str, task_id: Optional[str] = None) -> Optional[dict]:
    """ADR-118 緊急救火：把待命預備車轉 active（dispatched）並指派到救火行政區。"""
    return assign_district(vehicle_id, district, task_id)


def seed_default_vehicles(n: int = 41, max_capacity: int = 15) -> None:
    """種入 n 台預設調度車（ADR-114：官方 41 台 × 載運量 15，平清單不分區）。已存在則跳過。

    seed 只是開發/demo 起始值；未來 YouBike 車隊 API 進來即以真實清單覆蓋。
    車號流水號 CAR-001 ~ CAR-0NN。current_district 留空（分區由任務指派動態決定）。
    """
    conn = get_connection()
    for i in range(1, n + 1):
        vid = f"CAR-{i:03d}"
        exists = conn.execute(
            "SELECT 1 FROM vehicles WHERE vehicle_id = ?", (vid,)).fetchone()
        if not exists:
            create_vehicle(vid, max_capacity=max_capacity, status="available")
