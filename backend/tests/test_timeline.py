"""時間軸 3.10：mock 維持示範；歷史序列可用假 DataFrame 驗證。"""
from __future__ import annotations

import pandas as pd


def test_timeline_mock_still_works(client):
    r = client.get("/api/v1/stations/timeline", params={"district": "中和區"})
    assert r.status_code == 200
    body = r.json()
    assert "frames" in body
    assert body["frames"]


def test_historical_timeline_citywide(monkeypatch):
    from core.data.historical import HistoricalDataSource

    df = pd.DataFrame([
        {"timestamp": "2026-06-02 07:00:00", "station_id": "A", "station_name": "甲",
         "district": "板橋區", "lat": 25.01, "lng": 121.46, "total_docks": 20,
         "available_bikes": 10, "available_docks": 10, "usage_rate": 50},
        {"timestamp": "2026-06-02 08:00:00", "station_id": "A", "station_name": "甲",
         "district": "板橋區", "lat": 25.01, "lng": 121.46, "total_docks": 20,
         "available_bikes": 0, "available_docks": 20, "usage_rate": 0},
        {"timestamp": "2026-06-02 08:00:00", "station_id": "B", "station_name": "乙",
         "district": "新店區", "lat": 24.97, "lng": 121.54, "total_docks": 20,
         "available_bikes": 8, "available_docks": 12, "usage_rate": 40},
    ])
    monkeypatch.setattr(HistoricalDataSource, "_df", lambda self, month=None: df)
    result = HistoricalDataSource().get_timeline(district="全市", date="2026-06-02", interval=60)
    assert result["district"] == "全市"
    assert result["source"] == "historical"
    eight = next(frame for frame in result["frames"] if frame["time"] == "08:00")
    assert {row["station_id"] for row in eight["stations"]} == {"A", "B"}
    assert next(row for row in eight["stations"] if row["station_id"] == "A")["available_bikes"] == 0
