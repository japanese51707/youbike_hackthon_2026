"""騎乘者故障通報（示範信箱）。只累加站點數量，不觸發派工。"""

from __future__ import annotations

from datetime import datetime, timezone
from threading import Lock

_lock = Lock()
_summaries: dict[str, dict] = {}

QUANTITY_ISSUES = {"bike", "dock"}


def reset_rider_faults() -> None:
    with _lock:
        _summaries.clear()


def _empty(station_id: str, station_name: str | None = None) -> dict:
    return {
        "station_id": station_id,
        "station_name": station_name or station_id,
        "bikes": 0,
        "docks": 0,
        "station_down": False,
        "other": 0,
        "updated_at": None,
    }


def list_summaries() -> list[dict]:
    with _lock:
        return [dict(row) for row in _summaries.values()]


def get_summary(station_id: str) -> dict | None:
    with _lock:
        row = _summaries.get(station_id)
        return dict(row) if row else None


def add_report(
    station_id: str,
    issue: str,
    add_quantity: int = 1,
    station_name: str | None = None,
    note: str | None = None,
) -> dict:
    qty = max(1, min(10, int(add_quantity)))
    now = datetime.now(timezone.utc).isoformat()
    with _lock:
        row = _summaries.get(station_id) or _empty(station_id, station_name)
        if station_name:
            row["station_name"] = station_name
        if issue == "bike":
            row["bikes"] += qty
        elif issue == "dock":
            row["docks"] += qty
        elif issue == "station":
            row["station_down"] = True
        else:
            row["other"] += 1
        row["updated_at"] = now
        _summaries[station_id] = row
        summary = dict(row)
    return {
        "summary": summary,
        "added": {
            "station_id": station_id,
            "issue": issue,
            "quantity": qty if issue in QUANTITY_ISSUES else None,
            "note": note,
            "reported_at": now,
        },
    }
