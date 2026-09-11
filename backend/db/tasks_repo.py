"""
任務資料存取（db.tasks_repo）
==============================
tasks 表的 CRUD。取代 TaskManager 的記憶體 dict。
route 等複雜結構以 JSON 字串存 route_json；讀出時還原。
"""

from __future__ import annotations
import datetime as _dt
import json
from typing import Optional

from db.connection import get_connection, commit

# 存進 DB 的欄位（其餘非欄位的鍵會塞進 route_json 之外忽略）
_COLUMNS = [
    "task_id", "task_type", "task_status", "assigned_operator",
    "estimated_travel_minutes", "estimated_work_minutes", "estimated_total_minutes",
    "estimated_distance_km", "estimated_fuel_cost", "route_map_url",
    "source_override_station_id", "cancel_reason", "cancelled_by", "assigned_at",
    "district", "assigned_vehicle", "vehicle_return_status", "resources_released",   # ADR-114：這趟任務的行政區 + 指派的調度車
    "onboard_start", "onboard_planned_end",   # ADR-123 車上載量（出車／計畫收車）
]


def _now() -> str:
    return _dt.datetime.now().isoformat(timespec="seconds")


def _to_row(task: dict) -> dict:
    row = {c: task.get(c) for c in _COLUMNS}
    row["route_json"] = json.dumps(task.get("route", []), ensure_ascii=False)
    return row


def _from_row(row) -> dict:
    d = dict(row)
    d["route"] = json.loads(d.pop("route_json", "[]") or "[]")
    # 移除純 DB 欄位，保留對外一致的鍵
    d.pop("created_at", None)
    d.pop("updated_at", None)
    return d


def insert(task: dict) -> None:
    conn = get_connection()
    row = _to_row(task)
    now = _now()
    row["created_at"] = now
    row["updated_at"] = now
    cols = list(row.keys())
    placeholders = ", ".join(f":{c}" for c in cols)
    conn.execute(
        f"INSERT INTO tasks ({', '.join(cols)}) VALUES ({placeholders})", row)
    commit(conn)


def update(task: dict) -> None:
    """整筆更新（task_manager 改狀態後回寫）。"""
    conn = get_connection()
    row = _to_row(task)
    row["updated_at"] = _now()
    sets = ", ".join(f"{c} = :{c}" for c in row if c != "task_id")
    conn.execute(f"UPDATE tasks SET {sets} WHERE task_id = :task_id", row)
    commit(conn)


def get(task_id: str) -> Optional[dict]:
    conn = get_connection()
    row = conn.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
    return _from_row(row) if row else None


def exists(task_id: str) -> bool:
    conn = get_connection()
    return conn.execute("SELECT 1 FROM tasks WHERE task_id = ?", (task_id,)).fetchone() is not None


def list_tasks(status: Optional[str] = None, operator: Optional[str] = None) -> list[dict]:
    conn = get_connection()
    sql = "SELECT * FROM tasks WHERE 1=1"
    params: list = []
    if status:
        sql += " AND task_status = ?"; params.append(status)
    if operator:
        sql += " AND assigned_operator = ?"; params.append(operator)
    return [_from_row(r) for r in conn.execute(sql, params).fetchall()]


def find_by_override_source(station_id: str, statuses: list[str]) -> list[dict]:
    conn = get_connection()
    q = ",".join("?" * len(statuses))
    rows = conn.execute(
        f"SELECT * FROM tasks WHERE source_override_station_id = ? AND task_status IN ({q})",
        [station_id, *statuses]).fetchall()
    return [_from_row(r) for r in rows]


def not_completed() -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM tasks WHERE task_status NOT IN ('completed', 'cancelled')").fetchall()
    return [_from_row(r) for r in rows]
