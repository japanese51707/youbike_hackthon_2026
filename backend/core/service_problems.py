"""
空／滿站緊急時計（core.service_problems）— ADR-318
=================================================
站一進入 empty／full 就開時計；離開空／滿才關。派工不關。
時間一律後端算；規則全部確定性，不經模型。
"""

from __future__ import annotations

import datetime as _dt
import threading
import uuid
from typing import Optional

PROBLEM_KINDS = ("empty", "full")
CLOSE_RECOVERED = "recovered"
CLOSE_KIND_CHANGED = "kind_changed"
WORST_PER_DISTRICT = 3
TAIPEI = _dt.timezone(_dt.timedelta(hours=8))

_lock = threading.Lock()


def _now() -> _dt.datetime:
    return _dt.datetime.now(TAIPEI)


def _aware(moment: _dt.datetime) -> _dt.datetime:
    if moment.tzinfo is None:
        return moment.replace(tzinfo=TAIPEI)
    return moment.astimezone(TAIPEI)


def _iso(moment: _dt.datetime) -> str:
    return _aware(moment).isoformat(timespec="seconds")


def _parse(value) -> Optional[_dt.datetime]:
    if not value:
        return None
    try:
        parsed = _dt.datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    return _aware(parsed)


def _minutes_between(start: Optional[_dt.datetime], end: _dt.datetime) -> float:
    if start is None:
        return 0.0
    return max(0.0, (end - start).total_seconds() / 60.0)


def _round_minutes(value: float) -> float:
    return round(value, 1)


def _mean(values: list[float]) -> Optional[float]:
    if not values:
        return None
    return _round_minutes(sum(values) / len(values))


def _day_start(moment: _dt.datetime) -> _dt.datetime:
    local = _aware(moment)
    return local.replace(hour=0, minute=0, second=0, microsecond=0)


def _problem_id(moment: _dt.datetime) -> str:
    stamp = _iso(moment).replace(":", "").replace("-", "").replace("+", "")
    return f"SP-{stamp}-{uuid.uuid4().hex[:6]}"


def sync_service_problems(stations: list, now: Optional[_dt.datetime] = None) -> list:
    """依完整站況快照開／關空滿時計。空快照不動作（避免上游失敗洗掉時計）。"""
    if not stations:
        return []

    from db import service_problems_repo

    moment = _aware(now or _now())
    need = {}
    for station in stations:
        station_id = station.get("station_id")
        kind = station.get("status")
        if not station_id or kind not in PROBLEM_KINDS:
            continue
        need[station_id] = station

    with _lock:
        open_rows = {row["station_id"]: row for row in service_problems_repo.list_open()}
        stamp = _iso(moment)

        for station_id, row in open_rows.items():
            station = need.get(station_id)
            if station is None:
                service_problems_repo.close_problem(row["problem_id"], CLOSE_RECOVERED, stamp)
            elif station.get("status") != row.get("kind"):
                service_problems_repo.close_problem(
                    row["problem_id"], CLOSE_KIND_CHANGED, stamp)

        for station_id, station in need.items():
            existing = open_rows.get(station_id)
            if existing is not None and existing.get("kind") == station.get("status"):
                continue
            service_problems_repo.open_problem({
                "problem_id": _problem_id(moment),
                "station_id": station_id,
                "station_name": station.get("station_name", ""),
                "district": station.get("district", ""),
                "kind": station.get("status"),
                "opened_at": stamp,
            })

        return service_problems_repo.list_open()


