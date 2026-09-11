"""
ADR-117 任務執行閉環測試
========================
逐站完成回報（目標 vs 實際落差）、站點認領標註、後台手動介入（抽離/增加）、
執行者取消/退回（附原因）、稽核留痕。
"""
from __future__ import annotations
from tests.conftest import put_drivers_on_duty
import datetime as dt

import pytest

from db import vehicles_repo as vr, operators_repo as orp, tasks_repo
from core.providers import reset_providers
from core import dispatcher, task_execution as tx
from core.task_manager import get_task_manager


NOW = dt.datetime(2026, 6, 15, 11, 0)   # 平日早班離峰


def _rec(sid, dist, act, qty, score, avail, lat, lng):
    return {"station_id": sid, "station_name": sid, "district": dist,
            "action": act, "quantity": qty, "priority_score": score,
            "current_available": avail, "lat": lat, "lng": lng, "confidence_tier": "mid"}


def _make_trip():
    vr.seed_default_vehicles(3, 15)
    orp.seed_dispatch_operators(5)
    put_drivers_on_duty()
    reset_providers()
    dl = [
        _rec("滿A", "板橋區", "取車", 6, 80, 18, 25.010, 121.460),
        _rec("空B", "板橋區", "補車", 6, 90, 2, 25.012, 121.462),
    ]
    trips = dispatcher.assign_by_district(dl, now=NOW, persist=True)
    return trips[0]["trip_id"], dl


def test_claim_map_marks_stations():
    tid, _ = _make_trip()
    cmap = tx.station_claim_map()
    assert len(cmap) == 2
    assert cmap["滿A"]["claimed_by"] is not None
    assert cmap["滿A"]["task_id"] == tid


def test_report_station_records_gap_and_completion():
    tid, _ = _make_trip()
    r1 = tx.report_station(tid, "滿A", actual_available=12, operator="OP-004")
    assert r1["gap"] == 0.0          # 目標 12（18-6）vs 實際 12
    assert r1["all_done"] is False
    r2 = tx.report_station(tid, "空B", actual_available=7, operator="OP-004")
    assert r2["gap"] == 1.0          # 目標 8（2+6）vs 實際 7，落差 1
    assert r2["all_done"] is True
    # 全部回報後認領地圖清空
    assert len(tx.station_claim_map()) == 0


def test_report_unknown_station_raises():
    tid, _ = _make_trip()
    with pytest.raises(KeyError):
        tx.report_station(tid, "不存在", actual_available=5, operator="OP-004")


def test_remove_station_back_to_pool_when_demand_remains():
    tid, _ = _make_trip()
    # mock 源沒有「滿A」→ _demand_resolved 保守回 False → 回池
    rem = tx.remove_station(tid, "滿A", operator="OP-002", reason="改派")
    assert rem["back_to_pool"] is True
    assert rem["needs_notify"] is True
    # 抽離後該站清除認領
    assert "滿A" not in tx.station_claim_map()


def test_add_station_marks_claim():
    tid, _ = _make_trip()
    add = tx.add_station(tid, {"station_id": "新E", "station_name": "新E", "district": "板橋區",
                               "action": "補車", "target_available": 10, "quantity": 3},
                         operator="OP-002", reason="緊急增站")
    assert add["needs_notify"] is True
    assert "新E" in tx.station_claim_map()
    # 重複增加同站報錯
    with pytest.raises(ValueError):
        tx.add_station(tid, {"station_id": "新E"}, operator="OP-002")


def test_cancel_by_executor_requires_reason():
    tid, _ = _make_trip()
    with pytest.raises(ValueError):
        tx.cancel_by_executor(tid, operator="OP-005", reason="")


def test_cancel_by_executor_in_progress_goes_manual():
    tid, _ = _make_trip()
    tm = get_task_manager()
    tm.start(tid)   # in_progress
    tx.cancel_by_executor(tid, operator="OP-004", reason="車輛故障")
    # in_progress 退回 → manual_required（脫離執行中，後台可重排）
    assert tasks_repo.get(tid)["task_status"] == "manual_required"


def test_execution_writes_audit_trail():
    tid, _ = _make_trip()
    tx.report_station(tid, "滿A", actual_available=12, operator="OP-004")
    tx.remove_station(tid, "空B", operator="OP-002", reason="改派")
    from core.audit import get_audit_service
    logs = get_audit_service().query(type="task_report")
    assert len(logs) >= 2
