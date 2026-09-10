"""
即時天氣源（core.data.weather_source）— ADR-118
================================================
偵測突發天氣轉變（如驟雨 → 還車率暴增），作為緊急救火的額外觸發訊號。
比照 ADR-006 DataSource 可抽換：mock（開發/測試）/ cwa（中央氣象署開放資料，正式）。
換源只改 config.yaml 的 weather.mode。

精細度：觀測站級（ADR-118 owner 決定；比行政區級細）。雙資料集：
  - 雨量站 O-A0002-001（新北約 100 站，Past10Min/Now 雨量）→ 偵測驟雨主力（密度高）
  - 氣象站 O-A0003-001（新北約 25 站，氣溫/濕度/天氣現象）→ 一般天氣輔助
任一 YouBike 站（有經緯度）用 haversine 找「最近測站」取值（Voronoi 最近鄰對應）。

出向資安（steering §11）：CWA 是第三方——
  - API key 從環境變數 CWA_WEATHER_API_KEY 讀（放 .env，不進版控、不寫 log）
  - 設超時 + 重試上限；政府平台憑證鏈問題用 verify=False（比照 youbike_official）
  - 第三方回應當「不可信輸入」：欄位缺失/型別容錯，不直接信任

對外暴露：
    get_weather_source() -> WeatherSource        # 依 config 回實作（單例）
    WeatherSource                                 # 抽象基底
    get_rainfall_by_location(lat, lng)            # 最近雨量站的即時雨量（驟雨偵測）
    get_weather_by_location(lat, lng)             # 最近氣象站的氣溫/濕度/天氣現象
    get_weather(district)                         # 相容：回該區代表測站（行政區級用途）
    detect_weather_shift(prev, curr)              # 前後快照比對，偵測天氣突變
"""

from __future__ import annotations
import math
import os
from abc import ABC, abstractmethod
from typing import Optional

_CONDITION_SEVERITY = {
    "sunny": 0, "cloudy": 1, "rain": 2, "heavy_rain": 3, "typhoon": 4,
}

# CWA 資料集代碼（實測確認，2026-09）
_CWA_RAIN = "O-A0002-001"     # 自動雨量站（新北約 100 站）
_CWA_WEATHER = "O-A0003-001"  # 自動氣象站（新北約 25 站）
_CWA_BASE = "https://opendata.cwa.gov.tw/api/v1/rest/datastore"


def _haversine_km(lat1, lng1, lat2, lng2) -> float:
    try:
        lat1, lng1, lat2, lng2 = float(lat1), float(lng1), float(lat2), float(lng2)
    except (TypeError, ValueError):
        return float("inf")
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return r * 2 * math.asin(math.sqrt(a))


def _f(v, d=None):
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


# ── 抽象介面 ──
class WeatherSource(ABC):
    name: str = "abstract"

    @abstractmethod
    def rain_stations(self) -> list[dict]:
        """所有雨量站快照：{name, town, lat, lng, now, past10, past1hr}。"""
        ...

    @abstractmethod
    def weather_stations(self) -> list[dict]:
        """所有氣象站快照：{name, town, lat, lng, condition, temperature_c, humidity, rainfall_mm}。"""
        ...

    # ── 觀測站級查詢（ADR-118：最近測站對應）──
    def get_rainfall_by_location(self, lat, lng) -> Optional[dict]:
        stations = self.rain_stations()
        if not stations:
            return None
        s = min(stations, key=lambda x: _haversine_km(lat, lng, x["lat"], x["lng"]))
        return {**s, "distance_km": round(_haversine_km(lat, lng, s["lat"], s["lng"]), 2)}

    def get_weather_by_location(self, lat, lng) -> Optional[dict]:
        stations = self.weather_stations()
        if not stations:
            return None
        s = min(stations, key=lambda x: _haversine_km(lat, lng, x["lat"], x["lng"]))
        return {**s, "distance_km": round(_haversine_km(lat, lng, s["lat"], s["lng"]), 2)}

    def get_weather(self, district: str) -> Optional[dict]:
        """相容介面（行政區級）：回該區內任一氣象站；無則回 None。"""
        for s in self.weather_stations():
            if s.get("town", "").startswith(district) or district in s.get("town", ""):
                return s
        return None


# ── mock（開發/測試；不打外部 API）──
class MockWeatherSource(WeatherSource):
    name = "mock"

    def __init__(self, rain_overrides=None, wx_overrides=None):
        self._rain = rain_overrides or []
        self._wx = wx_overrides or []

    def rain_stations(self) -> list[dict]:
        return self._rain

    def weather_stations(self) -> list[dict]:
        if self._wx:
            return self._wx
        # 預設一個代表站，供測試不為空
        return [{"name": "mock站", "town": "板橋區", "lat": 25.01, "lng": 121.46,
                 "condition": "cloudy", "temperature_c": 26.0, "humidity": 80.0,
                 "rainfall_mm": 0.0}]


