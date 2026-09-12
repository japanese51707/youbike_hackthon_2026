"""道路實走路線（把站點順序轉成沿著道路的折線幾何）。

定位與界線
----------
這是**呈現層**服務：只負責「畫線」。停靠順序、載量切趟、可行性判斷一律由
dispatcher／dispatch_guards 決定（ADR-117/123），本模組不回頭影響任何調度決策，
所以路由服務掛掉也不會讓派工變不準——只是線畫得比較醜。

可抽換供應者（比照 ADR-006 DataSource）
------------------------------------
config `routing.providers` 依序嘗試；全部失敗就明確降級成直線，回應帶
`mode="straight"`，前端必須照實顯示「直線示意」，不可假裝是實走路線
（ADR-006：降級不等於成功）。

支援的供應者：
- `osrm`      公開 OSRM（無金鑰）。回 GeoJSON，最單純。
- `valhalla`  FOSSGIS 公開 Valhalla（無金鑰）。回 polyline6，需解碼。

兩者都是公益服務，僅適合 demo 流量；正式營運應自架或改用商用路由服務，
換供應者只要改 config，不動呼叫端。
"""

from __future__ import annotations

import threading
import time
from typing import Iterable, Optional

import httpx

from config_loader import get_config

# 座標快取：同一組站點順序不重複打外部服務。
# 派工單一旦確認就不會變，命中率很高。
_CACHE: dict[tuple, tuple[float, dict]] = {}
_CACHE_LOCK = threading.Lock()


def _cfg() -> dict:
    return (get_config().get("routing") or {})


def _providers() -> list[str]:
    value = _cfg().get("providers") or ["osrm"]
    return [str(p).strip().lower() for p in value if str(p).strip()]


def _timeout() -> float:
    return float(_cfg().get("逾時秒數", 6))


def _cache_ttl() -> float:
    return float(_cfg().get("快取秒數", 1800))


def _max_points() -> int:
    return int(_cfg().get("單次最多座標數", 25))


def _round(coordinates: Iterable[Iterable[float]]) -> list[list[float]]:
    """座標取到小數 5 位（約 1 公尺）。多餘精度只會降低快取命中率。"""
    out = []
    for point in coordinates:
        lng, lat = float(point[0]), float(point[1])
        out.append([round(lng, 5), round(lat, 5)])
    return out


def _straight(coordinates: list[list[float]], note: str) -> dict:
    return {
        "mode": "straight",
        "provider": None,
        "geometry": coordinates,
        "distance_m": None,
        "duration_s": None,
        "note": note,
    }


# ── polyline6 解碼（Valhalla 用）────────────────────────────────────────

def _decode_polyline6(encoded: str) -> list[list[float]]:
    """Google polyline 演算法，精度 1e-6（Valhalla 預設）。回 [[lng, lat], ...]。"""
    coordinates: list[list[float]] = []
    index = lat = lng = 0
    length = len(encoded)
    while index < length:
        for target in ("lat", "lng"):
            shift = result = 0
            while True:
                if index >= length:
                    return coordinates
                byte = ord(encoded[index]) - 63
                index += 1
                result |= (byte & 0x1F) << shift
                shift += 5
                if byte < 0x20:
                    break
            delta = ~(result >> 1) if result & 1 else (result >> 1)
            if target == "lat":
                lat += delta
            else:
                lng += delta
        coordinates.append([lng / 1e6, lat / 1e6])
    return coordinates


# ── 供應者實作 ─────────────────────────────────────────────────────────

def _via_osrm(coordinates: list[list[float]]) -> Optional[dict]:
    base = str(_cfg().get("osrm_base_url") or "https://router.project-osrm.org").rstrip("/")
    path = ";".join(f"{lng},{lat}" for lng, lat in coordinates)
    url = f"{base}/route/v1/driving/{path}"
    response = httpx.get(
        url,
        params={"overview": "full", "geometries": "geojson", "steps": "false"},
        timeout=_timeout(),
        follow_redirects=True,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("code") != "Ok" or not payload.get("routes"):
        return None
    route = payload["routes"][0]
    geometry = (route.get("geometry") or {}).get("coordinates") or []
    if len(geometry) < 2:
        return None
    return {
        "mode": "road",
        "provider": "osrm",
        "geometry": [[float(x), float(y)] for x, y in geometry],
        "distance_m": route.get("distance"),
        "duration_s": route.get("duration"),
        "note": None,
    }


def _via_valhalla(coordinates: list[list[float]]) -> Optional[dict]:
    base = str(_cfg().get("valhalla_base_url") or "https://valhalla1.openstreetmap.de").rstrip("/")
    body = {
        "locations": [{"lat": lat, "lon": lng} for lng, lat in coordinates],
        "costing": "truck",
        "directions_options": {"units": "kilometers"},
    }
    response = httpx.post(f"{base}/route", json=body, timeout=_timeout(), follow_redirects=True)
    response.raise_for_status()
    trip = (response.json() or {}).get("trip") or {}
    geometry: list[list[float]] = []
    for leg in trip.get("legs") or []:
        shape = leg.get("shape")
        if not shape:
            continue
        points = _decode_polyline6(shape)
        # 相鄰 leg 的接點重複，去掉一個免得折線多一個重複節點
        geometry.extend(points[1:] if geometry and points else points)
    if len(geometry) < 2:
        return None
    summary = trip.get("summary") or {}
    distance_km = summary.get("length")
    return {
        "mode": "road",
        "provider": "valhalla",
        "geometry": geometry,
        "distance_m": float(distance_km) * 1000 if distance_km is not None else None,
        "duration_s": summary.get("time"),
        "note": None,
    }


_PROVIDERS = {"osrm": _via_osrm, "valhalla": _via_valhalla}


# ── 對外入口 ───────────────────────────────────────────────────────────

def road_route(coordinates: list[list[float]]) -> dict:
    """回傳沿道路的折線幾何；任何失敗都降級成直線並標明 mode。

    coordinates：[[lng, lat], ...]，已是要走的順序（起點在第一個）。
    """
    points = _round(coordinates)
    if len(points) < 2:
        return _straight(points, "座標不足兩點")
    limit = _max_points()
    if len(points) > limit:
        return _straight(points, f"座標數超過單次上限 {limit}")

    key = tuple(tuple(p) for p in points)
    now = time.time()
    with _CACHE_LOCK:
        hit = _CACHE.get(key)
        if hit and now - hit[0] < _cache_ttl():
            return hit[1]

    errors = []
    for name in _providers():
        fn = _PROVIDERS.get(name)
        if fn is None:
            errors.append(f"{name}: 未支援")
            continue
        try:
            result = fn(points)
            if result:
                with _CACHE_LOCK:
                    _CACHE[key] = (now, result)
                    # 粗略上限，避免長時間執行把記憶體吃光
                    if len(_CACHE) > 500:
                        oldest = sorted(_CACHE.items(), key=lambda kv: kv[1][0])[:100]
                        for stale_key, _ in oldest:
                            _CACHE.pop(stale_key, None)
                return result
            errors.append(f"{name}: 無可用路線")
        except Exception as exc:  # 路由服務不可用不該讓派工畫面壞掉
            errors.append(f"{name}: {type(exc).__name__}")

    return _straight(points, "；".join(errors) or "沒有可用的路由供應者")


def clear_cache() -> None:
    with _CACHE_LOCK:
        _CACHE.clear()
