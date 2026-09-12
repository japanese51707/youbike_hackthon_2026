"""警示端點（3.11）。★題目要求：現行系統無警示。接 alert_service。"""

from fastapi import APIRouter, Body, HTTPException, Depends
from auth import require_role
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
    svc = get_alert_service()
    stations = get_stations_with_degradation()
    recs = build_dispatch_list(stations)
    svc.generate_from_stations(stations, recs)
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
    from core import escalation
    from core.task_manager import get_task_manager
    stations = get_stations_with_degradation()
    recs = build_dispatch_list(stations)
    tasks = get_task_manager().list_tasks()
    return escalation.sync_cases(stations, recs, tasks)


@router.get("/alerts/escalations")
def escalations():
    """ADR-309：未結案的緊急調度案件（含階段、已等待分鐘、下一階段時間）。

    查詢時順帶同步開案／關案，與現行警示同樣沒有常駐排程。
    時間一律後端換算，前端不自己累加（重整、換機器、多人同時看要一致）。
    """
    cases = _sync_escalations()
    return {
        "cases": cases,
        "counts": {
            "open": len(cases),
            "banner": sum(1 for c in cases if c["should_banner"]),
            "prompt": sum(1 for c in cases if c["should_prompt"]),
        },
    }


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
