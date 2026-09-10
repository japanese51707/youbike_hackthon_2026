"""
任務執行閉環（core.task_execution）— ADR-117
=============================================
逐站完成回報、站點認領標註、後台手動介入（抽離/增加站、取消/退回）。
是「系統給建議、人拍板」定位的執行層：任務指派後，現場逐站回報實際狀況，
後台可緊急介入個別站，認領狀態全程可見（防重複接/漏做）。

職責（單一）：只做「任務內站點層級的執行操作」。
不做：任務狀態機（在 task_manager）、產生建議（在 dispatcher）、觸發判斷（在 rule_engine）。

站點以 route（list[dict]）存於 task 的 route_json，每站含：
  station_id / station_name / district / action / target_available（目標存量，主指令）
  / est_quantity（預估增減量，輔助）/ station_status（pending/completed/removed）
  / claimed_by（認領人=任務的 assigned_operator）/ actual_available（回報實際存量）

對外暴露：
    report_station(task_id, station_id, actual_available, operator)   # 逐站完成回報
    remove_station(task_id, station_id, operator, reason)             # 後台抽離個別站
    add_station(task_id, station_dict, operator, reason)              # 後台增加個別站
    cancel_by_executor(task_id, operator, reason)                     # 執行者取消/退回(附原因)
    station_claim_map(district=None)                                  # 站點認領狀態(前端地圖用)
"""

from __future__ import annotations
import datetime as _dt
from typing import Optional

from config_loader import get_config


def _now() -> str:
    return _dt.datetime.now().isoformat(timespec="seconds")


def _audit(action, station_id=None, operator="system", reason=None):
    from core.audit import get_audit_service
    get_audit_service().record(
        type="task_report", operator=operator, action=action,
        station_id=station_id, reason=reason)


def _get_task(task_id: str) -> dict:
    from db import tasks_repo
    task = tasks_repo.get(task_id)
    if task is None:
        raise KeyError(f"找不到任務 {task_id}")
    return task


def _route(task: dict) -> list:
    """取任務的站點清單（route）。若為舊格式（純 ID 字串），升級為站物件。"""
    route = task.get("route", []) or []
    upgraded = []
    for item in route:
        if isinstance(item, dict):
            upgraded.append(item)
        else:  # 舊格式：純 station_id
            upgraded.append({"station_id": str(item), "station_status": "pending"})
    return upgraded


def _save_route(task: dict, route: list) -> None:
    from db import tasks_repo
    task["route"] = route
    tasks_repo.update(task)


def report_station(
    task_id: str, station_id: str, actual_available: float, operator: str = "system",
) -> dict:
    """逐站完成回報（ADR-117）：現場人員輸入「該站實際存量」，非「做了多少」。

    - 標記該站 station_status=completed、寫入 actual_available。
    - 記錄「目標 vs 實際」落差（供日後校準，本階段只記錄，不自動回饋）。
    - 若所有站皆 completed/removed → 任務可視為完成（回報告知，實際狀態轉換由 task_manager）。
    回傳：{ station, 落差 gap, all_done, remaining }
    """
    task = _get_task(task_id)
    route = _route(task)
    target = None
    found = None
    for s in route:
        if str(s.get("station_id")) == str(station_id):
            s["station_status"] = "completed"
            s["actual_available"] = float(actual_available)
            s["reported_at"] = _now()
            target = s.get("target_available")
            found = s
            break
    if found is None:
        raise KeyError(f"任務 {task_id} 內找不到站點 {station_id}")

    # 目標 vs 實際落差（目標存量 − 實際到場存量）
    gap = None
    if target is not None:
        gap = round(float(target) - float(actual_available), 1)
        found["target_gap"] = gap

    _save_route(task, route)
    _audit(action=f"逐站回報 {station_id} 實際存量={actual_available:.0f}"
           + (f"（目標{target:.0f}，落差{gap:+.1f}）" if gap is not None else ""),
           station_id=station_id, operator=operator)

    active = [s for s in route if s.get("station_status") == "pending"]
    return {
        "station": found, "gap": gap,
        "all_done": len(active) == 0,
        "remaining": len(active),
    }


