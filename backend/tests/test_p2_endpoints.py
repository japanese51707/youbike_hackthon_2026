"""
P2 API 端點測試（ADR-104/113 靜態層 + KPI/熱力圖）
==================================================
站點靜態打包（位置+地形+POI+指紋）+ heatmap 聚合 + KPI 真實統計。
用 mock 資料源。
"""
from __future__ import annotations


def test_station_static_bundle(client, monkeypatch):
    """靜態打包：含 location/terrain/poi/profile 四塊。"""
    import features.terrain as terrain
    monkeypatch.setattr(terrain, "get_terrain", lambda *a, **k: (_ for _ in ()).throw(AssertionError("static reads must not fetch/write terrain")))
    stations = client.get("/api/v1/stations").json()
    sid = stations[0]["station_id"]
    r = client.get(f"/api/v1/stations/{sid}/static")
    assert r.status_code == 200
    body = r.json()
    assert "location" in body and "terrain" in body and "poi" in body and "profile" in body
    assert body["location"]["station_name"] is not None
    # POI 一定有 area_type
    assert "area_type" in body["poi"]


def test_station_static_404(client):
    r = client.get("/api/v1/stations/NOPE-XYZ/static")
    assert r.status_code == 404


def test_heatmap_by_district(client):
    r = client.get("/api/v1/stations/heatmap", params={"dimension": "district"})
    assert r.status_code == 200
    body = r.json()
    assert body["dimension"] == "district"
    assert isinstance(body["buckets"], list)
    if body["buckets"]:
        b = body["buckets"][0]
        assert "count" in b and "avg_usage_rate" in b and "empty" in b


def test_heatmap_by_status(client):
    r = client.get("/api/v1/stations/heatmap", params={"dimension": "status"})
    assert r.status_code == 200
    assert r.json()["dimension"] == "status"


def test_kpi_real_stats(client):
    r = client.get("/api/v1/kpi")
    assert r.status_code == 200
    body = r.json()
    assert body["source"] == "mock"
    assert "total_stations" in body and "health_rate_pct" in body
    assert body["total_stations"] >= 0
