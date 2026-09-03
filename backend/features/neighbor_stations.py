"""
鄰近站連動因子（features.neighbor_stations）— ADR-013
======================================================
一個站空了，附近站可能被波及（使用者走去鄰站借還）。連動強度取決於「人願意走多遠」——
意願隨距離**指數衰減**（owner 洞見）：weight = exp(-distance / 特徵距離)。

★資料洩漏防範（ADR-013）：鄰近站「當下狀態」屬僅事後可知。預測 t+1 時，
  只能用鄰站 ≤ t 的已發生狀態，不可用 t+1 當下值。

特徵距離（characteristic distance）：控制衰減速度，可 config。
  預設 300m（YouBike 集水區 80% 使用在 300~500m，見 config event_radius 註解）。
  距離 = 特徵距離時權重 = exp(-1) ≈ 0.37；2 倍時 ≈ 0.14。

對外暴露：
    find_neighbors(lat, lng, all_stations, max_km) -> list   # 鄰近站 + 距離 + 連動權重
    neighbor_influence(station, all_stations, states)        # 加權鄰站狀態（防洩漏）
"""

from __future__ import annotations
import math
from typing import Optional

# 特徵距離（公里）：意願指數衰減的尺度。可 config 覆寫。
_CHAR_DISTANCE_KM = 0.3
# 只考慮此距離內的鄰站（超過權重已極小）
_MAX_NEIGHBOR_KM = 1.0


def _haversine(lat1, lng1, lat2, lng2) -> float:
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


def _decay_weight(distance_km: float, char_km: float = _CHAR_DISTANCE_KM) -> float:
    """距離 → 連動權重（指數衰減）。距離越遠，人越不願走過去，權重越小。"""
    return math.exp(-distance_km / char_km)


def find_neighbors(lat: float, lng: float, all_stations: list[dict],
                   max_km: float = _MAX_NEIGHBOR_KM,
                   char_km: float = _CHAR_DISTANCE_KM,
                   exclude_id: Optional[str] = None) -> list[dict]:
    """找指定座標周邊的鄰近站，附距離與連動權重（指數衰減）。

    all_stations：[{station_id, lat, lng, ...}]。exclude_id：排除自己。
    回傳依權重高到低排序的鄰站清單。
    """
    out = []
    for s in all_stations:
        if exclude_id and s.get("station_id") == exclude_id:
            continue
        d = _haversine(lat, lng, s["lat"], s["lng"])
        if d <= max_km:
            out.append({
                "station_id": s.get("station_id"),
                "station_name": s.get("station_name"),
                "distance_km": round(d, 3),
                "link_weight": round(_decay_weight(d, char_km), 4),
            })
    out.sort(key=lambda x: -x["link_weight"])
    return out


def neighbor_influence(station: dict, all_stations: list[dict],
                       states: dict, char_km: float = _CHAR_DISTANCE_KM) -> dict:
    """計算鄰近站對本站的加權連動影響（防洩漏：states 應為 ≤ t 的已發生狀態）。

    station：本站 {station_id, lat, lng}
    all_stations：所有站的座標清單
    states：{station_id: {available_bikes, available_docks, usage_rate}}（≤ t 的狀態）

    回傳加權後的鄰站借用率與「鄰站缺車/滿站壓力」——反映本站可能被波及的程度。
    """
    neighbors = find_neighbors(station["lat"], station["lng"], all_stations,
                               char_km=char_km, exclude_id=station.get("station_id"))
    if not neighbors:
        return {"neighbor_count": 0, "weighted_neighbor_usage": None,
                "neighbor_empty_pressure": None, "neighbor_full_pressure": None}

    total_w = 0.0
    w_usage = 0.0
    empty_pressure = 0.0   # 鄰站缺車（會有人來本站借）→ 對本站是「被借空」壓力
    full_pressure = 0.0    # 鄰站滿站（會有人來本站還）→ 對本站是「被還滿」壓力
    for nb in neighbors:
        st = states.get(nb["station_id"])
        if st is None:
            continue
        w = nb["link_weight"]
        total_w += w
        w_usage += w * float(st.get("usage_rate", 0))
        if st.get("available_bikes", 1) <= 0:
            empty_pressure += w
        if st.get("available_docks", 1) <= 0:
            full_pressure += w

    if total_w == 0:
        return {"neighbor_count": len(neighbors), "weighted_neighbor_usage": None,
                "neighbor_empty_pressure": None, "neighbor_full_pressure": None}

    return {
        "neighbor_count": len(neighbors),
        "weighted_neighbor_usage": round(w_usage / total_w, 1),
        "neighbor_empty_pressure": round(empty_pressure, 3),
        "neighbor_full_pressure": round(full_pressure, 3),
    }
