"""
ADR-119 互動式派工單組建測試
============================
三入口(以車/以站/緊急)+草稿預覽(estimate)+確認落地+總站待命資源。
"""
from __future__ import annotations
import datetime as dt

import pytest

from db import vehicles_repo as vr, operators_repo as orp, tasks_repo
from core.providers import reset_providers
from core import dispatch_builder as db


NOW = dt.datetime(2026, 6, 15, 11, 0)   # 平日早班離峰


def _rec(sid, dist, act, qty, score, avail, lat, lng):
    return {"station_id": sid, "station_name": sid, "district": dist,
            "action": act, "quantity": qty, "priority_score": score,
            "current_available": avail, "lat": lat, "lng": lng}


def _setup():
    vr.seed_default_vehicles(10, 15)
    vr.seed_depot_vehicles(3, 15)
    orp.seed_dispatch_operators(20)
    orp.seed_depot_standby_operators(5)
    reset_providers()


DL = [
    _rec("板橋滿", "板橋區", "取車", 6, 85, 40, 25.010, 121.460),
    _rec("板橋空", "板橋區", "補車", 6, 90, 2, 25.012, 121.462),
    _rec("三重空", "三重區", "補車", 7, 70, 2, 25.060, 121.490),
]


# ── 入口 a：以車為起點 ──
def test_build_from_vehicle_uses_vehicle_district():
    _setup()
    vr.update_vehicle("CAR-001", current_district="板橋區")
    reset_providers()
    draft = db.build_from_vehicle("CAR-001", "OP-004", DL, now=NOW)
    assert draft["is_draft"] is True
    assert draft["district"] == "板橋區"
    assert all(s["district"] == "板橋區" for s in draft["stations"])
    assert "estimate" in draft
    assert draft["estimate"]["urgency_sum"] > 0


def test_build_from_vehicle_change_district_recomputes():
    _setup()
    vr.update_vehicle("CAR-002", current_district="板橋區")
    reset_providers()
    # 後台改目標區為三重 → 應改用三重的站
    draft = db.build_from_vehicle("CAR-002", "OP-004", DL, district="三重區", now=NOW)
    assert draft["district"] == "三重區"
    assert all(s["district"] == "三重區" for s in draft["stations"])


# ── 入口 b：以站為起點 ──
def test_build_from_station_lists_vehicle_candidates():
    _setup()
    draft = db.build_from_station("板橋空", DL, now=NOW)
    assert draft["is_draft"] is True
    assert draft["district"] == "板橋區"
    # 車輛候選分三類
    cand = draft["vehicle_candidates"]
    assert "in_district" in cand and "nearby" in cand and "depot_standby" in cand
    assert len(cand["depot_standby"]) == 3   # 3 台總站待命


def test_build_from_station_seed_station_first():
    _setup()
    draft = db.build_from_station("板橋空", DL, now=NOW)
    # 被點的站應在這趟內
    assert any(s["station_id"] == "板橋空" for s in draft["stations"])


# ── 入口 c：緊急出車 ──
def test_build_emergency_resource_priority():
    _setup()
    # 設一台預備車
    vr.set_reserve_fleet(0.1)
    reset_providers()
    draft = db.build_emergency(["板橋滿", "板橋空"], DL, now=NOW)
    assert draft["mode"] == "emergency"
    rs = draft["resource_suggestion"]
    assert "nearest_idle" in rs and "reserve_standby" in rs
    # 就近閒置車優先（有閒置車時不預設用預備車）
    assert draft["assigned_vehicle"] in rs["nearest_idle"] or draft["assigned_vehicle"] is not None


def test_build_emergency_cross_district_marks():
    _setup()
    draft = db.build_emergency(["板橋滿", "三重空"], DL, now=NOW)
    assert draft["district"] == "緊急跨區"   # 跨多區


# ── 確認落地 ──
def test_confirm_trip_persists():
    _setup()
    vr.update_vehicle("CAR-003", current_district="板橋區")
    reset_providers()
    draft = db.build_from_vehicle("CAR-003", "OP-004", DL, now=NOW)
    res = db.confirm_trip(draft, operator="controller")
    assert res["confirmed"] is True
    assert res["status"] == "assigned"
    # 真正落地成 task
    task = tasks_repo.get(res["trip_id"])
    assert task is not None
    assert task["task_status"] == "assigned"
    # 車/人 current_district 已回寫
    assert vr.get_vehicle("CAR-003")["current_district"] == draft["district"]


def test_confirm_empty_draft_raises():
    _setup()
    with pytest.raises(ValueError):
        db.confirm_trip({"draft_id": "DRAFT-x", "stations": []})


def test_confirm_without_vehicle_or_operator_raises():
    _setup()
    with pytest.raises(ValueError):
        db.confirm_trip({"draft_id": "DRAFT-x", "stations": [{"station_id": "A"}],
                         "assigned_vehicle": None, "assigned_operator": None})