def remove_station(
    task_id: str, station_id: str, operator: str, reason: str = "",
) -> dict:
    """後台抽離任務內個別站（ADR-117，緊急用）。

    - 抽離時偵測該站當下狀況：需求已消失（不缺不滿）→ 視為已完成、不回池；
      需求仍在 → 清除認領標註、回待調度池（供他人重排）。
    - 必通知現場（走 alert/通知，這裡記錄 needs_notify 供上層發通知）。
    - 留痕。
    回傳：{ station, resolved（是否已消化）, back_to_pool, needs_notify }
    """
    task = _get_task(task_id)
    route = _route(task)
    target = None
    for s in route:
        if str(s.get("station_id")) == str(station_id):
            target = s
            break
    if target is None:
        raise KeyError(f"任務 {task_id} 內找不到站點 {station_id}")

    resolved = _demand_resolved(station_id)
    target["station_status"] = "removed"
    target["removed_by"] = operator
    target["removed_reason"] = reason
    target["claimed_by"] = None   # 清除認領標註
    target["removed_resolved"] = resolved
    _save_route(task, route)

    _audit(action=f"後台抽離站點 {station_id}（{'需求已消化,視為完成' if resolved else '需求仍在,回待調度池'}）",
           station_id=station_id, operator=operator, reason=reason)

    return {
        "station": target,
        "resolved": resolved,
        "back_to_pool": not resolved,   # 需求還在才回池重排
        "needs_notify": True,           # 必通知現場（ADR-117）
    }


def add_station(
    task_id: str, station: dict, operator: str, reason: str = "",
) -> dict:
    """後台增加個別站到任務（ADR-117，緊急用）。必通知現場 + 留痕。"""
    task = _get_task(task_id)
    route = _route(task)
    sid = str(station.get("station_id"))
    if any(str(s.get("station_id")) == sid for s in route):
        raise ValueError(f"站點 {sid} 已在任務 {task_id} 內")
    station.setdefault("station_status", "pending")
    station["claimed_by"] = task.get("assigned_operator")   # 認領標註
    station["added_by"] = operator
    route.append(station)
    _save_route(task, route)
    _audit(action=f"後台增加站點 {sid} 到任務 {task_id}",
           station_id=sid, operator=operator, reason=reason)
    return {"station": station, "needs_notify": True}


def cancel_by_executor(task_id: str, operator: str, reason: str) -> dict:
    """執行者取消/退回整張任務（ADR-117）：須說明原因；使任務脫離 in_progress，後台可重排。

    透過 task_manager.cancel（會擋非法狀態）；清除所有未完成站的認領標註。
    """
    if not reason:
        raise ValueError("取消/退回任務必須說明原因（ADR-117）")
    from core.task_manager import get_task_manager
    tm = get_task_manager()
    # task_manager.cancel 允許 pending/assigned/in_progress？既有規則 in_progress 不可 cancel，
    # 但「執行者退回」是合法脫離路徑：用 fail→manual_required 或直接 cancel 視狀態。
    task = _get_task(task_id)
    status = task.get("task_status")
    if status == "in_progress":
        # 執行者退回：in_progress → manual_required（脫離執行中，後台重排）
        tm.fail(task_id, retryable=False)
    result = tm.cancel(task_id, reason=reason, operator=operator) if status != "in_progress" \
        else _get_task(task_id)
    # 清除未完成站的認領標註
    route = _route(task if status == "in_progress" else result)
    for s in route:
        if s.get("station_status") == "pending":
            s["claimed_by"] = None
    t = _get_task(task_id)
    _save_route(t, route)
    _audit(action=f"執行者退回/取消任務 {task_id}", operator=operator, reason=reason)
    return {"task_id": task_id, "released": True, "reason": reason}


def station_claim_map(district: Optional[str] = None) -> dict:
    """回傳站點認領狀態（前端地圖用）：哪些站已被某任務認領、哪些待接。

    掃所有未完成任務的 route，蒐集 pending 站的認領人。
    """
    from core.task_manager import get_task_manager
    tm = get_task_manager()
    claimed = {}
    for task in tm.pending_or_active():
        for s in _route(task):
            if s.get("station_status") != "pending":
                continue
            if district and s.get("district") != district:
                continue
            claimed[str(s.get("station_id"))] = {
                "claimed_by": s.get("claimed_by") or task.get("assigned_operator"),
                "task_id": task.get("task_id"),
                "action": s.get("action"),
                "target_available": s.get("target_available"),
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
