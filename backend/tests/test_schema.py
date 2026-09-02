"""Schema 回傳測試（A0-A3）：關鍵欄位存在且尺度正確。"""


def test_stations_have_freshness_fields(client):
    """GET /stations 每站含 data_freshness 與 source_timestamp（NFR-10/NFR-5）。"""
    stations = client.get("/api/v1/stations").json()
    assert len(stations) > 0
    for s in stations:
        assert "data_freshness" in s
        assert "source_timestamp" in s
        assert "usage_rate" in s


def test_station_detail_shape(client):
    """單站詳情含 current/history/prediction/params。"""
    d = client.get("/api/v1/stations/500101001").json()
    assert "current" in d and "history" in d
    assert "prediction" in d and "params" in d


def test_target_usage_rate_same_scale_as_usage(client):
    """params 附換算好的 target_usage_rate（0~100%），與 usage_rate 同尺度可比（I-3）。"""
    p = client.get("/api/v1/stations/500101001/params").json()
    tur = p.get("target_usage_rate")
    assert tur is not None
    # target_level 0.5 → target_usage_rate 50.0
    assert tur == round(p["params"]["target_level"] * 100, 1)
    assert 0 <= tur <= 100


def test_recommendations_have_priority_and_reason(client):
    """調度建議含 priority_score(0~100) / priority_level / 人話 reason。"""
    recs = client.get("/api/v1/dispatch/recommendations").json()
    assert len(recs) > 0
    for r in recs:
        assert 0 <= r["priority_score"] <= 100
        assert r["priority_level"] in ("high", "medium", "low")
        assert isinstance(r["reason"], str) and len(r["reason"]) > 0
        assert r["action"] in ("補車", "取車")
