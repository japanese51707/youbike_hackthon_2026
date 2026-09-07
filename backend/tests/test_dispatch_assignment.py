"""
ADR-114 調度資源與行政區任務指派測試
=====================================
驗證：
  - vehicles_repo CRUD（建/查/改載運量/指派區/停用/冪等 seed）
  - Provider 抽換（DB 實作 + 工廠 + 未知 mode 報錯）
  - dispatcher.assign_by_district 行政區約束（每趟同區、不超載、不超站數）
  - persist 回寫 current_district 到車/人 + 建 task 帶 district
"""
from __future__ import annotations

import pytest

from db import vehicles_repo as vr
from db import operators_repo as orp
from core.providers import (
    get_fleet_provider, get_operator_provider, reset_providers,
)
from core import dispatcher


# ── vehicles_repo CRUD ──
def test_vehicle_crud_and_seed():
    vr.seed_default_vehicles(41, 15)
    vs = vr.list_vehicles()
    assert len(vs) == 41
    assert vs[0]["max_capacity"] == 15
    # 改載運量（車種差異，可改）
    vr.update_vehicle("CAR-001", max_capacity=20)
    assert vr.get_vehicle("CAR-001")["max_capacity"] == 20
    # 冪等 seed（不重複）
    vr.seed_default_vehicles(41, 15)
    assert len(vr.list_vehicles()) == 41


def test_vehicle_assign_and_clear_district():
    vr.seed_default_vehicles(5, 15)
    vr.assign_district("CAR-002", "板橋區", "TASK-X")
    v = vr.get_vehicle("CAR-002")
    assert v["current_district"] == "板橋區"
    assert v["status"] == "dispatched"
    vr.clear_assignment("CAR-002")
    v = vr.get_vehicle("CAR-002")
    assert v["current_district"] is None
    assert v["status"] == "available"


def test_vehicle_deactivate_keeps_record():
    vr.seed_default_vehicles(3, 15)
    assert vr.deactivate("CAR-003") is True
    # 停用不刪除：仍查得到，但 active_only 不含
    assert vr.get_vehicle("CAR-003") is not None
    assert all(v["vehicle_id"] != "CAR-003" for v in vr.list_vehicles(active_only=True))


def test_vehicle_invalid_inputs():
    with pytest.raises(ValueError):
        vr.create_vehicle("CAR-BAD", max_capacity=0)     # 載運量須正
    vr.create_vehicle("CAR-OK", max_capacity=10)
    with pytest.raises(ValueError):
        vr.create_vehicle("CAR-OK")                       # 重複建
    with pytest.raises(ValueError):
        vr.update_vehicle("CAR-OK", status="flying")      # 非法狀態


# ── Provider 抽換 ──
def test_providers_db_and_factory():
    vr.seed_default_vehicles(5, 15)
    orp.seed_dispatch_operators(10)
    reset_providers()
    fp = get_fleet_provider()
    op = get_operator_provider()
    assert fp.name == "db"
    assert len(fp.available_vehicles()) == 5
    assert len(op.available_operators()) >= 10
    with pytest.raises(ValueError):
        get_fleet_provider(force_mode="unknown")


# ── 行政區任務指派 ──
def _rec(sid, district, quantity, score):
    """組一筆模擬的調度建議（對齊 build_dispatch_list 輸出關鍵欄位）。"""
    return {
        "station_id": sid, "station_name": sid, "district": district,
        "action": "補車", "quantity": quantity, "priority_score": score,
        "confidence_tier": "mid",
    }


def test_assign_by_district_no_cross_district_and_no_overload():
    vr.seed_default_vehicles(10, 15)
    orp.seed_dispatch_operators(10)
    reset_providers()
    # 兩區各數站，總量會超過單車 15 → 應切多趟，但每趟不跨區、不超載
    dispatch_list = [
        _rec("A1", "板橋區", 6, 90),
        _rec("A2", "板橋區", 6, 80),
        _rec("A3", "板橋區", 6, 70),   # 板橋共 18 > 15 → 至少 2 趟
        _rec("B1", "三重區", 5, 85),
        _rec("B2", "三重區", 5, 60),   # 三重共 10 ≤ 15，但每趟最大站數=3 → 1 趟
    ]
    trips = dispatcher.assign_by_district(dispatch_list)
    assert len(trips) >= 3   # 板橋至少 2 趟 + 三重 1 趟
    for t in trips:
        # 每趟同一行政區
        assert len({s["district"] for s in t["stations"]}) == 1
        assert t["stations"][0]["district"] == t["district"]
        # 不超載（總量 ≤ 該趟車容量）
        assert t["total_quantity"] <= t["vehicle_capacity"]
        # 不超每趟站數上限（config 每趟最大站數=3）
        assert t["stop_count"] <= 3


def test_assign_by_district_persist_writes_back():
    vr.seed_default_vehicles(5, 15)
    orp.seed_dispatch_operators(5)
    reset_providers()
    dispatch_list = [_rec("A1", "新莊區", 8, 88), _rec("A2", "新莊區", 4, 70)]
    trips = dispatcher.assign_by_district(dispatch_list, persist=True)
    assert len(trips) == 1
    t = trips[0]
    assert t["status"] == "assigned"
    # 車/人的 current_district 已回寫
    veh = vr.get_vehicle(t["assigned_vehicle"])
    assert veh["current_district"] == "新莊區"
    assert veh["status"] == "dispatched"
    oper = orp.get_operator(t["assigned_operator"])
    assert oper["current_district"] == "新莊區"
    # task 已建且帶 district / assigned_vehicle
    from db import tasks_repo
    task = tasks_repo.get(t["trip_id"])
    assert task is not None
    assert task["district"] == "新莊區"
    assert task["assigned_vehicle"] == t["assigned_vehicle"]


def test_assign_by_district_unassigned_when_no_vehicle():
    """車不夠時多出的趟標 unassigned，不 crash。"""
    vr.seed_default_vehicles(1, 15)     # 只有 1 台車
    orp.seed_dispatch_operators(5)
    reset_providers()
    # 兩區各 1 趟 → 第 2 趟無車可派
    dispatch_list = [_rec("A1", "板橋區", 10, 90), _rec("B1", "三重區", 10, 85)]
    trips = dispatcher.assign_by_district(dispatch_list)
    assert len(trips) == 2
    statuses = {t["status"] for t in trips}
    assert "assigned" in statuses and "unassigned" in statuses
