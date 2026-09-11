"""ADR-302：授權逐站回報、手動介入與結案，所有寫入共用交易。"""

from copy import deepcopy
from datetime import datetime, timezone
from typing import Optional

from db import tasks_repo, vehicles_repo
from db.connection import atomic
from core.dispatch_errors import DispatchConflict
from core.dispatch_guards import (
    inventory, require_executor, require_dispatcher, require_active,
    validate_stations,
)
from core.task_manager import get_task_manager


def _audit(action, station_id=None, operator="system", reason=None):
    from core.audit import get_audit_service
    get_audit_service().record(type="task_report", operator=operator, action=action,
                              station_id=station_id, reason=reason)


def _get_task(task_id):
    task = tasks_repo.get(task_id)
    if task is None:
        raise KeyError(f"找不到任務 {task_id}")
    return task


def _route(task):
    return [dict(s) if isinstance(s, dict) else
            {"station_id": str(s), "station_status": "pending"}
            for s in task.get("route", []) or []]


def _stop(route, station_id):
    found = next((s for s in route if str(s.get("station_id")) == str(station_id)), None)
    if found is None:
        raise KeyError(f"任務內找不到站點 {station_id}")
    if found.get("station_status", "pending") != "pending":
        raise DispatchConflict("已完成或移除的站點不可再次操作")
    return found


def _settle_onboard(task):
    """ADR-123：結案時由實際回報推算收車載量，寫回車輛（來源 task_completion）。

    推算：出車載量 + Σ(取車實際搬運) − Σ(補車實際搬運)。
    每站實際搬運由計畫量與 target_gap 還原：補車 = q − gap、取車 = q + gap。
    任一站缺必要數字，或出車載量本身未知 → 把車上載量標回「未知」，不寫入猜測值。
    """
    vehicle_id = task.get("assigned_vehicle")
    if not vehicle_id:
        return
    onboard = task.get("onboard_start")
    if onboard is None:
        vehicles_repo.clear_onboard(vehicle_id)
        return
    total = int(onboard)
    for stop in task.get("route", []) or []:
        if not isinstance(stop, dict):
            vehicles_repo.clear_onboard(vehicle_id)
            return
        status = stop.get("station_status", "pending")
        if status == "removed":
            continue          # 抽離的站沒有搬運，不影響載量
        planned = stop.get("est_quantity")
        gap = stop.get("target_gap")
        if status != "completed" or planned is None or gap is None:
            vehicles_repo.clear_onboard(vehicle_id)
            return
        moved = float(planned) + (float(gap) if stop.get("action") == "取車" else -float(gap))
        total += int(round(moved)) if stop.get("action") == "取車" else -int(round(moved))
    if total < 0:
        vehicles_repo.clear_onboard(vehicle_id)
        return
    capacity = (vehicles_repo.get_vehicle(vehicle_id) or {}).get("max_capacity")
    if capacity is not None and total > int(capacity):
        vehicles_repo.clear_onboard(vehicle_id)
        return
    vehicles_repo.report_onboard(vehicle_id, total, "task_completion")


def _finish_if_done(task):
    route = task["route"]
    remaining = sum(s.get("station_status", "pending") == "pending" for s in route)
    tasks_repo.update(task)
    if not remaining:
        tm = get_task_manager()
        if task["task_status"] == "assigned":
            tm.start(task["task_id"])
        _settle_onboard(task)          # 先在資源釋放前算定載量（ADR-123）
        tm.complete(task["task_id"])
    return remaining


@atomic
def start_task(task_id, operator):
    task = _get_task(task_id)
    require_executor(task, operator)
    require_active(task)
    if task["task_status"] == "assigned":
        task = get_task_manager().start(task_id)
        _audit(f"開始任務 {task_id}", operator=operator)
    return {"task_id": task_id, "status": task["task_status"]}


@atomic
def report_station(task_id, station_id, actual_available, operator="system"):
    task = _get_task(task_id)
    require_executor(task, operator)
    require_active(task)
    route = _route(task)
    found = _stop(route, station_id)
    actual = inventory(actual_available, found.get("total_docks"))
    # 首次回報相容既有客戶端；在同一交易內完成 assigned → in_progress。
    if task["task_status"] == "assigned":
        task = get_task_manager().start(task_id)
        _audit(f"首次回報開始任務 {task_id}", operator=operator)
    found.update(station_status="completed", actual_available=actual, claimed_by=None,
                 reported_at=datetime.now(timezone.utc).isoformat(), reported_by=operator)
    target = found.get("target_available")
    gap = round(target - actual, 1) if target is not None else None
    if gap is not None:
        found["target_gap"] = gap
    task["route"] = route
    remaining = _finish_if_done(task)
    _audit(f"逐站回報 {station_id} 實際存量={actual}，剩餘 {remaining} 站",
           station_id=station_id, operator=operator)
    if not remaining:
        _audit(f"全部站點完成，任務 {task_id} 結案並釋放資源", operator=operator)
    return {"station": found, "gap": gap, "all_done": remaining == 0, "remaining": remaining,
            "status": "completed" if remaining == 0 else "in_progress"}


