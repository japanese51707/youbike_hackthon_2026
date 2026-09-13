"""警示端點（3.11）。★題目要求：現行系統無警示。接 alert_service。"""

import datetime as _dt
from fastapi import APIRouter, Body, HTTPException, Depends
from auth import get_operator, require_role
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal


class EmergencyCheckRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    in_transit_eta_min: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    persist: Literal[False] = False

from core.alert_service import get_alert_service
from core.data import get_stations_with_degradation
from core import build_dispatch_list

router = APIRouter(prefix="/api/v1", tags=["alerts"])


@router.get("/alerts")
def list_alerts(level: str | None = None, acknowledged: bool | None = None):
    """3.11 取得警示

    即時掃描站點 + 調度建議產生警示（分級 info/warning/critical），再依條件篩選。
    """
    # ADR-313：讀背景預算快取的站況 + 需調度清單（避免每次重跑全站規則引擎/預測）。
    from core import dispatch_cache
    snap = dispatch_cache.get_snapshot()
    svc = get_alert_service()
    svc.generate_from_stations(snap["stations"], snap["recs"])
    return svc.list_alerts(level=level, acknowledged=acknowledged)


@router.post("/alerts/{alert_id}/acknowledge")
def acknowledge(alert_id: str):
    """3.11 確認警示已讀"""
    a = get_alert_service().acknowledge(alert_id)
    if a is None:
        raise HTTPException(status_code=404, detail=f"找不到警示 {alert_id}")
    return {"message": f"警示 {alert_id} 已標記為已讀", "alert": a}


@router.post("/alerts/subscribe")
def subscribe(body: dict = Body(...)):
    """3.11 機關訂閱警示 webhook（出向資安：callback 須 https 且非內網）"""
    try:
        sub = get_alert_service().subscribe(
            callback_url=body["callback_url"],
            levels=body.get("levels", ["warning", "critical"]),
            districts=body.get("districts", []),
            token=body.get("token"),
        )
    except (KeyError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"message": "已登記 webhook 訂閱", **sub}


@router.get("/alerts/stream")
def alert_stream():
    """3.11 前端即時警示串流（骨架：回傳待推佇列。正式改 SSE EventSource）"""
    return {"events": get_alert_service().drain_sse()}


# ── ADR-118 死結警報 / 緊急救火 ──

@router.get("/emergency/deadlocks")
def deadlocks():
    """ADR-118 偵測各行政區死結大站（≥門檻 個大站連續滿/空）。"""
    from core import emergency
    stations = get_stations_with_degradation()
    return emergency.detect_deadlocks(stations)


@router.post("/emergency/check")
def emergency_check(body: EmergencyCheckRequest = Body(default_factory=EmergencyCheckRequest),
                    operator: dict = Depends(require_role("dispatcher", "maintainer"))):
    """ADR-302：只回偵測與建議，不修改派工、人車或警報資料。"""
    from core import emergency
    stations = get_stations_with_degradation()
    return emergency.check_and_dispatch_reserve(
        stations, in_transit_eta_min=body.in_transit_eta_min)


# ── ADR-309 緊急調度案件升級追蹤 ──

class CaseActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    note: str = Field(default="", max_length=500)
    contact: str = Field(default="", max_length=120)


def _sync_escalations():
    # ADR-313：讀背景預算快取的站況 + 需調度清單。
    from core import escalation, dispatch_cache
    from core.task_manager import get_task_manager
    snap = dispatch_cache.get_snapshot()
    tasks = get_task_manager().list_tasks()
    return escalation.sync_cases(snap["stations"], snap["recs"], tasks)


def _controller_ids() -> list:
    """管理端收件者：dispatcher／maintainer 角色的啟用帳號。"""
    from db import operators_repo
    out = []
    for row in operators_repo.list_operators(active_only=True):
        if row.get("role") in ("dispatcher", "maintainer"):
            out.append(row["operator_id"])
    return out


