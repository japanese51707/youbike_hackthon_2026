"""KPI + 模擬重放端點（3.7, 3.8）。KPI 接真實即時統計；replay 仍 mock。"""

from fastapi import APIRouter
from mock_store import get_mock
from core.data import get_stations_with_degradation

router = APIRouter(prefix="/api/v1", tags=["kpi"])


@router.get("/kpi")
def kpi():
    """3.7 KPI 指標（接真實站點即時統計）：全市健康度、空/滿站數、平均借用率。"""
    stations = get_stations_with_degradation()
    total = len(stations)
    empty = sum(1 for s in stations if s.get("status") == "empty")
    full = sum(1 for s in stations if s.get("status") == "full")
    healthy = total - empty - full
    avg_usage = round(sum(float(s.get("usage_rate", 0) or 0) for s in stations) / total, 1) if total else 0
    return {
        "total_stations": total,
        "empty_stations": empty,
        "full_stations": full,
        "healthy_stations": healthy,
        "health_rate_pct": round(healthy / total * 100, 1) if total else 0,
        "avg_usage_rate": avg_usage,
        "source": "realtime",
    }


@router.get("/simulation/replay")
def replay(date: str = "2026-06-02"):
    """3.8 模擬重放 Before/After（Demo 成效）"""
    return get_mock()["simulation_replay"]
