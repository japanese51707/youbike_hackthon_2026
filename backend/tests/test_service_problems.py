"""
ADR-324 空／滿站緊急時計
========================
守住：一出現就開時計、再開不重置、派工不關、恢復才算排除、空↔滿不計入平均。
"""
from __future__ import annotations

import datetime as _dt

from core import service_problems as sp
from db import service_problems_repo

T0 = _dt.datetime(2026, 9, 12, 9, 0, 0, tzinfo=sp.TAIPEI)
T1 = T0 + _dt.timedelta(minutes=20)
T2 = T0 + _dt.timedelta(minutes=50)


def _station(station_id="S1", status="empty", district="板橋區", name=None):
    return {
        "station_id": station_id,
        "station_name": name or f"測試站{station_id}",
        "district": district,
        "status": status,
    }


def test_empty_station_opens_a_clock():
    opened = sp.sync_service_problems([_station()], now=T0)
    assert len(opened) == 1
    assert opened[0]["kind"] == "empty"
    assert opened[0]["opened_at"] == T0.isoformat(timespec="seconds")


def test_resync_does_not_reset_opened_at():
    sp.sync_service_problems([_station()], now=T0)
    later = sp.sync_service_problems([_station()], now=T1)
    assert later[0]["opened_at"] == T0.isoformat(timespec="seconds")
    snap = sp.snapshot(now=T1)
    assert snap["open"][0]["elapsed_minutes"] == 20.0


def test_dispatch_does_not_close_the_clock():
    """派工不是排除——站還空著時計就要繼續走。"""
    sp.sync_service_problems([_station()], now=T0)
    still = sp.sync_service_problems([_station()], now=T1)
    assert len(still) == 1
    assert service_problems_repo.get_open_by_station("S1") is not None


def test_recovery_closes_and_counts_toward_today_average():
    sp.sync_service_problems([_station()], now=T0)
    after = sp.sync_service_problems([_station(status="normal")], now=T1)
    assert after == []
    snap = sp.snapshot(now=T1)
    assert snap["city"]["resolved_count"] == 1
    assert snap["city"]["avg_resolved_minutes"] == 20.0
    assert snap["districts"][0]["district"] == "板橋區"
    assert snap["districts"][0]["avg_resolved_minutes"] == 20.0


def test_empty_to_full_is_not_resolution():
    sp.sync_service_problems([_station(status="empty")], now=T0)
    after = sp.sync_service_problems([_station(status="full")], now=T1)
    assert len(after) == 1
    assert after[0]["kind"] == "full"
    assert after[0]["opened_at"] == T1.isoformat(timespec="seconds")
    snap = sp.snapshot(now=T1)
    assert snap["city"]["resolved_count"] == 0
    assert snap["city"]["avg_resolved_minutes"] is None


def test_empty_snapshot_does_not_close_open_clocks():
    sp.sync_service_problems([_station()], now=T0)
    sp.sync_service_problems([], now=T1)
    assert service_problems_repo.get_open_by_station("S1") is not None


def test_worst_stations_prefer_longest_open():
    sp.sync_service_problems([
        _station("A", "empty", "板橋區", "長空"),
        _station("B", "full", "板橋區", "短滿"),
        _station("C", "empty", "中和區", "他區"),
    ], now=T0)
    sp.sync_service_problems([
        _station("A", "empty", "板橋區", "長空"),
        _station("B", "normal", "板橋區", "短滿"),
        _station("C", "empty", "中和區", "他區"),
    ], now=T1)
    snap = sp.snapshot(now=T2)
    banqiao = next(row for row in snap["districts"] if row["district"] == "板橋區")
    assert banqiao["worst_stations"][0]["station_name"] == "長空"
    assert banqiao["worst_stations"][0]["open"] is True
    assert banqiao["worst_stations"][0]["minutes"] == 50.0
    assert any(item["station_name"] == "短滿" and item["open"] is False
               for item in banqiao["worst_stations"])


def test_snapshot_uses_rolling_window_not_calendar_midnight():
    """25 小時前結案的不進平均；窗口內的才算。"""
    old = T0 - _dt.timedelta(hours=25)
    sp.sync_service_problems([_station("OLD", "empty")], now=old)
    sp.sync_service_problems([_station("OLD", "normal")], now=old + _dt.timedelta(minutes=10))
    sp.sync_service_problems([_station("NEW", "empty")], now=T0)
    sp.sync_service_problems([_station("NEW", "normal")], now=T1)
    snap = sp.snapshot(now=T1)
    assert snap["window_hours"] == 24
    assert snap["city"]["resolved_count"] == 1
    assert snap["city"]["avg_resolved_minutes"] == 20.0


