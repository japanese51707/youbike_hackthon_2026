"""
P1 API 端點測試（ADR-114/117/118/119 串接）
=============================================
逐站回報/認領/後台介入 + 下一趟建議 + 人力車隊 + 死結警報。
用 mock 資料源 + seed 資源；不打外部即時源。
"""
from __future__ import annotations

import pytest


# ── 人力車隊 ──
def test_operators_list_real(client):
    """調度員清單接 operators_repo（conftest seed 了預設帳號）。"""
    r = client.get("/api/v1/operators")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_operators_filter_role_type(client):
    r = client.get("/api/v1/operators", params={"role_type": "driver"})
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_vehicles_list(client):
    """車隊清單（初始可能空，端點應正常回陣列）。"""
    from db import vehicles_repo as vr
    vr.seed_default_vehicles(5, 15)
    r = client.get("/api/v1/vehicles")
    assert r.status_code == 200
    assert len(r.json()) >= 5


def test_vehicles_standby_structure(client):
    from db import vehicles_repo as vr
    vr.seed_default_vehicles(10, 15)
    vr.set_reserve_fleet(0.2)
    vr.seed_depot_vehicles(3, 15)
    r = client.get("/api/v1/vehicles/standby")
    assert r.status_code == 200
    body = r.json()
    assert "reserve_standby" in body and "depot_standby" in body
    assert len(body["depot_standby"]) == 3


def test_vehicle_404(client):
    r = client.get("/api/v1/vehicles/NO-SUCH-CAR")
    assert r.status_code == 404


# ── 死結警報 ──
def test_deadlocks_endpoint(client):
    """死結偵測端點（mock 源，回陣列即可）。"""
    r = client.get("/api/v1/emergency/deadlocks")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_emergency_check_endpoint(client):
    r = client.post("/api/v1/emergency/check", json={"in_transit_eta_min": 45})
    assert r.status_code == 200
    body = r.json()
    assert "triggered" in body and "dispatched" in body


# ── 下一趟建議 ──
def test_next_trip_needs_vehicle(client):
    r = client.get("/api/v1/dispatch/next-trip")
    assert r.status_code == 422   # 缺必填 query param vehicle_id


def test_next_trip_unknown_vehicle(client):
    r = client.get("/api/v1/dispatch/next-trip", params={"vehicle_id": "NOPE"})
    assert r.status_code == 200
    assert "candidates" in r.json()   # 找不到車回 error + 空候選，不 500


# ── 後台介入權限 ──
def test_remove_station_requires_auth(client):
    r = client.delete("/api/v1/dispatch/tasks/T1/stations/S1")
    assert r.status_code == 401


def test_return_task_needs_reason(client):
    """退回需附原因；帶身分但無原因 → 400。"""
    r = client.post("/api/v1/dispatch/tasks/T1/return", json={},
                    headers={"X-Operator-Id": "OP-001"})
    assert r.status_code == 400


def test_report_needs_fields(client):
    r = client.post("/api/v1/dispatch/tasks/T1/report", json={},
                    headers={"X-Operator-Id": "OP-001"})
    assert r.status_code == 400


def test_claim_map_empty_initially(client):
    r = client.get("/api/v1/dispatch/claim-map")
    assert r.status_code == 200
    assert isinstance(r.json(), dict)
