"""
近 24 小時站況快照（db.station_snapshots_repo）— ADR-328
=======================================================
背景收集每次完整站況；逾窗刪除。不進派工決策。
"""

from __future__ import annotations

from typing import Optional

from db.clock_connection import get_clock_connection


def record_snapshots(stations: list, observed_at: str) -> int:
    """寫入一輪完整站況。同一觀察時間重跑則覆蓋。"""
    if not stations or not observed_at:
        return 0
    rows = []
    for station in stations:
        station_id = station.get("station_id")
        if not station_id:
            continue
        rows.append((
            observed_at,
            station_id,
            station.get("station_name") or "",
            station.get("district") or "",
            station.get("status") or "",
            _int(station.get("available_bikes")),
            _int(station.get("available_docks")),
            _int(station.get("total_docks")),
        ))
    if not rows:
        return 0
    conn = get_clock_connection()
    conn.executemany(
        """INSERT INTO station_snapshots
           (observed_at, station_id, station_name, district, status,
            available_bikes, available_docks, total_docks)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(observed_at, station_id) DO UPDATE SET
             station_name=excluded.station_name,
             district=excluded.district,
             status=excluded.status,
             available_bikes=excluded.available_bikes,
             available_docks=excluded.available_docks,
             total_docks=excluded.total_docks""",
        rows,
    )
    conn.commit()
    return len(rows)


def delete_before(cutoff_at: str) -> int:
    """刪掉觀察時間早於窗口的快照。"""
    conn = get_clock_connection()
    cur = conn.execute(
        "DELETE FROM station_snapshots WHERE observed_at < ?",
        (cutoff_at,),
    )
    conn.commit()
    return int(cur.rowcount or 0)


def coverage(since: Optional[str] = None) -> dict:
    conn = get_clock_connection()
    if since:
        row = conn.execute(
            "SELECT COUNT(DISTINCT observed_at), COUNT(DISTINCT station_id), "
            "MIN(observed_at), MAX(observed_at) "
            "FROM station_snapshots WHERE observed_at >= ?",
            (since,),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT COUNT(DISTINCT observed_at), COUNT(DISTINCT station_id), "
            "MIN(observed_at), MAX(observed_at) FROM station_snapshots"
        ).fetchone()
    return {
        "poll_count": int(row[0] or 0),
        "station_count": int(row[1] or 0),
        "first_observed_at": row[2],
        "last_observed_at": row[3],
    }


def latest_status_counts() -> dict:
    conn = get_clock_connection()
    latest = conn.execute(
        "SELECT MAX(observed_at) FROM station_snapshots").fetchone()[0]
    if not latest:
        return {}
    rows = conn.execute(
        "SELECT status, COUNT(*) FROM station_snapshots "
        "WHERE observed_at = ? GROUP BY status",
        (latest,),
    ).fetchall()
    return {row[0]: int(row[1]) for row in rows}


def list_for_station(station_id: str, since: Optional[str] = None) -> list:
    conn = get_clock_connection()
    if since:
        rows = conn.execute(
            "SELECT * FROM station_snapshots "
            "WHERE station_id = ? AND observed_at >= ? ORDER BY observed_at",
            (station_id, since),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM station_snapshots "
            "WHERE station_id = ? ORDER BY observed_at",
            (station_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def _int(value) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
