"""供車站（donor）：可以借出車輛、但自己沒有出事的站。

為什麼需要這個
--------------
原本的車源只能從「規則引擎已標記為取車的站」來（dispatch_list 內 action=="取車"）。
但早尖峰全市幾乎都是空站／補車，**沒有任何站被標成取車**，於是車源結構性為 0，
每一張補車單都會判定「附近無足夠車源」。那不是「附近真的沒車」，
而是「附近沒有正在出事的滿站」——這兩件事完全不同。

供車站補上這個缺口：任何水位高於目標水位、而且借走幾台之後仍在安全緩衝以上的站，
都可以當車源。一個 85% 滿的站不是緊急取車點，但它是完美的取車地點。

界線
----
- 供車站**不進緊急度清單、不算調度需求**。它只是「順路去拿車的地方」。
- 借出量保守估：借走後水位仍要高於（目標水位 + 安全緩衝），不把供車站變成下一個空站。
- 資料不新鮮／停用／已被其他任務認領的站一律不當供車站。
"""

from __future__ import annotations

import threading
import time
from typing import Iterable, Optional

_CACHE_LOCK = threading.Lock()
_CACHE: dict[str, tuple[float, list[dict]]] = {}


def _int(value, default=None):
    try:
        if value is None:
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _haversine_km(lat1, lng1, lat2, lng2) -> float:
    from core.dispatcher import _haversine_km as h
    return h(lat1, lng1, lat2, lng2)


def donor_candidates(
    stations: Iterable[dict],
    exclude_ids: set[str],
    cfg: dict,
    *,
    near_lat=None,
    near_lng=None,
    district: Optional[str] = None,
    limit: int = 8,
) -> list[dict]:
    """從全市站況挑出可借車的供車站，回傳與 dispatch_list 同形狀的「取車」條目。

    exclude_ids：已在需調度清單、已被任務認領、或本趟已納入的站，一律排除。
    district：有給就把同區的排在前面（同區優先、跨區次之，ADR-316）。
    """
    target_cfg = cfg.get("target", {}) or {}
    fleet_cfg = cfg.get("fleet", {}) or {}
    target_pct = float(target_cfg.get("預設借用率百分比", 50)) / 100.0
    buffer_ratio = float(target_cfg.get("安全緩衝_比例", 0.12))
    min_take = int(fleet_cfg.get("供車站最少可取_台數", 3))
    max_take = int(fleet_cfg.get("供車站單站最多取_台數", 10))

    out: list[dict] = []
    for station in stations:
        sid = str(station.get("station_id") or "")
        if not sid or sid in exclude_ids:
            continue
        # 停用／離線／資料不新鮮的站不當車源（與規則引擎同一組排除條件）
        if (station.get("service_available") is False
                or station.get("status") == "offline"
                or station.get("dispatch_eligible") is False
                or station.get("data_freshness") in ("stale", "historical", "historical_fallback")):
            continue
        total = _int(station.get("total_docks"))
        avail = _int(station.get("available_bikes"))
        if not total or total <= 0 or avail is None:
            continue
        # 借走之後仍要留在「目標水位 + 安全緩衝」之上
        keep = total * target_pct + max(2, round(total * buffer_ratio))
        take = int(avail - keep)
        if take < min_take:
            continue
        take = min(take, max_take)
        out.append({
            "station_id": sid,
            "station_name": station.get("station_name") or sid,
            "district": station.get("district"),
            "action": "取車",
            "quantity": take,
            "priority_score": 0.0,          # 供車站沒有緊急度，不參與排序打底
            "priority_level": "low",
            "reason": f"供車站：目前 {avail}/{total} 台，可借出 {take} 台仍在安全水位以上",
            "current_available": avail,
            "total_docks": total,
            "target_available": float(round(avail - take, 1)),
            "lat": station.get("lat"),
            "lng": station.get("lng"),
            "is_donor": True,               # 供車站標記：前端可顯示成不同顏色
        })

    def sort_key(row):
        same_district = 0 if (district and row.get("district") == district) else 1
        if near_lat is not None and row.get("lat") is not None:
            distance = _haversine_km(near_lat, near_lng, row.get("lat"), row.get("lng"))
        else:
            distance = 0.0
        # 同區優先 → 近的優先 → 可借多的優先
        return (same_district, round(distance, 2), -int(row.get("quantity", 0)))

    out.sort(key=sort_key)
    return out[:limit]


def get_all_stations(ttl_sec: float = 60.0) -> list[dict]:
    """全市站況（短 TTL 快取）。

    自動配單會對每個緊急站各呼叫一次組單，若每次都重抓全市站況會非常浪費；
    這裡用 60 秒快取擋住重複讀取（官方即時源本來就約 5 分鐘才更新一次）。
    """
    now = time.time()
    with _CACHE_LOCK:
        hit = _CACHE.get("all")
        if hit and now - hit[0] < ttl_sec:
            return hit[1]
    try:
        from core.data.degradation import get_stations_with_degradation
        stations = get_stations_with_degradation()
    except Exception:  # 站況拿不到就當作沒有供車站，不讓組單掛掉
        stations = []
    with _CACHE_LOCK:
        _CACHE["all"] = (now, stations)
    return stations


def clear_cache() -> None:
    with _CACHE_LOCK:
        _CACHE.clear()
