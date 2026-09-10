"""
P0 API 端點測試（ADR-113/118/119 串接）
========================================
單站預測 / 天氣 by-location / 任務清單 / 互動組單三入口 / confirm-trip。
測試用 mock 資料源（不打外部即時源）；預測/天氣驗證端點結構與降級行為。
"""
from __future__ import annotations


def test_station_detail_has_prediction(client):
    """單站詳情含 prediction（真實 LightGBM 或降級 mock，都要有 source 標記）。"""
    # mock 源第一站
    stations = client.get("/api/v1/stations").json()
    assert stations, "mock 應有站點"
    sid = stations[0]["station_id"]
    r = client.get(f"/api/v1/stations/{sid}")
    assert r.status_code == 200
    body = r.json()
    assert "current" in body and "prediction" in body and "params" in body
    pred = body["prediction"]
    assert "source" in pred   # lightgbm 或 mock_fallback，都明確標來源


def test_station_detail_404():
    from fastapi.testclient import TestClient
    from main import app
    r = TestClient(app).get("/api/v1/stations/NOT-EXIST-XYZ")
    assert r.status_code == 404


def test_dispatch_tasks_empty_initially(client):
    """任務清單接 task_manager：初始無任務回空陣列（不再是 mock 假資料）。"""
    r = client.get("/api/v1/dispatch/tasks")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_dispatch_task_detail_404(client):
    r = client.get("/api/v1/dispatch/tasks/NOPE")
    assert r.status_code == 404


def test_build_from_station_returns_draft(client):
    """以站為起點組單：回草稿（is_draft）。用 mock 源的第一站。"""
    stations = client.get("/api/v1/stations").json()
    sid = stations[0]["station_id"]
    # 需先有需調度站；mock 源不一定觸發，但端點應正常回應（草稿或錯誤訊息）
    r = client.post("/api/v1/dispatch/build/from-station", json={"station_id": sid})
    assert r.status_code == 200
    body = r.json()
    # 該站若在需調度清單→回草稿；否則回 error 提示（兩者都不該 500）
    assert body.get("is_draft") is True or "error" in body


def test_build_from_vehicle_needs_params(client):
    r = client.post("/api/v1/dispatch/build/from-vehicle", json={})
    assert r.status_code == 400


def test_build_emergency_needs_station_ids(client):
    r = client.post("/api/v1/dispatch/build/emergency", json={})
    assert r.status_code == 400


def test_confirm_trip_requires_auth(client):
    """confirm-trip 需 dispatcher/maintainer 權限；無身分 → 401。"""
    r = client.post("/api/v1/dispatch/confirm-trip", json={"draft": {"draft_id": "X"}})
    assert r.status_code == 401


def test_confirm_trip_empty_draft_rejected(client):
    """帶合法身分但空草稿 → 400（走 dispatcher 帳號 OP-002）。"""
    r = client.post("/api/v1/dispatch/confirm-trip",
                    json={"draft": {}},
                    headers={"X-Operator-Id": "OP-002"})
    assert r.status_code == 400
