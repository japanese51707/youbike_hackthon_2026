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
    # ADR-313：顯示用清單讀背景預算快取（每 60 秒刷新一次全量），避免每次 request 重跑
    # 全站規則引擎/預測。切 limit / 篩 priority 在讀取端做。派工端口仍即時（_current_dispatch_list）。
    from core import dispatch_cache
    return dispatch_cache.get_recommendations(limit=limit, priority=priority)


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


def _attach_live_station_status(tasks: list[dict]) -> None:
    """ADR-329：把每個停靠站的「當下站況」補進任務路線（就地修改）。

    路線裡的 current_available 是**組單當下**的快照，不是現在。調度員盯著進行中任務
    要看的是「這站現在有幾台車、還有幾個空位、目標補到幾台」，三個數字缺一不可：
    只有目標看不出離目標多遠，只有現有看不出還塞不塞得下。

    站況來源不可用時靜默略過（維持原本快照），overview 不因此中斷。
    """
    if not tasks:
        return
    try:
        from core.donor_stations import get_all_stations
        live = {str(st.get("station_id")): st for st in get_all_stations()}
    except Exception:  # noqa: BLE001
        return
    if not live:
        return
    for task in tasks:
        for stop in task.get("route") or []:
            if not isinstance(stop, dict):
                continue
            st = live.get(str(stop.get("station_id")))
            if not st:
                continue
            stop["live_available_bikes"] = st.get("available_bikes")
            stop["live_available_docks"] = st.get("available_docks")
            stop["live_total_docks"] = st.get("total_docks")
            stop["live_observed_at"] = st.get("observed_at") or st.get("timestamp")

    # ADR-330：接空／滿站緊急時計（service_problems）——把「該站真正變空/滿的觸發時間」
    # 附到對應停靠站，讓進行中任務卡的站點旁能顯示「已緊急 X 分」（與任務起始時間不同：
    # 這是站況本身出事到現在多久，時鐘存後端 DB，前端只算差值，介面關掉後端仍持續計時）。
    try:
        from db import service_problems_repo
        open_by_station = {str(r.get("station_id")): r for r in service_problems_repo.list_open()}
    except Exception:  # noqa: BLE001
        open_by_station = {}
    if open_by_station:
        for task in tasks:
            for stop in task.get("route") or []:
                if not isinstance(stop, dict):
                    continue
                incident = open_by_station.get(str(stop.get("station_id")))
                if incident:
                    stop["problem_opened_at"] = incident.get("opened_at")  # 觸發時間戳（後端算）
                    stop["problem_kind"] = incident.get("kind")            # empty / full


@router.get("/dispatch/overview")
def overview():
    """3.17 全域調度總覽（後台/長官）"""
    from db import tasks_repo, operators_repo, vehicles_repo
    from api.operators import _apply_shift_duty
    rows = tasks_repo.list_tasks()
    _attach_live_station_status(rows)
    # ADR-312：operators 依當前班別注入在線狀態（當班未派工＝on_duty）。
    return {"tasks": rows, "operators": _apply_shift_duty(operators_repo.list_operators()),
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
        district=body.district, escort_id=body.escort_id,
        created_by=operator["operator_id"])


@router.post("/dispatch/build/from-station")
def build_from_station(body: BuildStationRequest,
                       operator: dict = Depends(require_role("dispatcher", "maintainer"))):
    """ADR-119 入口 b：以站為起點組草稿。body: {station_id, operator_id?, vehicle_id?}"""
    from core import dispatch_builder as db
    return _call(db.build_from_station,
        body.station_id, _current_dispatch_list(),
        operator_id=body.operator_id, vehicle_id=body.vehicle_id,
        escort_id=body.escort_id, created_by=operator["operator_id"])


@router.post("/dispatch/build/emergency")
def build_emergency(body: BuildEmergencyRequest,
                       operator: dict = Depends(require_role("dispatcher", "maintainer"))):
    """ADR-119 入口 c：緊急出車組草稿。body: {station_ids[], vehicle_id?, operator_id?}"""
    from core import dispatch_builder as db
    return _call(db.build_emergency,
        body.station_ids, _current_dispatch_list(),
        vehicle_id=body.vehicle_id, operator_id=body.operator_id,
        escort_id=body.escort_id, created_by=operator["operator_id"])


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


# ── ADR-320 自動配單後台開關（dispatcher/maintainer 可開關）──

@router.get("/dispatch/auto-dispatch")
def get_auto_dispatch_state():
    """回傳自動配單目前狀態（供調度決策儀表板顯示開關與倒數）。

    enabled：目前是否啟用（runtime 開關優先於 config 預設）。
    running：背景輪詢 thread 是否在跑（mock 源不啟）。
    interval_sec：輪詢間隔（對齊官方約 5 分更新）。
    next_run_at：下一輪預定執行時間（ISO/UTC，供前端倒數）。
    last_run_at / last_placed_count：上一輪執行時間與落地張數。
    """
    from core import auto_dispatch
    return auto_dispatch.run_status()


@router.post("/dispatch/auto-dispatch")
def set_auto_dispatch_state(
    body: dict = Body(...),
    operator: dict = Depends(require_role("dispatcher", "maintainer")),
):
    """後台開關自動配單（即時生效，不必重啟服務）。body: {enabled: bool}。需 dispatcher/maintainer。"""
    from core import auto_dispatch
    from core.audit import get_audit_service
    if "enabled" not in body or not isinstance(body["enabled"], bool):
        raise HTTPException(status_code=422, detail="需提供布林值 enabled")
    enabled = auto_dispatch.set_enabled(body["enabled"])
    get_audit_service().record(
        type="param_edit", operator=operator["operator_id"],
        action=f"{'開啟' if enabled else '關閉'}自動配單")
    return {"enabled": enabled}


@router.post("/dispatch/auto-dispatch/run-now")
def run_auto_dispatch_now(
    operator: dict = Depends(require_role("dispatcher", "maintainer")),
):
    """後台手動立即執行一輪自動配單（看得到結果），並重設下一輪倒數。需 dispatcher/maintainer。

    回 {placed_count, placed[], enabled}。若開關為關則回 placed_count=0（不強制配單）。
    """
    from core import auto_dispatch
    from core.audit import get_audit_service
    result = auto_dispatch.run_now()
    get_audit_service().record(
        type="param_edit", operator=operator["operator_id"],
        action=f"手動觸發自動配單一輪（落地 {result['placed_count']} 張）")
    return result
