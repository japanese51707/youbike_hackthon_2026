"""ADR-303 regression: real-provider shape, freshness and confirm-time observations."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import ssl
import pytest
from config_loader import get_config
from core.data import observations, degradation
from core.data.observations import TAIPEI
from core.data.youbike_official import YouBikeOfficialDataSource
from core import dispatch_builder
from db import operators_repo, vehicles_repo, tasks_repo
from tests.conftest import OP_DISPATCHER


def raw(**changes):
    return {"sno": "500201001", "sna": "官方站", "sarea": "板橋區", "lat": "25.01", "lng": "121.46",
            "tot_quantity": "20", "sbi_quantity": "2", "bemp": "18", "act": "1",
            "mday": "20260911T083500", **changes}


def station(**changes):
    ts = datetime.now(timezone.utc).isoformat()
    return {**YouBikeOfficialDataSource._to_standard(raw()), "timestamp": ts,
            "observed_at": ts, "source_timestamp": ts, **changes}


class Source:
    def __init__(self, rows): self.rows, self.failed = rows, False
    def get_stations(self):
        if self.failed: raise RuntimeError("upstream failure")
        return self.rows
    def get_history(self, *a, **k): raise AssertionError("live source has no history")


def use_source(monkeypatch, rows):
    monkeypatch.setitem(get_config()["data_source"], "mode", "youbike_official")
    src = Source(rows)
    monkeypatch.setattr(degradation, "get_data_source", lambda: src)
    return src


def test_official_observation_is_not_receipt():
    row = YouBikeOfficialDataSource._to_standard(raw())
    assert row["timestamp"] == row["observed_at"] == "2026-09-11T08:35:00+08:00"
    assert row["received_at"] != row["observed_at"]
    assert row["source"] == "youbike_official"


@pytest.mark.parametrize("change", [
    {"sbi_quantity": "oops"}, {"sbi_quantity": "1.5"}, {"bemp": "-1"},
    {"tot_quantity": "nan"}, {"lat": "nan"}, {"lng": "181"},
    {"mday": "oops"}, {"act": "invalid"}, {"bemp": "20"},
])
def test_untrusted_values_are_rejected(change):
    assert YouBikeOfficialDataSource._to_standard(raw(**change)) is None


def test_disabled_station_not_empty_demand():
    row = YouBikeOfficialDataSource._to_standard(raw(act="0", sbi_quantity="0", bemp="20"))
    assert row["status"] == "offline"
    assert observations.normalize(row, "youbike_official")["dispatch_eligible"] is False


def test_aware_naive_future_and_missing_times():
    now = datetime(2026, 9, 11, 0, 35, tzinfo=timezone.utc)
    row = YouBikeOfficialDataSource._to_standard(raw())
    assert observations.normalize(row, "youbike_official", now=now)["data_freshness"] == "live"
    assert observations.parse_time("2026-09-11T08:35:00").utcoffset() == timedelta(hours=8)
    future = {**row, "observed_at": (now + timedelta(hours=1)).isoformat()}
    assert "future_observation" in observations.normalize(future, "youbike_official", now=now)["quality_reasons"]
    assert degradation._is_stale(None, 600)


def test_parse_time_accepts_real_source_iso_variants():
    """ADR-303 regression: every timestamp shape the real sources emit must parse.

    Python 3.11+ fromisoformat swallows all of these, so a 3.10 runtime used to fail
    the official feed's compact mday and the Z-suffixed history bounds — surfacing as
    a blanket 503 on every station endpoint. Pin the shapes, not the interpreter.
    """
    expected = datetime(2026, 9, 12, 9, 34, 2, tzinfo=TAIPEI)
    for text in ("2026-09-12T09:34:02",            # 擴充式、naive（補 +08:00）
                 "2026-09-12 09:34:02",            # 空白分隔
                 "2026-09-12T09:34:02+08:00",      # 帶冒號位移
                 "2026-09-12T09:34:02+0800",       # 無冒號位移
                 "20260912T093402",                # 官方源 mday 緊湊式
                 "20260912T093402+08:00"):
        assert observations.parse_time(text) == expected, text
    # Z / z 是 UTC 指示字，不可當成本地時間。
    for text in ("2026-09-12T01:34:02Z", "2026-09-12T01:34:02z", "20260912T013402Z"):
        assert observations.parse_time(text) == expected, text
    assert observations.parse_time(expected) is expected
    with pytest.raises(ValueError):
        observations.parse_time("not-a-timestamp")


def test_failed_live_snapshot_stays_same_source_and_does_not_mutate(monkeypatch):
    original = station()
    src = use_source(monkeypatch, [original])
    first = degradation.get_stations_with_degradation()
    first[0]["available_bikes"] = 999
    assert original["available_bikes"] == 2
    src.failed = True
    last = degradation.get_stations_with_degradation()[0]
    assert last["source"] == "youbike_official"
    assert last["data_freshness"] == "stale"
    assert last["available_bikes"] == 2 and not last["dispatch_eligible"]
    assert last["observed_at"] == original["observed_at"]


def test_no_snapshot_is_503_not_successful_empty(client, monkeypatch):
    src = use_source(monkeypatch, [])
    src.failed = True
    response = client.get("/api/v1/stations")
    assert response.status_code == 503
    assert response.json()["error"] == "data_unavailable"


def test_source_switch_never_reuses_previous_provider(monkeypatch):
    src = use_source(monkeypatch, [station()])
    degradation.get_stations_with_degradation()
    replacement = Source([])
    replacement.failed = True
    monkeypatch.setattr(degradation, "get_data_source", lambda: replacement)
    with pytest.raises(observations.DataUnavailable): degradation.get_stations_with_degradation()


def test_live_detail_does_not_ask_live_adapter_for_archive(client, monkeypatch):
    row = station()
    use_source(monkeypatch, [row])
    from core.data.historical import HistoricalDataSource
    monkeypatch.setattr(HistoricalDataSource, "get_history", lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError()))
    response = client.get(f"/api/v1/stations/{row['station_id']}")
    assert response.status_code == 200
    body = response.json()
    assert body["history"] == [] and body["history_status"]["status"] == "unavailable"
    assert body["prediction"]["source"] == "unavailable"  # MockPredictor fixture cannot masquerade as live
    assert body["params"] is None


@pytest.mark.parametrize("change", ["expired", "offline", "inventory", "time", "source"])
def test_confirmation_rechecks_actual_observation(client, monkeypatch, change):
    row = station()
    src = use_source(monkeypatch, [row])
    operators_repo.seed_dispatch_operators(4)
    operators_repo.update_status("OP-004", "on_duty")
    vehicles_repo.seed_default_vehicles(1, 15)
    normalized = degradation.get_stations_with_degradation()[0]
    rec = {**normalized, "current_available": 2, "action": "補車", "quantity": 3, "priority_score": 80}
    draft = dispatch_builder.build_from_station(row["station_id"], [rec], "OP-004", "CAR-001", created_by="OP-002")
    if change == "expired": src.failed = True
    if change == "offline": row["service_available"] = False
    if change == "inventory": row.update(available_bikes=3, available_docks=17)
    if change == "time": row["observed_at"] = (datetime.now(timezone.utc) - timedelta(seconds=30)).isoformat()
    if change == "source": monkeypatch.setitem(get_config()["data_source"], "mode", "mock")
    response = client.post("/api/v1/dispatch/confirm-trip", json={"draft_id": draft["draft_id"], "version": 1}, headers=OP_DISPATCHER)
    assert response.status_code == 409
    assert tasks_repo.list_tasks() == []


def test_history_range_validation(client):
    assert client.get("/api/v1/stations/A/history?start=oops&end=2026-06-30").status_code == 422
    assert client.get("/api/v1/stations/A/history?start=2026-01-01&end=2026-06-30").status_code == 422


def test_duty_and_actual_http_task_lifecycle(client, monkeypatch):
    row = station()
    use_source(monkeypatch, [row])
    operators_repo.seed_dispatch_operators(4)
    vehicles_repo.seed_default_vehicles(1, 15)
    # ADR-123：這站要補到目標水位需 8 台，出車前宣告滿載（未回報載量會被擋，另有專門測試）
    vehicles_repo.report_onboard("CAR-001", 15, "manual_report")
    driver = {"X-Operator-Id": "OP-004"}
    assert client.post("/api/v1/operators/me/duty", json={"status": "on_duty"}, headers=driver).status_code == 200
    preview = client.post("/api/v1/dispatch/build/from-station", json={"station_id": row["station_id"], "operator_id": "OP-004", "vehicle_id": "CAR-001"}, headers=OP_DISPATCHER)
    assert preview.status_code == 200
    draft = preview.json()
    confirmed = client.post("/api/v1/dispatch/confirm-trip", json={"draft_id": draft["draft_id"], "version": draft["version"]}, headers=OP_DISPATCHER)
    assert confirmed.status_code == 200, confirmed.text
    tid = confirmed.json()["trip_id"]
    assert client.post("/api/v1/operators/me/duty", json={"status": "off_duty"}, headers=driver).status_code == 409
    assert client.post(f"/api/v1/dispatch/tasks/{tid}/start", headers=driver).status_code == 200
    report = client.post(f"/api/v1/dispatch/tasks/{tid}/report", json={"station_id": row["station_id"], "actual_available": 10}, headers=driver)
    assert report.status_code == 200 and report.json()["status"] == "completed"
    overview = client.get("/api/v1/dispatch/overview").json()
    assert overview["task_counts"]["completed"] == 1
    assert vehicles_repo.get_vehicle("CAR-001")["status"] == "available"
    assert client.post("/api/v1/operators/me/duty", json={"status": "off_duty"}, headers=driver).status_code == 200


def test_official_tls_keeps_certificate_and_hostname_checks(monkeypatch):
    from contextlib import contextmanager
    import httpx
    seen = {}
    class Response:
        def raise_for_status(self): pass
        def iter_bytes(self): yield b"sno,act\nA,1\n"
    @contextmanager
    def stream(*args, **kwargs):
        seen.update(kwargs)
        yield Response()
    monkeypatch.setattr(httpx, "stream", stream)
    assert YouBikeOfficialDataSource()._fetch_raw() == [{"sno": "A", "act": "1"}]
    assert seen["verify"].verify_mode == ssl.CERT_REQUIRED
    assert seen["verify"].check_hostname is True
    assert seen["follow_redirects"] is False


@pytest.mark.parametrize("url", ["http://data.ntpc.gov.tw/", "https://127.0.0.1/", "https://evil.example/", "https://user:secret@data.ntpc.gov.tw/"])
def test_official_url_boundary(monkeypatch, url):
    monkeypatch.setitem(get_config()["data_source"], "youbike_official_url", url)
    with pytest.raises(ValueError): YouBikeOfficialDataSource()


def test_historical_month_boundary_and_timezone(tmp_path, monkeypatch):
    import pandas as pd
    from core.data.historical import HistoricalDataSource
    monkeypatch.setenv("YOUBIKE_HISTORY_DIR", str(tmp_path))
    for month, timestamp in [("2026-05", "2026-05-31T23:30:00"), ("2026-06", "2026-06-01T00:00:00")]:
        path = tmp_path / f"year_month={month}"
        path.mkdir()
        pd.DataFrame([{"日期": timestamp, "場站名稱": "sample", "行政區": "板橋區", "緯度": 25.01,
                       "經度": 121.46, "可借車數": 2, "可還位數": 18, "總車柱數": 20, "借用率": 10}]).to_parquet(path / "data.parquet")
    rows = HistoricalDataSource().get_history("sample", "2026-05-31T15:00:00Z", "2026-05-31T16:00:00Z")
    assert len(rows) == 2
    assert all(r["source"] == "historical" and r["timestamp"].endswith("+08:00") for r in rows)
    assert rows[0]["identity_source"] == "unmapped_historical_name"


# ── ADR-305：開發模式資料源降級到 mock（正式路徑不變）──

def test_adr305_no_snapshot_no_switch_still_503(monkeypatch):
    """開關 false（預設）→ 真實源失敗且無快照仍回 503（維持 ADR-303）。"""
    src = use_source(monkeypatch, [])
    src.failed = True
    monkeypatch.setitem(get_config()["data_source"], "dev_fallback_to_mock", False)
    with pytest.raises(observations.DataUnavailable):
        degradation.get_stations_with_degradation()


def test_adr305_production_env_never_falls_back_to_mock(monkeypatch):
    """開關 true 但 APP_ENV=production → 正式環境不降級，仍回 503。"""
    src = use_source(monkeypatch, [])
    src.failed = True
    monkeypatch.setitem(get_config()["data_source"], "dev_fallback_to_mock", True)
    monkeypatch.setenv("APP_ENV", "production")
    with pytest.raises(observations.DataUnavailable):
        degradation.get_stations_with_degradation()


def test_adr305_dev_env_falls_back_to_mock_marked_and_not_dispatchable(monkeypatch):
    """開發環境 + 開關 true + 真實源失敗且無快照 → 回 mock，且每筆標記且不可派工。"""
    src = use_source(monkeypatch, [])
    src.failed = True
    monkeypatch.setitem(get_config()["data_source"], "dev_fallback_to_mock", True)
    monkeypatch.setenv("APP_ENV", "development")
    rows = degradation.get_stations_with_degradation()
    assert len(rows) > 0
    for r in rows:
        assert r["data_freshness"] == "mock"
        assert r["dispatch_eligible"] is False
        assert "upstream_unavailable_using_mock" in r["quality_reasons"]


def test_adr305_status_reports_degrading_to_mock(monkeypatch):
    """/data/status 在降級時回 degrading_to_mock=true 與 mock_fallback_reason。"""
    src = use_source(monkeypatch, [])
    src.failed = True
    monkeypatch.setitem(get_config()["data_source"], "dev_fallback_to_mock", True)
    monkeypatch.setenv("APP_ENV", "development")
    status = degradation.degradation_status()
    assert status["degrading_to_mock"] is True
    assert status["mock_fallback_reason"]
