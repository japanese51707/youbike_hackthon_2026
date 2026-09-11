"""派工共用的身分、資源占用與站點檢查（ADR-302）。"""

import math

from db import operators_repo, tasks_repo, vehicles_repo
from core.dispatch_errors import DispatchConflict, DispatchForbidden


def require_dispatcher(operator):
    if operators_repo.get_role(operator) not in {"dispatcher", "maintainer"}:
        raise DispatchForbidden("此操作需要 dispatcher 或 maintainer 權限")


def require_executor(task, operator):
    if operators_repo.get_role(operator) is None or task.get("assigned_operator") != operator:
        raise DispatchForbidden("只能操作指派給自己的任務")


def require_active(task):
    if task.get("task_status") not in {"assigned", "in_progress"} or task.get("resources_released"):
        raise DispatchConflict("任務目前狀態不允許此操作")


def inventory(value, capacity=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("實際存量必須為非負整數")
    if not math.isfinite(value) or value < 0 or int(value) != value:
        raise ValueError("實際存量必須為非負整數")
    if capacity is not None and value > capacity:
        raise ValueError("實際存量不可超過站點容量")
    return int(value)


def occupied_tasks(exclude=None):
    return [t for t in tasks_repo.not_completed()
            if t["task_id"] != exclude and not t.get("resources_released")]


def ensure_unclaimed(station_ids, exclude=None):
    for task in occupied_tasks(exclude):
        for stop in task.get("route", []):
            sid = stop.get("station_id") if isinstance(stop, dict) else stop
            status = stop.get("station_status", "pending") if isinstance(stop, dict) else "pending"
            if str(sid) in station_ids and status == "pending":
                raise DispatchConflict(f"站點 {sid} 已被任務 {task['task_id']} 認領")


def validate_resources(trip, exclude=None):
    vehicle = vehicles_repo.get_vehicle(trip.get("assigned_vehicle"))
    operator = operators_repo.get_operator(trip.get("assigned_operator"))
    allowed_vehicle = {"available", "standby"} if trip.get("mode") == "emergency" else {"available"}
    if not vehicle or not vehicle["is_active"] or vehicle["status"] not in allowed_vehicle:
        raise DispatchConflict("車輛不存在、停用或目前不可派遣")
    if vehicle.get("current_task_id") not in (None, exclude):
        raise DispatchConflict("車輛已有任務")
    if (not operator or not operator["is_active"] or operator.get("status") != "on_duty"
            or operator.get("role_type") not in {"driver", "depot_standby"}):
        raise DispatchConflict("人員不存在、停用、未值勤或不具調度車執行角色")
    if operator.get("current_task_id") not in (None, exclude):
        raise DispatchConflict("人員已有任務")
    for task in occupied_tasks(exclude):
        if (task.get("assigned_vehicle") == vehicle["vehicle_id"]
                or task.get("assigned_operator") == operator["operator_id"]):
            raise DispatchConflict("人車已被其他未結束任務占用")
    return vehicle, operator


def validate_stations(stations, capacity, exclude=None):
    if not stations:
        raise ValueError("空任務不可派遣")
    ids = [str(s.get("station_id") or "") for s in stations]
    if not all(ids) or len(ids) != len(set(ids)):
        raise ValueError("站點 ID 不可空白或重複")
    total = 0
    for s in stations:
        if s.get("action") not in {"補車", "取車"}:
            raise ValueError("站點動作必須為補車或取車")
        total += inventory(s.get("quantity", s.get("est_quantity")))
        if s.get("target_available") is not None:
            inventory(s["target_available"], s.get("total_docks"))
        if s.get("service_available") is False or s.get("status") == "offline":
            raise DispatchConflict("停用站點不可派遣")
    if total > capacity:
        raise DispatchConflict("派工數量超過車輛容量，請重新預覽")
    ensure_unclaimed(set(ids), exclude)
