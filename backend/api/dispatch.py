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
def confirm(
    recommendation_ids: list[str] = Body(..., embed=True),
    operator: dict = Depends(require_role("dispatcher", "maintainer")),
):
    """3.4 確認派發（★人在迴圈唯一閘門，需 dispatcher/maintainer）"""
    return get_mock()["tasks"]  # A0：回 mock 任務


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


@router.post("/dispatch/tasks/{task_id}/report")
def report(task_id: str, body: dict = Body(...), operator: dict = Depends(get_operator)):
    """3.6/3.13 回報任務 + 取下一任務（依位置）。只能回報自己的任務。"""
    # A0 骨架：實際「只能回報自己任務」的驗證在 A2 接 task_manager 後補
    return {
        "next_task": get_mock()["tasks"][0],
        "assignment_reason": "mock：距您最近的最優先站已安排",
    }


@router.get("/dispatch/overview")
def overview():
    """3.17 全域調度總覽（後台/長官）"""
    return get_mock()["dispatch_overview"]


# ── ADR-119 互動式派工單組建（三入口 + 確認）──

def _current_dispatch_list():
    """當前需調度清單（供組單三入口共用）：站點現況 → 規則引擎 → 排序建議。"""
    stations = get_stations_with_degradation()
    overrides = get_override_service().active_station_ids()
    return build_dispatch_list(stations, override_station_ids=overrides)


@router.post("/dispatch/build/from-vehicle")
def build_from_vehicle(body: dict = Body(...)):
    """ADR-119 入口 a：以車為起點組草稿。body: {vehicle_id, operator_id, district?}"""
    from core import dispatch_builder as db
    if not body.get("vehicle_id") or not body.get("operator_id"):
        raise HTTPException(status_code=400, detail="需 vehicle_id 與 operator_id")
    return db.build_from_vehicle(
        body["vehicle_id"], body["operator_id"], _current_dispatch_list(),
        district=body.get("district"))


@router.post("/dispatch/build/from-station")
def build_from_station(body: dict = Body(...)):
    """ADR-119 入口 b：以站為起點組草稿。body: {station_id, operator_id?, vehicle_id?}"""
    from core import dispatch_builder as db
    if not body.get("station_id"):
        raise HTTPException(status_code=400, detail="需 station_id")
    return db.build_from_station(
        body["station_id"], _current_dispatch_list(),
        operator_id=body.get("operator_id"), vehicle_id=body.get("vehicle_id"))


@router.post("/dispatch/build/emergency")
def build_emergency(body: dict = Body(...)):
    """ADR-119 入口 c：緊急出車組草稿。body: {station_ids[], vehicle_id?, operator_id?}"""
    from core import dispatch_builder as db
    if not body.get("station_ids"):
        raise HTTPException(status_code=400, detail="需 station_ids（陣列）")
    return db.build_emergency(
        body["station_ids"], _current_dispatch_list(),
        vehicle_id=body.get("vehicle_id"), operator_id=body.get("operator_id"))


@router.post("/dispatch/confirm-trip")
def confirm_trip(
    body: dict = Body(...),
    operator: dict = Depends(require_role("dispatcher", "maintainer")),
):
    """ADR-119 確認派工單落地（★人在迴圈閘門，需 dispatcher/maintainer）。body: {draft}"""
    from core import dispatch_builder as db
    draft = body.get("draft")
    if not draft:
        raise HTTPException(status_code=400, detail="需 draft（來自 build 端點的草稿）")
    try:
        return db.confirm_trip(draft, operator=operator["operator_id"])
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
