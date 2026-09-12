"""
緊急調度案件與稽核軌跡（db.escalation_repo）— ADR-309
=======================================================
alert_cases      ：以站為單位的案件，opened_at 不隨警示重建而改變
alert_case_actions：每一次人為動作（已讀／已電話聯絡／延後／轉組單）的稽核軌跡

同一站同時間只能有一個未結案案件——靠 partial unique index 由資料庫保證，
不靠應用層自律（兩個分頁同時開案是真的會發生的）。
"""

from __future__ import annotations

from typing import Optional

from db.connection import get_connection


def _row(row) -> dict:
    return dict(row) if row is not None else None


def open_case(case: dict) -> dict:
    conn = get_connection()
    conn.execute(
        """INSERT INTO alert_cases
           (case_id, station_id, station_name, district, opened_at,
            trigger_reason, suggested_action, highest_stage)
           VALUES (:case_id, :station_id, :station_name, :district, :opened_at,
                   :trigger_reason, :suggested_action, 0)
           ON CONFLICT DO NOTHING""",
        {
            "case_id": case["case_id"],
            "station_id": case["station_id"],
            "station_name": case.get("station_name", ""),
            "district": case.get("district", ""),
            "opened_at": case["opened_at"],
            "trigger_reason": case.get("trigger_reason"),
            "suggested_action": case.get("suggested_action"),
        },
    )
    conn.commit()
    return get_open_case_by_station(case["station_id"])


def get_case(case_id: str) -> Optional[dict]:
    conn = get_connection()
    return _row(conn.execute(
        "SELECT * FROM alert_cases WHERE case_id = ?", (case_id,)).fetchone())


def get_open_case_by_station(station_id: str) -> Optional[dict]:
    conn = get_connection()
    return _row(conn.execute(
        "SELECT * FROM alert_cases WHERE station_id = ? AND closed_at IS NULL",
        (station_id,)).fetchone())


def list_open_cases() -> list:
    conn = get_connection()
    return [dict(r) for r in conn.execute(
        "SELECT * FROM alert_cases WHERE closed_at IS NULL ORDER BY opened_at").fetchall()]


def list_cases(limit: int = 200, include_closed: bool = True) -> list:
    conn = get_connection()
    sql = "SELECT * FROM alert_cases"
    if not include_closed:
        sql += " WHERE closed_at IS NULL"
    sql += " ORDER BY opened_at DESC LIMIT ?"
    return [dict(r) for r in conn.execute(sql, (int(limit),)).fetchall()]


def close_case(case_id: str, reason: str, closed_at: str) -> None:
    conn = get_connection()
    conn.execute(
        "UPDATE alert_cases SET closed_at = ?, close_reason = ? "
        "WHERE case_id = ? AND closed_at IS NULL",
        (closed_at, reason, case_id))
    conn.commit()


def mute_case(case_id: str, muted_until: str) -> None:
    conn = get_connection()
    conn.execute("UPDATE alert_cases SET muted_until = ? WHERE case_id = ?",
                 (muted_until, case_id))
    conn.commit()


def set_highest_stage(case_id: str, stage: int) -> None:
    conn = get_connection()
    conn.execute(
        "UPDATE alert_cases SET highest_stage = ? WHERE case_id = ? AND highest_stage < ?",
        (int(stage), case_id, int(stage)))
    conn.commit()


def insert_action(action: dict) -> None:
    conn = get_connection()
    conn.execute(
        """INSERT INTO alert_case_actions
           (action_id, case_id, action, actor, stage, note, contact, created_at)
           VALUES (:action_id, :case_id, :action, :actor, :stage, :note, :contact, :created_at)""",
        action)
    conn.commit()


def list_actions(case_id: Optional[str] = None, limit: int = 200) -> list:
    conn = get_connection()
    if case_id:
        rows = conn.execute(
            "SELECT * FROM alert_case_actions WHERE case_id = ? ORDER BY created_at",
            (case_id,)).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM alert_case_actions ORDER BY created_at DESC LIMIT ?",
            (int(limit),)).fetchall()
    return [dict(r) for r in rows]
