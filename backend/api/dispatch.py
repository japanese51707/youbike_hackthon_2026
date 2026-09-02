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
def tasks():
    """3.5 任務清單"""
    return get_mock()["tasks"]


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
