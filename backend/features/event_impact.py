"""
事件因子（features.event_impact）— ADR-012（選項 A：介面先行）
================================================================
活動/路跑/馬拉松等動態事件會短時間大幅改變周邊站點需求。這類是逐次資料、
無現成歷史 API，故採「事件資料表」介面：結構先建好，歷史資料事後補、現場可填。

事件資料檔 events_data.json（初期空表 + 格式範例）。每筆事件：
  event_id, name, type(活動/路跑/馬拉松...), date, start_time, end_time,
  lat, lng, expected_attendance, influence_radius_km

特徵計算：給定站點座標 + 時間 → 該時刻是否有事件影響、影響強度（依距離與規模）。
影響強度轉換係數初期粗估（ADR-011/012），之後校準。

對外暴露：
    get_active_events(date) -> list             # 某日進行中的事件
    get_event_feature(lat, lng, timestamp)      # 站點該時刻的事件影響特徵
    add_event(event)                            # 新增事件（現場/補資料用）
"""

from __future__ import annotations
import datetime as _dt
import json
import math
from pathlib import Path

_EVENTS_PATH = Path(__file__).parent / "events_data.json"


def _load() -> list[dict]:
    if not _EVENTS_PATH.exists():
        return []
    return json.loads(_EVENTS_PATH.read_text(encoding="utf-8")).get("events", [])


def _save(events: list[dict]) -> None:
    _EVENTS_PATH.write_text(
        json.dumps({"_說明": "事件資料表（活動/路跑/馬拉松），ADR-012 選項A介面先行，資料事後補。",
                    "events": events}, ensure_ascii=False, indent=1),
        encoding="utf-8")


def _haversine(lat1, lng1, lat2, lng2) -> float:
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


def add_event(event: dict) -> dict:
    """新增一筆事件（現場或補歷史資料用）。需含 name/date/lat/lng。"""
    for k in ("name", "date", "lat", "lng"):
        if k not in event:
            raise ValueError(f"事件缺必要欄位：{k}")
    events = _load()
    event.setdefault("event_id", f"EVT-{event['date'].replace('-', '')}-{len(events) + 1:03d}")
    event.setdefault("type", "活動")
    event.setdefault("influence_radius_km", 1.0)
    event.setdefault("expected_attendance", 0)
    events.append(event)
    _save(events)
    return event


def get_active_events(date: str) -> list[dict]:
    """某日期進行中的事件。"""
    d = str(date)[:10]
    return [e for e in _load() if str(e.get("date", ""))[:10] == d]


def get_event_feature(lat: float, lng: float, timestamp: str) -> dict:
    """站點該時刻的事件影響特徵。

    無事件時 has_event=False、強度 0（多數日子如此，屬正常）。
    有事件且站點在影響半徑內 → 依「距離越近、規模越大」給影響強度（0~1 粗估）。
    """
    date = str(timestamp)[:10]
    events = get_active_events(date)
    if not events:
        return {"has_event": False, "event_influence": 0.0, "nearest_event": None}

    best_influence = 0.0
    nearest = None
    for e in events:
        dist = _haversine(lat, lng, e["lat"], e["lng"])
        radius = float(e.get("influence_radius_km", 1.0))
        if dist <= radius:
            # 影響 = (1 - 距離/半徑) × 規模因子（人數正規化，粗估）
            proximity = 1 - dist / radius
            scale = min(1.0, float(e.get("expected_attendance", 0)) / 10000.0)
            influence = round(proximity * (0.5 + 0.5 * scale), 3)
            if influence > best_influence:
                best_influence = influence
                nearest = {"name": e["name"], "type": e.get("type"),
                           "distance_km": round(dist, 3)}
    return {
        "has_event": best_influence > 0,
        "event_influence": best_influence,
        "nearest_event": nearest,
    }
