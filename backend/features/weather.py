"""
天氣因子（features.weather）— ADR-011
======================================
天氣影響騎乘意願（雨天需求降、好天氣休閒站需求升）。訓練階段用歷史資料；
即時 CWA API 待模型建好、要「以現況預測下個時段」時才接（owner 核准，見 ADR-011）。

資料源：CODiS 重建逐時歷史（github Raingel/historical_weather）。
  新北市 56 個在營測站（weather_stations.json）。
  逐時資料 URL：.../data_codis_rebuild_full/{站號}/{站號}_{年}.csv

對齊策略：
  1. 站點座標 → 找最近的氣象測站（haversine 距離）
  2. 讀該測站當年逐時資料
  3. YouBike 逐半時（00:00/00:30）對齊天氣逐時：同一小時的兩個半時用該小時值
  4. 缺值明確標 None，不假裝（NFR-5）

抓下來的測站年度資料快取到本地，避免重複下載。

對外暴露：
    nearest_station(lat, lng) -> dict            # 最近測站
    get_weather_feature(lat, lng, timestamp)     # 該站該時刻天氣特徵
"""

from __future__ import annotations
import io
import json
import math
from functools import lru_cache
from pathlib import Path
from typing import Optional

_STATIONS_PATH = Path(__file__).parent / "weather_stations.json"
_CACHE_DIR = Path(__file__).parent / "_weather_cache"
_RAW_URL = ("https://raw.githubusercontent.com/Raingel/historical_weather/main/"
            "data_codis_rebuild_full/{sid}/{sid}_{year}.csv")

# CODiS 欄位 → 標準特徵欄位。
# 自動站（C0開頭）實際有值的是簡碼欄位（Tx/RH/Precp/WS），完整名欄位常為空，
# 故「簡碼優先」；完整名當備援（少數有人站可能用）。
_COL_MAP = {
    "Tx": "temperature",       # 氣溫
    "RH": "humidity",          # 濕度
    "Precp": "precipitation",  # 雨量
    "WS": "wind_speed",        # 風速
}
_COL_MAP_ALT = {
    "AirTemperature.Instantaneousf": "temperature",
    "RelativeHumidity.Instantaneousf": "humidity",
    "Precipitation.Accumulationf": "precipitation",
    "WindSpeed.Meanf": "wind_speed",
}


@lru_cache(maxsize=1)
def _load_stations() -> list[dict]:
    return json.loads(_STATIONS_PATH.read_text(encoding="utf-8"))["stations"]


def _haversine(lat1, lng1, lat2, lng2) -> float:
    """兩座標間距離（公里）。"""
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


def nearest_station(lat: float, lng: float) -> dict:
    """找離指定座標最近的氣象測站，附距離(km)。"""
    best, best_d = None, float("inf")
    for s in _load_stations():
        d = _haversine(lat, lng, s["lat"], s["lng"])
        if d < best_d:
            best, best_d = s, d
    return {**best, "distance_km": round(best_d, 2)}


@lru_cache(maxsize=32)
def _load_station_year(station_id: str, year: int):
    """讀某測站某年的逐時資料 → DataFrame（indexed by 'YYYY-MM-DD HH'）。快取到本地+記憶體。"""
    import pandas as pd

    _CACHE_DIR.mkdir(exist_ok=True)
    cache_file = _CACHE_DIR / f"{station_id}_{year}.csv"
    if cache_file.exists():
        df = pd.read_csv(cache_file)
    else:
        import httpx
        url = _RAW_URL.format(sid=station_id, year=year)
        r = httpx.get(url, timeout=60, follow_redirects=True)
        r.raise_for_status()
        df = pd.read_csv(io.StringIO(r.text))
        df.to_csv(cache_file, index=False)

    # 欄位對映（優先完整名，備援簡碼）
    rename = {}
    for raw, std in _COL_MAP.items():
        if raw in df.columns:
            rename[raw] = std
    for raw, std in _COL_MAP_ALT.items():
        if raw in df.columns and std not in rename.values():
            rename[raw] = std
    df = df.rename(columns=rename)
    # 時間鍵：取到「小時」（YouBike 半時對齊到整點小時）
    df["_hourkey"] = df["timestamp"].astype(str).str[:13]  # 'YYYY-MM-DD HH'
    return df.set_index("_hourkey")


def get_weather_feature(lat: float, lng: float, timestamp: str) -> dict:
    """回傳某站點座標、某時刻的天氣特徵（對齊最近測站的該小時值）。

    timestamp 接受 'YYYY-MM-DD HH:MM:SS' 或 'YYYY-MM-DDTHH:MM'。
    缺值回 None（不假裝），並附對齊到的測站與距離。
    """
    ts = str(timestamp).replace("T", " ")
    hourkey = ts[:13]              # 'YYYY-MM-DD HH'
    year = int(ts[:4])

    st = nearest_station(lat, lng)
    feature = {
        "station_id": st["station_id"],
        "station_name": st["name"],
        "distance_km": st["distance_km"],
        "temperature": None, "humidity": None,
        "precipitation": None, "wind_speed": None,
        "temp_comfort": None,   # 溫度舒適度（倒U，見下）
    }
    try:
        df = _load_station_year(st["station_id"], year)
        if hourkey in df.index:
            row = df.loc[hourkey]
            if hasattr(row, "iloc"):   # 同小時多筆時取第一筆
                row = row.iloc[0] if getattr(row, "ndim", 1) > 1 else row
            for col in ("temperature", "humidity", "precipitation", "wind_speed"):
                if col in df.columns:
                    val = row[col]
                    # CODiS 用特殊值表缺測（如 -99），這裡簡單過濾負異常與 NaN
                    import pandas as pd
                    if pd.notna(val) and not (isinstance(val, (int, float)) and val <= -90):
                        feature[col] = round(float(val), 1)
    except Exception:
        pass  # 拿不到資料 → 保持 None（NFR-5 明確缺值）

    # 溫度舒適度（倒 U 型，ADR-013）：騎乘意願在「最適溫」最高，太熱太冷都降。
    # 用高斯型：comfort = exp(-((T - 最適)/寬度)^2)，值域 0~1。
    if feature["temperature"] is not None:
        feature["temp_comfort"] = round(_temp_comfort(feature["temperature"]), 3)
    return feature


# 溫度舒適度參數（可 config 覆寫）：最適約 24°C、標準差寬度約 8°C
_TEMP_OPTIMAL = 24.0
_TEMP_WIDTH = 8.0


def _temp_comfort(temp: float) -> float:
    """溫度 → 騎乘舒適度（0~1，倒U型）。24°C 最舒適，太熱太冷遞減。"""
    import math
    return math.exp(-((temp - _TEMP_OPTIMAL) / _TEMP_WIDTH) ** 2)