def snapshot(now: Optional[_dt.datetime] = None) -> dict:
    """進行中時計 + 今日已排除彙總（台北日曆日）。"""
    from db import service_problems_repo

    moment = _aware(now or _now())
    day_start = _day_start(moment)
    open_rows = service_problems_repo.list_open()
    closed_rows = service_problems_repo.list_closed_since(_iso(day_start))
    recovered = [row for row in closed_rows if row.get("close_reason") == CLOSE_RECOVERED]

    open_items = []
    for row in open_rows:
        elapsed = _round_minutes(_minutes_between(_parse(row.get("opened_at")), moment))
        open_items.append({
            "problem_id": row.get("problem_id"),
            "station_id": row.get("station_id"),
            "station_name": row.get("station_name") or "",
            "district": row.get("district") or "未分區",
            "kind": row.get("kind"),
            "opened_at": row.get("opened_at"),
            "elapsed_minutes": elapsed,
        })
    open_items.sort(key=lambda item: (-item["elapsed_minutes"], item["station_name"]))

    recovered_items = []
    for row in recovered:
        duration = _round_minutes(_minutes_between(
            _parse(row.get("opened_at")), _parse(row.get("closed_at")) or moment))
        recovered_items.append({
            "problem_id": row.get("problem_id"),
            "station_id": row.get("station_id"),
            "station_name": row.get("station_name") or "",
            "district": row.get("district") or "未分區",
            "kind": row.get("kind"),
            "opened_at": row.get("opened_at"),
            "closed_at": row.get("closed_at"),
            "duration_minutes": duration,
            "open": False,
        })

    districts = _district_rows(open_items, recovered_items)
    city_avg = _mean([item["duration_minutes"] for item in recovered_items])
    longest_open = open_items[0]["elapsed_minutes"] if open_items else None
    longest_empty = _longest_kind(open_items, "empty")
    longest_full = _longest_kind(open_items, "full")

    return {
        "as_of": _iso(moment),
        "today": day_start.date().isoformat(),
        "city": {
            "avg_resolved_minutes": city_avg,
            "resolved_count": len(recovered_items),
            "open_count": len(open_items),
            "longest_open_minutes": longest_open,
            "longest_empty_minutes": longest_empty,
            "longest_full_minutes": longest_full,
        },
        "open": open_items,
        "districts": districts,
    }


def _longest_kind(open_items: list, kind: str) -> Optional[float]:
    matched = [item["elapsed_minutes"] for item in open_items if item.get("kind") == kind]
    return max(matched) if matched else None


def _district_rows(open_items: list, recovered_items: list) -> list:
    names = sorted(
        {item["district"] for item in open_items}
        | {item["district"] for item in recovered_items},
        key=lambda name: name,
    )
    rows = []
    for district in names:
        open_here = [item for item in open_items if item["district"] == district]
        recovered_here = [item for item in recovered_items if item["district"] == district]
        worst = _worst_stations(open_here, recovered_here)
        longest_open = max((item["elapsed_minutes"] for item in open_here), default=None)
        rows.append({
            "district": district,
            "avg_resolved_minutes": _mean([item["duration_minutes"] for item in recovered_here]),
            "resolved_count": len(recovered_here),
            "open_count": len(open_here),
            "longest_open_minutes": longest_open,
            "worst_stations": worst,
        })
    rows.sort(key=lambda row: (
        row["avg_resolved_minutes"] is None,
        -(row["avg_resolved_minutes"] or 0),
        -(row["longest_open_minutes"] or 0),
        row["district"],
    ))
    return rows


def _worst_stations(open_here: list, recovered_here: list) -> list:
    candidates = [
        {
            "station_id": item["station_id"],
            "station_name": item["station_name"],
            "kind": item["kind"],
            "minutes": item["elapsed_minutes"],
            "open": True,
            "opened_at": item["opened_at"],
        }
        for item in open_here
    ]
    candidates.extend({
        "station_id": item["station_id"],
        "station_name": item["station_name"],
        "kind": item["kind"],
        "minutes": item["duration_minutes"],
        "open": False,
        "opened_at": item["opened_at"],
        "closed_at": item["closed_at"],
    } for item in recovered_here)
    candidates.sort(key=lambda item: (-item["minutes"], not item["open"], item["station_name"]))
    return candidates[:WORST_PER_DISTRICT]
