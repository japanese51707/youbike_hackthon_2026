"""
調度端點（3.3~3.6, 3.13, 3.17）
含全域總覽 overview（不在 operators）。confirm 需 dispatcher 權限（C-08）。
"""

from fastapi import APIRouter, Depends, Body, HTTPException
from mock_store import get_mock
from auth import get_operator, require_role
from core import build_dispatch_list
from core.data import get_stations_with_degradation
from core.override_service import get_override_service
from core.dispatch_errors import DispatchConflict, DispatchForbidden
from core.task_manager import IllegalTransition
from models_schema.task_execution import StationReportRequest, TaskReturnRequest
from models_schema.dispatch_requests import (
    BuildVehicleRequest, BuildStationRequest, BuildEmergencyRequest,
    ConfirmReference, ConfirmDraft, AddStationRequest,
)


def _call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except DispatchForbidden as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except (DispatchConflict, IllegalTransition) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _confirm_body(body, operator):
    from core import dispatch_builder
    data = body.model_dump()
    return _call(dispatch_builder.confirm_trip, data.get("draft", data), operator["operator_id"])


router = APIRouter(prefix="/api/v1", tags=["dispatch"])


@router.get("/dispatch/recommendations")
def recommendations(limit: int = 15, priority: str | None = None):
    """3.3 調度建議清單（已排序）

    走規則引擎：取 data_source 的站點狀態 → rule_engine 觸發判斷 →
    dispatcher 排序（覆寫最前綴）+ 緊急度分級 + 資源限制。
    預測目前用 mock predictor（A6 換 B 的 LightGBM）。
    """
    stations = get_stations_with_degradation()
    overrides = get_override_service().active_station_ids()
    recs = build_dispatch_list(stations, override_station_ids=overrides)
    if priority:
        recs = [r for r in recs if r["priority_level"] == priority]
    return recs[:limit]


@router.post("/dispatch/confirm")
def confirm(body: ConfirmReference | ConfirmDraft,
            operator: dict = Depends(require_role("dispatcher", "maintainer"))):
    """ADR-302：與 confirm-trip 同一契約，不再回 mock 成功。"""
    return _confirm_body(body, operator)


@router.get("/dispatch/tasks")
def tasks(status: str | None = None, operator: str | None = None):
    """3.5 任務清單（接 task_manager，可篩 status/operator）"""
    from core.task_manager import get_task_manager
    return get_task_manager().list_tasks(status=status, operator=operator)


@router.get("/dispatch/tasks/{task_id}")
def task_detail(task_id: str):
    """3.5 單一任務詳情（含站級 route）"""
    from core.task_manager import get_task_manager
    t = get_task_manager().get(task_id)
    if t is None:
        raise HTTPException(status_code=404, detail=f"找不到任務 {task_id}")
    return t


@router.post("/dispatch/tasks/{task_id}/start")
def start(task_id: str, operator: dict = Depends(get_operator)):
    from core import task_execution as tx
    return _call(tx.start_task, task_id, operator["operator_id"])


@router.post("/dispatch/tasks/{task_id}/report")
def report(task_id: str, body: StationReportRequest,
           operator: dict = Depends(get_operator)):
    from core import task_execution as tx
    return _call(tx.report_station, task_id, body.station_id, body.actual_available,
                 operator["operator_id"])


@router.delete("/dispatch/tasks/{task_id}/stations/{station_id}")
def remove_station(task_id: str, station_id: str, reason: str = "",
                   operator: dict = Depends(require_role("dispatcher", "maintainer"))):
    from core import task_execution as tx
    return _call(tx.remove_station, task_id, station_id, operator["operator_id"], reason)


@router.post("/dispatch/tasks/{task_id}/stations")
def add_station(task_id: str, body: AddStationRequest,
                operator: dict = Depends(require_role("dispatcher", "maintainer"))):
    from core import task_execution as tx
    submitted = body.station or {"station_id": body.station_id}
    sid = submitted.get("station_id") if isinstance(submitted, dict) else None
    # 站點指令來自後端當前建議，客戶端只能選 ID，不能夾帶目標或完成狀態。
    station = next((r for r in _current_dispatch_list() if r["station_id"] == sid), None)
    if station is None:
        raise HTTPException(status_code=409, detail="站點不在目前需調度清單，請重新預覽")
    return _call(tx.add_station, task_id, station, operator["operator_id"], body.reason)


