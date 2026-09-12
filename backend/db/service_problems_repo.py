"""
空／滿站緊急時計（db.service_problems_repo）— ADR-324
====================================================
service_problems：以站為單位的空／滿 incident。
opened_at 開案後不再改；同一站同時間只能有一筆未結案。
連線走 clock_connection（ADR-326），與主庫分開。
"""

from __future__ import annotations

from typing import Optional

from db.clock_connection import get_clock_connection


def _row(row) -> Optional[dict]:
    return dict(row) if row is not None else None


def open_problem(problem: dict) -> Optional[dict]:
    conn = get_clock_connection()
    conn.execute(
        """INSERT INTO service_problems
           (problem_id, station_id, station_name, district, kind, opened_at)
           VALUES (:problem_id, :station_id, :station_name, :district, :kind, :opened_at)
           ON CONFLICT DO NOTHING""",
        {
            "problem_id": problem["problem_id"],
            "station_id": problem["station_id"],
            "station_name": problem.get("station_name", ""),
            "district": problem.get("district", ""),
            "kind": problem["kind"],
            "opened_at": problem["opened_at"],
        },
    )
    conn.commit()
    return get_open_by_station(problem["station_id"])


def get_open_by_station(station_id: str) -> Optional[dict]:
    conn = get_clock_connection()
    return _row(conn.execute(
        "SELECT * FROM service_problems WHERE station_id = ? AND closed_at IS NULL",
        (station_id,)).fetchone())


def list_open() -> list:
    conn = get_clock_connection()
    return [dict(r) for r in conn.execute(
        "SELECT * FROM service_problems WHERE closed_at IS NULL ORDER BY opened_at"
    ).fetchall()]


def list_closed_since(started_at: str) -> list:
    conn = get_clock_connection()
    return [dict(r) for r in conn.execute(
        "SELECT * FROM service_problems "
        "WHERE closed_at IS NOT NULL AND closed_at >= ? "
        "ORDER BY closed_at",
        (started_at,),
    ).fetchall()]


def delete_closed_before(cutoff_at: str) -> int:
    """刪掉已結案且關閉時間早於窗口的列（ADR-325）。進行中不刪。"""
    conn = get_clock_connection()
    cur = conn.execute(
        "DELETE FROM service_problems "
        "WHERE closed_at IS NOT NULL AND closed_at < ?",
        (cutoff_at,),
    )
    conn.commit()
    return int(cur.rowcount or 0)


def close_problem(problem_id: str, reason: str, closed_at: str) -> None:
    conn = get_clock_connection()
    conn.execute(
        "UPDATE service_problems SET closed_at = ?, close_reason = ? "
        "WHERE problem_id = ? AND closed_at IS NULL",
        (closed_at, reason, problem_id),
    )
    conn.commit()
