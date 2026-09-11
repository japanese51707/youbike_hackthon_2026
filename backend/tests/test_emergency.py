"""
ADR-118 緊急救火與死結警報測試
===============================
車隊保留率(standby 排除常態派單)、死結偵測(某區≥3大站死結)、
救火觸發(在途來不及→派 standby，可跨區)。
"""
from __future__ import annotations

from db import vehicles_repo as vr
from core.providers import get_fleet_provider, reset_providers
from core.alert_service import reset_alert_service
from core import emergency


def _st(sid, dist, total, bikes):
    docks = total - bikes
    return {"station_id": sid, "station_name": sid, "district": dist,
            "total_docks": total, "available_bikes": bikes, "available_docks": docks}


# ── 車隊保留率 ──
def test_reserve_fleet_excluded_from_available():
    vr.seed_default_vehicles(41, 15)
    n = vr.set_reserve_fleet(0.12)
    assert n == 5   # ceil(41*0.12)=5
    assert len(vr.list_standby()) == 5
    reset_providers()
    fp = get_fleet_provider()
    # available_vehicles 應排除 standby（41-5=36）
    assert len(fp.available_vehicles()) == 36


# ── 死結偵測 ──
def test_detect_deadlocks_by_district():
    stations = [
        _st("大滿1", "板橋區", 50, 50),   # 滿站死結(大站)
        _st("大空2", "板橋區", 48, 0),    # 空站死結(大站)
        _st("大滿3", "板橋區", 45, 45),   # 滿站死結(大站)
        _st("小空", "板橋區", 20, 0),     # 死結但小站(<40) → 不算
        _st("正常", "板橋區", 50, 25),    # 正常 → 不算
        _st("三重大空", "三重區", 60, 0), # 三重只1個 → 不達門檻
    ]
    dl = emergency.detect_deadlocks(stations)
    assert len(dl) == 1                 # 只有板橋達 ≥3
    assert dl[0]["district"] == "板橋區"
    assert dl[0]["count"] == 3          # 小站不算


# ── 救火觸發 ──
def test_firefight_suggests_reserve_without_dispatching():
    vr.seed_default_vehicles(41, 15)
    vr.set_reserve_fleet(0.12)
    reset_providers()
    reset_alert_service()
    stations = [
        _st("大滿1", "板橋區", 50, 50),
        _st("大空2", "板橋區", 48, 0),
        _st("大滿3", "板橋區", 45, 45),
    ]
    # 在途車 45 分才到（>30 門檻）→ 該派 standby
    res = emergency.check_and_dispatch_reserve(
        stations, in_transit_eta_min=45, persist=False)
    assert res["triggered"] is True
    assert len(res["suggestions"]) == 1        # 板橋 1 區 → 派 1 台
    assert len(res["alerts"]) == 1
    assert res["alerts"][0]["level"] == "critical"
    # 建議不占用車輛；人工確認另由 confirm-trip 完成
    veh_id = res["suggestions"][0]["vehicle_id"]
    assert vr.get_vehicle(veh_id)["status"] == "standby"
    assert res["dispatched"] == []
    assert vr.get_vehicle(veh_id)["current_task_id"] is None


def test_firefight_not_triggered_when_in_transit_fast_enough():
    vr.seed_default_vehicles(41, 15)
    vr.set_reserve_fleet(0.12)
    reset_providers()
    reset_alert_service()
    stations = [
        _st("大滿1", "板橋區", 50, 50),
        _st("大空2", "板橋區", 48, 0),
        _st("大滿3", "板橋區", 45, 45),
    ]
    # 在途車 20 分就到（≤30）→ 常態車處理，不動 standby
    res = emergency.check_and_dispatch_reserve(
        stations, in_transit_eta_min=20, persist=False)
    assert res["triggered"] is False
    assert res["dispatched"] == []
    assert len(vr.list_standby()) == 5        # standby 沒被動用


def test_firefight_not_triggered_below_threshold():
    vr.seed_default_vehicles(41, 15)
    vr.set_reserve_fleet(0.12)
    reset_providers()
    reset_alert_service()
    stations = [
        _st("大滿1", "板橋區", 50, 50),
        _st("大空2", "板橋區", 48, 0),   # 只 2 個 < 門檻 3
    ]
    res = emergency.check_and_dispatch_reserve(stations, in_transit_eta_min=None, persist=False)
    assert res["triggered"] is False
