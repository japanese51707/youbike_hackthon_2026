"""
POI 距離因子 + 站點區域類型（features.poi_distance）— ADR-012
==============================================================
標注 9 類地理靜態 POI 座標（poi_data.json，來自 OSM），計算 YouBike 站點到
「最近各類 POI」的距離。站點區域類型由「最近且在門檻內的 POI 類別」自動推導。

POI 類型：metro/train/bus_terminal/school/mall/night_market/hospital/park/venue

區域類型推導（可 config 調門檻）：
  找該站門檻距離內、最近的 POI 類別當主類型；都不在門檻內 → residential（住宅區）。
  類別→區域類型對映：metro/train/bus_terminal→transit、school→school、
  mall/night_market→commercial、park→leisure、hospital→medical、venue→venue。

對外暴露：
    distances_to_poi(lat, lng) -> dict         # 到各類最近 POI 的距離(km)
    classify_area_type(lat, lng) -> str        # 站點區域類型
    get_poi_feature(lat, lng) -> dict          # 距離 + 區域類型
"""

from __future__ import annotations
import json
import math
from functools import lru_cache
from pathlib import Path

_POI_PATH = Path(__file__).parent / "poi_data.json"

# POI 類別 → 區域類型
_TYPE_MAP = {
    "metro": "transit", "train": "transit", "bus_terminal": "transit",
    "school": "school",
    "mall": "commercial", "night_market": "commercial",
    "park": "leisure",
    "hospital": "medical",
    "venue": "venue",
}
# 判定區域類型的距離門檻（公里）：最近 POI 在此距離內才算該類型
_AREA_THRESHOLD_KM = 0.3


@lru_cache(maxsize=1)
def _load_poi() -> dict:
    return json.loads(_POI_PATH.read_text(encoding="utf-8"))["poi"]


def _haversine(lat1, lng1, lat2, lng2) -> float:
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


def distances_to_poi(lat: float, lng: float) -> dict:
    """回傳站點到各類 POI「最近一個」的距離(km)。某類無資料則為 None。"""
    poi = _load_poi()
    out = {}
    for ptype, points in poi.items():
        if not points:
            out[ptype] = None
            continue
        best = min(_haversine(lat, lng, p["lat"], p["lng"]) for p in points)
        out[ptype] = round(best, 3)
    return out


def classify_area_type(lat: float, lng: float,
                       threshold_km: float = _AREA_THRESHOLD_KM) -> str:
    """依最近 POI 推站點區域類型；門檻內都沒有 → residential。"""
    dists = distances_to_poi(lat, lng)
    # 找門檻內、距離最小的 POI 類別
    candidates = [(d, ptype) for ptype, d in dists.items()
                  if d is not None and d <= threshold_km]
    if not candidates:
        return "residential"
    _, nearest_type = min(candidates)
    return _TYPE_MAP.get(nearest_type, "mixed")


def get_poi_feature(lat: float, lng: float) -> dict:
    """站點 POI 特徵：到各類最近距離 + 區域類型。"""
    dists = distances_to_poi(lat, lng)
    return {
        "area_type": classify_area_type(lat, lng),
        "dist_metro_km": dists.get("metro"),
        "dist_train_km": dists.get("train"),
        "dist_bus_terminal_km": dists.get("bus_terminal"),
        "dist_school_km": dists.get("school"),
        "dist_mall_km": dists.get("mall"),
        "dist_night_market_km": dists.get("night_market"),
        "dist_hospital_km": dists.get("hospital"),
        "dist_park_km": dists.get("park"),
        "dist_venue_km": dists.get("venue"),
    }
