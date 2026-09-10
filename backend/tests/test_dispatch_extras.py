"""
調度系統加分項測試
==================
ADR-117 大夜跨區排程、尖峰折返組；ADR-118 駐點預備車量、即時天氣源突變偵測。
"""
from __future__ import annotations
import datetime as dt

from db import vehicles_repo as vr, operators_repo as orp
from core.providers import reset_providers
from core import dispatcher, emergency
from core.data import weather_source as ws


def _rec(sid, dist, act, qty, score, avail, lat, lng):
    return {"station_id": sid, "station_name": sid, "district": dist,
            "action": act, "quantity": qty, "priority_score": score,
            "current_available": avail, "lat": lat, "lng": lng, "confidence_tier": "mid"}


def _setup():
    vr.seed_default_vehicles(10, 15)
    orp.seed_dispatch_operators(20)
    reset_providers()


# ── 大夜跨區排程 ──
def test_night_shift_allows_cross_district():
    _setup()
    dl = [
        _rec("板橋滿", "板橋區", "取車", 8, 80, 40, 25.010, 121.460),
        _rec("三重空", "三重區", "補車", 7, 75, 2, 25.060, 121.490),
    ]
    night = dt.datetime(2026, 6, 15, 23, 30)
    trips = dispatcher.assign_by_district(dl, now=night)
    assert trips[0]["mode"] == "night"
    # 兩站量 15 = 車容量 → 一趟裝下 → 應跨區同趟
    cross = [t for t in trips if len({s["district"] for s in t["stations"]}) > 1]
    assert len(cross) >= 1


def test_day_shift_no_cross_district():
    _setup()
    dl = [
        _rec("板橋滿", "板橋區", "取車", 8, 80, 40, 25.010, 121.460),
        _rec("三重空", "三重區", "補車", 7, 75, 2, 25.060, 121.490),
    ]
    day = dt.datetime(2026, 6, 15, 11, 0)
    trips = dispatcher.assign_by_district(dl, now=day)
    for t in trips:
        assert len({s["district"] for s in t["stations"]}) == 1


# ── 尖峰折返組 ──
def test_peak_shuttle_clusters_same_district():
    _setup()
    dl = [
        _rec("滿A", "板橋區", "取車", 10, 85, 40, 25.010, 121.460),
        _rec("空B", "板橋區", "補車", 6, 90, 2, 25.012, 121.462),
        _rec("空C", "板橋區", "補車", 5, 70, 3, 25.011, 121.461),
        _rec("滿D", "板橋區", "取車", 8, 80, 38, 25.013, 121.463),
    ]
    now = dt.datetime(2026, 6, 15, 8, 0)   # 早尖峰
    clusters = dispatcher.assign_peak_shuttle(dl, now=now)
    assert len(clusters) >= 1
    for c in clusters:
        assert c["mode"] == "peak_shuttle"
        assert "shuttle_cluster" in c
        assert len({s["district"] for s in c["stations"]}) == 1   # 折返組同區
    # 應有含取車站的折返組（滿站→空站）
    assert any(any(s["action"] == "取車" for s in c["stations"]) for c in clusters)


# ── 駐點預備車量 ──
def test_reserve_bikes_deduct_on_site():
    def st(sid, total, bikes):
        return {"station_id": sid, "station_name": sid, "total_docks": total, "available_bikes": bikes}
    # 週轉40、站上10 → 備30
    assert emergency.reserve_bikes_for_station(st("A", 50, 10), 40)["reserve_bikes"] == 30
    # 週轉40、站上45 → 備0（站上已足）
    assert emergency.reserve_bikes_for_station(st("D", 50, 45), 40)["reserve_bikes"] == 0


def test_reserve_bikes_capped_by_space():
    st = {"station_id": "C", "station_name": "C", "total_docks": 20, "available_bikes": 5}
    r = emergency.reserve_bikes_for_station(st, peak_turnover=60)
    assert r["reserve_bikes"] == 15          # 空位只 15，被夾
    assert r["capped_by_space"] is True


def test_plan_stationed_reserves_sorted():
    stations = [
        {"station_id": "A", "station_name": "A", "total_docks": 50, "available_bikes": 10},
        {"station_id": "B", "station_name": "B", "total_docks": 50, "available_bikes": 35},
    ]
    plan = emergency.plan_stationed_reserves(stations, {"A": 40, "B": 40}, top_n=2)
    assert plan[0]["reserve_bikes"] >= plan[-1]["reserve_bikes"]


# ── 即時天氣源 ──
def test_weather_source_factory_and_unknown_mode():
    import pytest
    ws.reset_weather_source()
    assert ws.get_weather_source().name == "mock"
    with pytest.raises(ValueError):
        ws.get_weather_source(force_mode="unknown")


def test_weather_shift_detection():
    # ≥2 級跳才算突變
    assert ws.detect_weather_shift({"condition": "sunny"}, {"condition": "heavy_rain"}) is not None
    assert ws.detect_weather_shift({"condition": "cloudy"}, {"condition": "rain"}) is None


def test_cwa_source_is_skeleton():
    import pytest
    cwa = ws.get_weather_source(force_mode="cwa")
    with pytest.raises(NotImplementedError):
        cwa.get_weather("板橋區")
