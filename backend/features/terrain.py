"""
地形因子（features.terrain）— ADR-011
======================================
用站點座標查高程，估算局部坡度，套 config.terrain_thresholds 分類。
地形影響騎乘意願（上坡站點借車意願低、還車意願高，反之亦然）。

坡度估法：
  查站點中心 + 四個方向（東西南北）各約 100m 的點的高程，
  取「最大高程差 / 水平距離」當局部坡度（%）。單點高程不足以表達坡度，需周邊點。

高程資料源：Open-Elevation 公開 API（免金鑰）。
  查詢結果快取到本地 JSON，避免每次重複打 API（1576 站不需每次查）。
  正式可換政府 DEM（更精確），介面不變。

分類（config.terrain_thresholds，坡度%）：
  flat(<flat_max) / gentle(<gentle_max) / moderate(<moderate_max) / steep(其餘)

對外暴露：
    classify_slope(slope_pct) -> str            # 坡度% → 分類
    get_terrain(lat, lng) -> dict               # 單站地形特徵（高程/坡度/分類）
"""

from __future__ import annotations
import json
import math
import os
from pathlib import Path
from typing import Optional

# 高程查詢快取（避免重複打 API）
_CACHE_PATH = Path(__file__).parent / "_elevation_cache.json"
_ELEVATION_API = "https://api.open-elevation.com/api/v1/lookup"

# 估坡度用的偏移距離（公尺）與地球換算
_OFFSET_M = 100.0
_M_PER_DEG_LAT = 111_320.0   # 緯度 1 度約 111.32 km


def _thresholds() -> dict:
    from config_loader import get_config
    return get_config().get("terrain_thresholds",
                            {"flat_max": 3, "gentle_max": 5, "moderate_max": 8})


def classify_slope(slope_pct: float) -> str:
    """坡度百分比 → 地形分類（對齊 config 門檻）。"""
    t = _thresholds()
    if slope_pct < t["flat_max"]:
        return "flat"
    if slope_pct < t["gentle_max"]:
        return "gentle"
    if slope_pct < t["moderate_max"]:
        return "moderate"
    return "steep"


def _load_cache() -> dict:
    if _CACHE_PATH.exists():
        return json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
    return {}


def _save_cache(cache: dict) -> None:
    _CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")


def _query_elevations(points: list[tuple[float, float]]) -> list[Optional[float]]:
    """批次查多點高程。回傳對應高程 list（查不到為 None）。"""
    import httpx
    loc = "|".join(f"{lat},{lng}" for lat, lng in points)
    try:
        r = httpx.get(f"{_ELEVATION_API}?locations={loc}", timeout=20)
        r.raise_for_status()
        return [item.get("elevation") for item in r.json().get("results", [])]
    except Exception:
        # 失敗不靜默給 0（NFR-5）：回 None，讓上層知道拿不到
        return [None] * len(points)


def get_terrain(lat: float, lng: float, use_cache: bool = True) -> dict:
    """回傳單站地形特徵：高程、局部坡度(%)、分類。

    查中心 + 東西南北各 ~100m 共 5 點，用最大高程差/水平距離估坡度。
    查不到高程時 slope=None、terrain_class="unknown"（明確標示，不假裝 flat）。
    """
    key = f"{round(lat, 5)},{round(lng, 5)}"
    cache = _load_cache() if use_cache else {}
    if key in cache:
        return cache[key]

    # 中心 + 四方向偏移點
    dlat = _OFFSET_M / _M_PER_DEG_LAT
    dlng = _OFFSET_M / (_M_PER_DEG_LAT * math.cos(math.radians(lat)))
    points = [
        (lat, lng),                # 中心
        (lat + dlat, lng),         # 北
        (lat - dlat, lng),         # 南
        (lat, lng + dlng),         # 東
        (lat, lng - dlng),         # 西
    ]
    elevs = _query_elevations(points)
    valid = [e for e in elevs if e is not None]

    if len(valid) < 2:
        result = {"elevation": (valid[0] if valid else None),
                  "slope_pct": None, "terrain_class": "unknown"}
    else:
        center = elevs[0] if elevs[0] is not None else valid[0]
        # 最大高程差（中心 vs 周邊），除以偏移距離 → 坡度%
        max_diff = max(abs(center - e) for e in valid if e is not None)
        slope_pct = round(max_diff / _OFFSET_M * 100, 2)
        result = {
            "elevation": round(float(center), 1),
            "slope_pct": slope_pct,
            "terrain_class": classify_slope(slope_pct),
        }

    if use_cache:
        cache[key] = result
        _save_cache(cache)
    return result
