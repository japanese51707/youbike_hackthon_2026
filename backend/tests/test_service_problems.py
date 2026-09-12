"""
ADR-318 空／滿站緊急時計
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