@router.get("/alerts/escalations")
def escalations():
    """ADR-335：未結案的緊急調度案件（含階段、已持續分鐘、承辦責任、觀測新鮮度）。

    案件只在「新鮮觀測確認解除」時關閉——派工不關案，所以這裡回的是
    「問題還沒解除」的清單，不是「還沒派工」的清單。
    同步時一併產生該輪的分級提醒（冪等，重複查詢不會重複送）。
    """
    from core import notification_service
    cases = _sync_escalations()
    try:
        notification_service.sync_notifications(cases, _controller_ids())
    except Exception:  # noqa: BLE001 - 提醒寫入失敗不該讓案件清單掛掉
        pass
    return {
        "cases": cases,
        "server_now": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "counts": {
            "open": len(cases),
            "banner": sum(1 for c in cases if c["should_banner"]),
            "prompt": sum(1 for c in cases if c["should_prompt"]),
            "unassigned": sum(1 for c in cases
                              if c.get("responsibility_status") == "unassigned"),
            "unverified": sum(1 for c in cases
                              if c.get("observation_status") == "unverified"),
        },
    }


# ── ADR-335 站內通知：每人只看得到／只能標記自己的 ──────────────────
@router.get("/alerts/notifications")
def my_notifications(include_resolved: bool = False,
                     operator: dict = Depends(get_operator)):
    """我的提醒。司機只拿得到自己的；管理端拿到自己身分收到的那些。"""
    from db import notifications_repo
    rows = notifications_repo.list_for_recipient(
        operator["operator_id"], include_resolved=include_resolved)
    stamp = _dt.datetime.now(_dt.timezone.utc).isoformat()
    for row in rows:
        if not row.get("delivered_at"):
            notifications_repo.mark(row["notification_id"], "delivered_at", stamp,
                                    recipient_id=operator["operator_id"])
            row["delivered_at"] = stamp
    return {"notifications": rows, "server_now": stamp}


@router.post("/alerts/notifications/{notification_id}/{action}")
def notification_action(notification_id: str, action: str,
                        operator: dict = Depends(get_operator)):
    """標記自己的提醒：seen／ack／mute。

    ★一個人已讀不會替另一端消音（ADR-335）：通知是每人一筆，
      這裡只會動到呼叫者自己那一筆。靜音也不遮清單、不擋下一階段。
    """
    from core import notification_service
    from db import notifications_repo
    stamp = _dt.datetime.now(_dt.timezone.utc)
    iso = stamp.isoformat()
    if action == "seen":
        row = notifications_repo.mark(notification_id, "seen_at", iso,
                                      recipient_id=operator["operator_id"])
    elif action == "ack":
        row = notifications_repo.mark(notification_id, "acknowledged_at", iso,
                                      recipient_id=operator["operator_id"])
    elif action == "mute":
        minutes = notification_service.settings()["mute_minutes"]
        until = (stamp + _dt.timedelta(minutes=minutes)).isoformat()
        notifications_repo.mute(notification_id, until, operator["operator_id"])
        row = notifications_repo.find_by_id(notification_id)
    else:
        raise HTTPException(status_code=400, detail="action 必須是 seen／ack／mute")
    if row is None:
        raise HTTPException(status_code=404, detail="查無此提醒或不屬於你")
    return row


@router.get("/alerts/escalations/history")
def escalation_history(limit: int = 100):
    """管理後台稽核用：含已關閉案件與所有人為動作。"""
    from db import escalation_repo
    cases = escalation_repo.list_cases(limit=limit)
    by_case = {}
    for action in escalation_repo.list_actions(limit=limit * 4):
        by_case.setdefault(action["case_id"], []).append(action)
    for case in cases:
        case["actions"] = by_case.get(case["case_id"], [])
    return cases


@router.post("/alerts/escalations/{case_id}/{action}")
def escalation_action(case_id: str, action: str,
                      body: CaseActionRequest = Body(default_factory=CaseActionRequest),
                      operator: dict = Depends(require_role("dispatcher", "maintainer"))):
    """記錄人為動作。★不關案——關案只認派工或站況恢復（ADR-309 §2）。"""
    from core import escalation
    try:
        return escalation.record_action(
            case_id, action, operator["operator_id"],
            note=body.note, contact=body.contact)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
