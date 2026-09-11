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
    offline = sum(1 for s in stations if s.get("status") == "offline")
    # 健康率以「營運中站」為分母（排除故障站，才不會被離線站拉低失真）
    in_service = total - offline
    healthy = in_service - empty - full
    usable = [s for s in stations if s.get("status") != "offline"]
    avg_usage = (round(sum(float(s.get("usage_rate", 0) or 0) for s in usable) / len(usable), 1)
                 if usable else 0)
    return {
        "total_stations": total,
        "in_service_stations": in_service,
        "offline_stations": offline,      # 故障/未啟用（可借與可還同時 0）
        "empty_stations": empty,
        "full_stations": full,
        "healthy_stations": healthy,
        "health_rate_pct": round(healthy / in_service * 100, 1) if in_service else 0,
        "avg_usage_rate": avg_usage,
        "source": stations[0].get("source", "unknown") if stations else "unavailable",
        "freshness_counts": {key: sum(s.get("data_freshness") == key for s in stations)
                             for key in ("live", "stale", "historical", "mock")},
    }


@router.get("/simulation/replay")
def replay(date: str = "2026-06-02"):
    """3.8 模擬重放 Before/After（Demo 成效）"""
    from api.stations import _require_mock
    _require_mock("模擬重放")
    return get_mock()["simulation_replay"]