@router.post("/dispatch/tasks/{task_id}/return")
def return_task(task_id: str, body: TaskReturnRequest,
                operator: dict = Depends(get_operator)):
    from core import task_execution as tx
    return _call(tx.cancel_by_executor, task_id, operator["operator_id"], body.reason)


@router.get("/dispatch/claim-map")
def claim_map(district: str | None = None):
    """ADR-119 站點認領地圖：哪些站已被某任務認領（防重複接/漏做）。"""
    from core import task_execution as tx
    return tx.station_claim_map(district=district)


@router.get("/dispatch/overview")
def overview():
    """3.17 全域調度總覽（後台/長官）"""
    from db import tasks_repo, operators_repo, vehicles_repo
    rows = tasks_repo.list_tasks()
    return {"tasks": rows, "operators": operators_repo.list_operators(),
            "vehicles": vehicles_repo.list_vehicles(),
            "task_counts": {status: sum(t["task_status"] == status for t in rows)
                            for status in ("assigned", "in_progress", "completed", "cancelled", "manual_required")},
            "source": "backend"}


# ── ADR-119 互動式派工單組建（三入口 + 確認）──

def _current_dispatch_list():
    """當前需調度清單（供組單三入口共用）：站點現況 → 規則引擎 → 排序建議。"""
    stations = get_stations_with_degradation()
    overrides = get_override_service().active_station_ids()
    recs = build_dispatch_list(stations, override_station_ids=overrides)
    by_id = {str(s["station_id"]): s for s in stations}
    for rec in recs:
        st = by_id.get(str(rec["station_id"]), {})
        for key in ("total_docks", "service_available", "status"):
            if key in st:
                rec[key] = st[key]
    return recs


@router.post("/dispatch/build/from-vehicle")
def build_from_vehicle(body: BuildVehicleRequest,
                       operator: dict = Depends(require_role("dispatcher", "maintainer"))):
    """ADR-119 入口 a：以車為起點組草稿。body: {vehicle_id, operator_id, district?}"""
    from core import dispatch_builder as db
    return _call(db.build_from_vehicle,
        body.vehicle_id, body.operator_id, _current_dispatch_list(),
        district=body.district, created_by=operator["operator_id"])


@router.post("/dispatch/build/from-station")
def build_from_station(body: BuildStationRequest,
                       operator: dict = Depends(require_role("dispatcher", "maintainer"))):
    """ADR-119 入口 b：以站為起點組草稿。body: {station_id, operator_id?, vehicle_id?}"""
    from core import dispatch_builder as db
    return _call(db.build_from_station,
        body.station_id, _current_dispatch_list(),
        operator_id=body.operator_id, vehicle_id=body.vehicle_id,
        created_by=operator["operator_id"])


@router.post("/dispatch/build/emergency")
def build_emergency(body: BuildEmergencyRequest,
                       operator: dict = Depends(require_role("dispatcher", "maintainer"))):
    """ADR-119 入口 c：緊急出車組草稿。body: {station_ids[], vehicle_id?, operator_id?}"""
    from core import dispatch_builder as db
    return _call(db.build_emergency,
        body.station_ids, _current_dispatch_list(),
        vehicle_id=body.vehicle_id, operator_id=body.operator_id,
        created_by=operator["operator_id"])


@router.get("/dispatch/next-trip")
def next_trip(vehicle_id: str, top_k: int = 10):
    """ADR-117 離峰滾動：車完成任務後，依車當前位置給下一趟建議（緊急度-距離評分，非自動派）。"""
    from core.dispatcher import suggest_next_trip
    return suggest_next_trip(vehicle_id, _current_dispatch_list(), top_k=top_k)


@router.post("/dispatch/confirm-trip")
def confirm_trip(
    body: ConfirmReference | ConfirmDraft,
    operator: dict = Depends(require_role("dispatcher", "maintainer")),
):
    """ADR-302：body 為 {draft_id, version} 或未修改的 {draft}。"""
    return _confirm_body(body, operator)
