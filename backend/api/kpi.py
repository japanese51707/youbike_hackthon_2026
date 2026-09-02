"""KPI + 模擬重放端點（3.7, 3.8）。A0 回 mock。"""

from fastapi import APIRouter
from mock_store import get_mock

router = APIRouter(prefix="/api/v1", tags=["kpi"])


@router.get("/kpi")
def kpi():
    """3.7 KPI 指標"""
    return get_mock()["kpi"]


@router.get("/simulation/replay")
def replay(date: str = "2026-06-02"):
    """3.8 模擬重放 Before/After（Demo 成效）"""
    return get_mock()["simulation_replay"]
