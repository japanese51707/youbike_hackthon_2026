"""調度員 + 車隊端點（3.16, ADR-114/116/119）。接 operators_repo / vehicles_repo。"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, ConfigDict
from typing import Literal
from auth import get_operator

router = APIRouter(prefix="/api/v1", tags=["operators"])


def _apply_shift_duty(operators: list[dict]) -> list[dict]:
    """ADR-312：依當前班別注入「在線狀態」（呈現層，不改 DB 真實 status）。

    規則（只影響未派工的人；已派工 busy 者維持真實狀態不動）：
      - 已派工（有 current_task_id）→ 維持原 status（任務中 busy）。
      - 當班（shift == 現在班別）且未派工 → on_duty（上班中・閒置待命）。
      - 總部預備（depot_standby，不綁班別）且未派工 → on_duty（隨時機動支援）。
      - 其餘（非當班、未派工）→ off_duty（未上班）。
    這樣「現在這個時段誰在線可調度」隨時段自動反映，不必背景改 DB。
    """
    from core.shift import current_shift
    now_shift = current_shift()
    out = []
    for o in operators:
        oo = dict(o)
        if oo.get("current_task_id"):
            pass  # 派工中：真實狀態（busy）不動
        elif oo.get("role_type") == "depot_standby":
            oo["status"] = "on_duty"
        elif oo.get("shift") and oo.get("shift") == now_shift:
            oo["status"] = "on_duty"
        else:
            oo["status"] = "off_duty"
        out.append(oo)
    return out


@router.get("/operators")
def list_operators(role_type: str | None = None, active_only: bool = True):
    """3.16 調度員清單（接 operators_repo）。可篩營運角色 role_type（driver/stationed/controller/depot_standby）。

    ADR-312：回傳依當前班別注入在線狀態（當班且未派工＝on_duty 閒置待命；非當班＝off_duty）。
    """
    from db import operators_repo as repo
    if role_type:
        return _apply_shift_duty(repo.list_by_role_type(role_type, active_only=active_only))
    return _apply_shift_duty(repo.list_operators(active_only=active_only))


class DutyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["on_duty", "off_duty"]


@router.post("/operators/me/duty")
def update_my_duty(body: DutyRequest, operator: dict = Depends(get_operator)):
    from core.operator_duty import set_duty
    from api.dispatch import _call
    return _call(set_duty, operator["operator_id"], body.status)


@router.get("/operators/{operator_id}")
def operator_detail(operator_id: str):
    """3.16 單一調度員"""
    from db import operators_repo as repo
    o = repo.get_operator(operator_id)
    if o is None:
        raise HTTPException(status_code=404, detail="查無此調度員")
    return o


@router.get("/vehicles")
def list_vehicles(status: str | None = None, active_only: bool = True):
    """ADR-114 車隊清單（接 vehicles_repo）。含 max_capacity/status/is_depot/current_district。"""
    from db import vehicles_repo as repo
    return repo.list_vehicles(status=status, active_only=active_only)


@router.get("/vehicles/standby")
def standby_vehicles():
    """ADR-118 待命車：預備車（保留率 standby）+ 總站待命車（is_depot），供緊急/支援調度。"""
    from db import vehicles_repo as repo
    return {"reserve_standby": repo.list_standby(), "depot_standby": repo.list_depot_standby()}


@router.get("/vehicles/{vehicle_id}")
def vehicle_detail(vehicle_id: str):
    """ADR-114 單一調度車"""
    from db import vehicles_repo as repo
    v = repo.get_vehicle(vehicle_id)
    if v is None:
        raise HTTPException(status_code=404, detail="查無此調度車")
    return v


class OnboardReport(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    onboard_bikes: int
    source: Literal["manual_report", "fleet_api"] = "manual_report"


@router.post("/vehicles/{vehicle_id}/onboard")
def report_vehicle_onboard(vehicle_id: str, body: OnboardReport,
                           operator: dict = Depends(get_operator)):
    """ADR-123：回報調度車目前車上台數（可追溯：值 + 來源 + 觀測時間）。

    授權：dispatcher／maintainer 可回報任何車；driver／depot_standby 只能回報自己任務的車。
    未回報或回報過期的車，確認派工會被擋（不假設車上為零）。
    """
    from db import vehicles_repo as repo
    vehicle = repo.get_vehicle(vehicle_id)
    if vehicle is None:
        raise HTTPException(status_code=404, detail="查無此調度車")
    if operator.get("role") not in {"dispatcher", "maintainer"}:
        # get_operator 只回 {operator_id, role}；營運角色與當前任務要查主檔。
        from db import operators_repo
        record = operators_repo.get_operator(operator["operator_id"]) or {}
        if (record.get("role_type") not in {"driver", "depot_standby"}
                or vehicle.get("current_task_id") is None
                or vehicle.get("current_task_id") != record.get("current_task_id")):
            raise HTTPException(status_code=403, detail="只能回報自己任務中的調度車")
    try:
        updated = repo.report_onboard(vehicle_id, body.onboard_bikes, body.source)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    from core.audit import get_audit_service
    get_audit_service().record(
        type="task_report", operator=operator["operator_id"],
        action=f"回報車輛 {vehicle_id} 車上 {body.onboard_bikes} 台（{body.source}）")
    return updated


@router.get("/operators/{operator_id}/stream")
def operator_stream(operator_id: str):
    """NFR-9 只推該調度員工作範圍內的即時更新（A0 骨架，之後改 SSE）"""
    return {"message": "mock：SSE 串流端點，A2/A3 實作", "operator_id": operator_id}