# ── 中央氣象署（正式）──
class CWAWeatherSource(WeatherSource):
    """CWA 開放資料。雙資料集 + 最近測站對應。key 由環境變數 CWA_WEATHER_API_KEY 讀。"""
    name = "cwa"

    def __init__(self):
        from config_loader import get_config
        w = get_config().get("weather", {})
        self._timeout = int(w.get("timeout_sec", 5))
        self._retries = int(w.get("max_retries", 2))
        self._county = w.get("county", "新北")
        self._key = os.environ.get("CWA_WEATHER_API_KEY", "")
        self._rain_cache: Optional[list] = None
        self._wx_cache: Optional[list] = None

    def _fetch(self, code: str) -> list[dict]:
        """打 CWA API，回該縣市測站原始列（出向資安：超時/重試/verify=False/回應容錯）。"""
        import httpx
        if not self._key:
            raise RuntimeError("缺 CWA_WEATHER_API_KEY 環境變數（放 .env，勿進版控）")
        url = f"{_CWA_BASE}/{code}"
        last_err = None
        for _ in range(self._retries + 1):
            try:
                # 政府平台憑證鏈問題 → verify=False（比照 youbike_official；key 在參數非靠 SSL 保護）
                r = httpx.get(url, params={"Authorization": self._key, "format": "JSON"},
                              timeout=self._timeout, verify=False)
                r.raise_for_status()
                stations = r.json().get("records", {}).get("Station", [])
                return [s for s in stations
                        if self._county in s.get("GeoInfo", {}).get("CountyName", "")]
            except Exception as e:   # noqa: BLE001 - 第三方不可信，容錯後重試
                last_err = e
        raise RuntimeError(f"CWA {code} 取用失敗：{type(last_err).__name__}")

    @staticmethod
    def _wgs84(geo: dict):
        for c in geo.get("Coordinates", []):
            if c.get("CoordinateName") == "WGS84":
                return _f(c.get("StationLatitude")), _f(c.get("StationLongitude"))
        cs = geo.get("Coordinates", [])
        return (_f(cs[0].get("StationLatitude")), _f(cs[0].get("StationLongitude"))) if cs else (None, None)

    def rain_stations(self) -> list[dict]:
        if self._rain_cache is not None:
            return self._rain_cache
        out = []
        for s in self._fetch(_CWA_RAIN):
            geo = s.get("GeoInfo", {})
            lat, lng = self._wgs84(geo)
            if lat is None or lng is None:
                continue
            re = s.get("RainfallElement", {})
            out.append({
                "name": s.get("StationName", "?"), "town": geo.get("TownName", ""),
                "lat": lat, "lng": lng,
                "now": _f(re.get("Now", {}).get("Precipitation"), 0.0),
                "past10": _f(re.get("Past10Min", {}).get("Precipitation"), 0.0),
                "past1hr": _f(re.get("Past1hr", {}).get("Precipitation"), 0.0),
            })
        self._rain_cache = out
        return out

    def weather_stations(self) -> list[dict]:
        if self._wx_cache is not None:
            return self._wx_cache
        out = []
        for s in self._fetch(_CWA_WEATHER):
            geo = s.get("GeoInfo", {})
            lat, lng = self._wgs84(geo)
            if lat is None or lng is None:
                continue
            we = s.get("WeatherElement", {})
            out.append({
                "name": s.get("StationName", "?"), "town": geo.get("TownName", ""),
                "lat": lat, "lng": lng,
                "condition": _map_condition(we.get("Weather", "")),
                "raw_weather": we.get("Weather", ""),
                "temperature_c": _f(we.get("AirTemperature")),
                "humidity": _f(we.get("RelativeHumidity")),
                "rainfall_mm": _f(we.get("Now", {}).get("Precipitation"), 0.0),
            })
        self._wx_cache = out
        return out


def _map_condition(raw: str) -> str:
    """CWA 中文天氣現象 → 標準 condition（供 detect_weather_shift 嚴重度比對）。"""
    if not raw:
        return "cloudy"
    if "颱" in raw:
        return "typhoon"
    if "大雨" in raw or "豪雨" in raw or "雷" in raw:
        return "heavy_rain"
    if "雨" in raw:
        return "rain"
    if "晴" in raw:
        return "sunny"
    return "cloudy"


def detect_weather_shift(prev: dict, curr: dict) -> Optional[dict]:
    """比對同區前後快照，偵測天氣突變（惡化 ≥2 級）→ 回突變事件，否則 None。"""
    if not prev or not curr:
        return None
    sp = _CONDITION_SEVERITY.get(prev.get("condition"), 0)
    sc = _CONDITION_SEVERITY.get(curr.get("condition"), 0)
    if sc - sp >= 2:
        return {
            "from": prev.get("condition"), "to": curr.get("condition"),
            "severity_jump": sc - sp,
            "hint": "天氣驟變惡化，還車率可能暴增，建議該區提前備援（駐點/預備車）",
        }
    return None


# ── 工廠（依 config 切換，單例）──
_instance: Optional[WeatherSource] = None
_mode: Optional[str] = None


def get_weather_source(force_mode: Optional[str] = None) -> WeatherSource:
    global _instance, _mode
    try:
        from config_loader import get_config
        mode = force_mode or get_config().get("weather", {}).get("mode", "mock")
    except Exception:
        mode = force_mode or "mock"
    if force_mode is None and _instance is not None and _mode == mode:
        return _instance
    inst = _build(mode)
    if force_mode is None:
        _instance, _mode = inst, mode
    return inst


def _build(mode: str) -> WeatherSource:
    if mode == "mock":
        return MockWeatherSource()
    if mode == "cwa":
        return CWAWeatherSource()
    raise ValueError(f"未知的 weather.mode：'{mode}'（可用：mock / cwa）")


def reset_weather_source() -> None:
    global _instance, _mode
    _instance = _mode = None