def test_start_background_skips_when_external_worker(monkeypatch):
    monkeypatch.setenv("SERVICE_CLOCK_EXTERNAL", "1")
    assert sp.start_background("youbike_official") is False


def test_start_background_skips_when_in_app_false(monkeypatch):
    from config_loader import get_config
    cfg = get_config()
    monkeypatch.setitem(cfg.setdefault("service_problems", {}), "in_app", False)
    monkeypatch.setitem(cfg["service_problems"], "enabled", True)
    assert sp.start_background("youbike_official") is False


def test_corrupt_clock_file_is_rebuilt(tmp_path, monkeypatch):
    from db.clock_connection import get_clock_connection, reset_clock_connection

    clock = tmp_path / "service_clock.db"
    clock.write_text("this is not sqlite", encoding="utf-8")
    monkeypatch.setenv("YOUBIKE_CLOCK_DB_PATH", str(clock))
    reset_clock_connection()
    conn = get_clock_connection()
    conn.execute("SELECT COUNT(*) FROM service_problems").fetchone()
    conn.execute("SELECT COUNT(*) FROM station_snapshots").fetchone()
    assert clock.exists()
    assert clock.read_bytes()[:15] == b"SQLite format 3"


def test_clock_writes_dedicated_file_not_memory_main(tmp_path, monkeypatch):
    """YOUBIKE_CLOCK_DB_PATH 指向檔案時，時計不進主記憶體庫。"""
    from db.clock_connection import clock_db_path, reset_clock_connection
    from db.connection import get_connection

    clock = tmp_path / "service_clock.db"
    monkeypatch.setenv("YOUBIKE_CLOCK_DB_PATH", str(clock))
    reset_clock_connection()
    assert clock_db_path() == str(clock)

    sp.sync_service_problems([_station()], now=T0)
    assert service_problems_repo.get_open_by_station("S1") is not None
    assert clock.exists()
    main_count = get_connection().execute(
        "SELECT COUNT(*) FROM service_problems").fetchone()[0]
    assert main_count == 0


def test_snapshot_does_not_require_a_full_24h():
    """窗口內有一筆排除就顯示，不必等滿 24 小時。"""
    sp.sync_service_problems([_station()], now=T0)
    sp.sync_service_problems([_station(status="normal")], now=T1)
    snap = sp.snapshot(now=T1)
    assert snap["city"]["resolved_count"] == 1
    assert snap["city"]["avg_resolved_minutes"] == 20.0
    assert snap["history"]["poll_count"] == 0


def test_record_station_history_keeps_rolling_24h():
    from db import station_snapshots_repo

    old = T0 - _dt.timedelta(hours=25)
    sp.record_station_history([
        {**_station("OLD"), "available_bikes": 0, "available_docks": 10, "total_docks": 10},
    ], now=old)
    sp.record_station_history([
        {**_station("NEW"), "status": "normal", "available_bikes": 5,
         "available_docks": 5, "total_docks": 10},
    ], now=T0)
    cover = station_snapshots_repo.coverage(T0.isoformat(timespec="seconds"))
    assert cover["station_count"] == 1
    assert cover["poll_count"] == 1
    points = station_snapshots_repo.list_for_station("NEW")
    assert len(points) == 1
    assert points[0]["available_bikes"] == 5


def test_stale_snapshot_is_not_stored():
    from db import station_snapshots_repo

    result = sp.record_station_history([
        {**_station(), "data_freshness": "stale", "available_bikes": 0,
         "available_docks": 10, "total_docks": 10},
    ], now=T0)
    assert result["recorded"] == 0
    assert station_snapshots_repo.coverage()["poll_count"] == 0


def test_prune_deletes_closed_outside_window_but_keeps_open():
    old = T0 - _dt.timedelta(hours=25)
    sp.sync_service_problems([_station("OLD", "empty")], now=old)
    sp.sync_service_problems([_station("OLD", "normal")], now=old + _dt.timedelta(minutes=10))
    sp.sync_service_problems([_station("LIVE", "empty")], now=T0)
    deleted = sp.prune_older_than(now=T1, hours=24)
    assert deleted == 1
    assert service_problems_repo.get_open_by_station("LIVE") is not None
    assert service_problems_repo.list_closed_since(old.isoformat(timespec="seconds")) == []