def remove_station(task_id, station_id, operator, reason=""):
    # 來源讀取可能等待外部網路，不能在 SQLite 寫入交易內阻塞其他派工。
    require_dispatcher(operator)
    task = _get_task(task_id)
    require_active(task)
    _stop(_route(task), station_id)
    resolved = _demand_resolved(station_id)
    return _remove_station(task_id, station_id, operator, reason, resolved)


@atomic
def _remove_station(task_id, station_id, operator, reason, resolved):
    require_dispatcher(operator)
    task = _get_task(task_id)
    require_active(task)
    route = _route(task)
    target = _stop(route, station_id)
    target.update(station_status="removed", removed_by=operator, removed_reason=reason,
                  claimed_by=None, removed_resolved=resolved)
    task["route"] = route
    remaining = _finish_if_done(task)
    _audit(f"後台抽離站點 {station_id}，剩餘 {remaining} 站", station_id, operator, reason)
    return {"station": target, "resolved": resolved, "back_to_pool": not resolved,
            "needs_notify": True, "all_done": remaining == 0}


def _onboard_at_stop(task, pending):
    """剩餘路線的起始車上載量：最後一個已完成站的 onboard_after，否則回出車載量。

    兩者都沒有時回 None（未知），由可行性評估標記為載量未知，不假設為零。
    """
    done = [s for s in task.get("route", []) or []
            if isinstance(s, dict) and s.get("station_status") == "completed"
            and s.get("onboard_after") is not None]
    if done:
        return done[-1]["onboard_after"]
    return task.get("onboard_start")


@atomic
def add_station(task_id, station, operator, reason=""):
    require_dispatcher(operator)
    task = _get_task(task_id)
    require_active(task)
    route = _route(task)
    station = deepcopy(station)
    sid = str(station.get("station_id") or "")
    if any(str(s.get("station_id")) == sid for s in route):
        raise DispatchConflict(f"站點 {sid} 已在任務內")
    vehicle = vehicles_repo.get_vehicle(task.get("assigned_vehicle"))
    if vehicle is None:
        raise DispatchConflict("任務缺少車輛資料，請人工處理")
    pending = [s for s in route if s.get("station_status", "pending") == "pending"]
    validate_stations(pending + [station], vehicle["max_capacity"], exclude=task_id)
    # ADR-123/304：加站後整條剩餘路線仍須通過同一份可行性評估（載量守恆／逐站視野）
    from core.dispatch_feasibility import evaluate_feasibility, first_blocking_message
    remaining_plan = evaluate_feasibility(
        pending + [station],
        {**vehicle, "onboard_bikes": _onboard_at_stop(task, pending)},
        None, mode=task.get("task_type"), check_resources=False)
    blocked = first_blocking_message(remaining_plan)
    if blocked:
        raise DispatchConflict(blocked)
    station.update(station_status="pending", claimed_by=task["assigned_operator"], added_by=operator)
    route.append(station)
    task["route"] = route
    tasks_repo.update(task)
    _audit(f"後台增加站點 {sid} 到任務 {task_id}", sid, operator, reason)
    return {"station": station, "needs_notify": True}


@atomic
def cancel_by_executor(task_id, operator, reason):
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("取消/退回任務必須說明原因")
    task = _get_task(task_id)
    require_executor(task, operator)
    require_active(task)
    tm = get_task_manager()
    if task["task_status"] == "in_progress":
        task = tm.fail(task_id, retryable=False)
        task.update(cancel_reason=reason.strip(), cancelled_by=operator)
    else:
        task = tm.cancel(task_id, reason.strip(), operator)
    from db.task_resources_repo import release
    release(task)
    task["resources_released"] = 1
    route = _route(task)
    for stop in route:
        stop["claimed_by"] = None
    task["route"] = route
    tasks_repo.update(task)
    _audit(f"執行者退回任務 {task_id}，釋放認領及人車", operator=operator, reason=reason.strip())
    return {"task_id": task_id, "released": True, "reason": reason.strip(),
            "status": task["task_status"]}


def station_claim_map(district: Optional[str] = None):
    claimed = {}
    for task in get_task_manager().pending_or_active():
        if task.get("resources_released"):
            continue
        for stop in _route(task):
            if stop.get("station_status", "pending") != "pending":
                continue
            if district and stop.get("district") != district:
                continue
            claimed[str(stop.get("station_id"))] = {
                "claimed_by": stop.get("claimed_by") or task.get("assigned_operator"),
                "task_id": task["task_id"], "action": stop.get("action"),
                "target_available": stop.get("target_available"),
            }
    return claimed


def _demand_resolved(station_id: str) -> bool:
    """偵測站點當下是否已無調度需求（抽離時判定「任務是否已完成」）。

    用即時資料源拿當下站況 + 規則引擎判斷：evaluate_station 回 None = 不需調度 = 需求已消化。
    無法取得站況時保守回 False（當作需求仍在，回池重排，不誤判為完成）。
    """
    try:
        from core.data.data_source import get_data_source
        from core.rule_engine import evaluate_station
        st = get_data_source().get_station(str(station_id))
        if st is None:
            return False
        rec = evaluate_station(st, prediction=None)   # 無預測走降級門檻判斷當下是否還危險
        return rec is None   # None = 不需調度 = 需求已消化
    except Exception:
        return False
