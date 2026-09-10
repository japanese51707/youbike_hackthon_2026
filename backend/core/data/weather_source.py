"""
即時天氣源（core.data.weather_source）— ADR-118
================================================
偵測突發天氣轉變（如驟雨 → 還車率暴增），作為緊急救火的額外觸發訊號。
比照 ADR-006 DataSource 可抽換：mock（開發/demo）/ cwa（中央氣象署開放資料，正式）。

換源只改 config.yaml 的 weather.mode（比照 data_source.mode）。

出向資安（steering §11 出向信任）：氣象署 API 是「我方主動打第三方」，
  - 只允許 https、設連線/讀取超時、限制重試次數
  - 第三方回應當「不可信輸入」：型別/範圍檢查後才用，不直接信任
  - API key 放環境變數（CWA_API_KEY），不寫進版控、不寫 log（steering §11.1）
  - 不把內部錯誤細節外流

對外暴露：
    get_weather_source() -> WeatherSource        # 依 config 回實作（單例）
    WeatherSource                                 # 抽象基底
    WeatherSnapshot 欄位契約：
      district, condition(sunny/cloudy/rain/heavy_rain/typhoon),
      rainfall_mm, temperature_c, observed_at, source

天氣突變偵測（供 emergency 用）：
    detect_weather_shift(prev, curr) -> Optional[dict]   # 前後兩快照比對，回突變事件或 None
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Optional

# 天氣狀態嚴重度（數字越大越可能推升還車率）
_CONDITION_SEVERITY = {
    "sunny": 0, "cloudy": 1, "rain": 2, "heavy_rain": 3, "typhoon": 4,
}


class WeatherSource(ABC):
    """即時天氣源介面。實作回傳標準 WeatherSnapshot dict。"""

    name: str = "abstract"

    @abstractmethod
    def get_weather(self, district: str) -> Optional[dict]:
        """回單一行政區當前天氣快照。找不到回 None。"""
        ...

    @abstractmethod
    def get_all(self) -> list[dict]:
        """回所有行政區當前天氣快照。"""
        ...


# ── 內建 mock（開發/demo；可注入指定天氣供測試突變）──
class MockWeatherSource(WeatherSource):
    name = "mock"

    def __init__(self, overrides: Optional[dict] = None):
        # overrides: {district: condition} 供測試指定天氣
        self._overrides = overrides or {}

    def get_weather(self, district: str) -> Optional[dict]:
        import datetime as _dt
        cond = self._overrides.get(district, "cloudy")
        return {
            "district": district,
            "condition": cond,
            "rainfall_mm": {"heavy_rain": 30.0, "rain": 5.0, "typhoon": 60.0}.get(cond, 0.0),
            "temperature_c": 26.0,
            "observed_at": _dt.datetime.now().isoformat(timespec="seconds"),
            "source": "mock",
        }

    def get_all(self) -> list[dict]:
        # mock 只回 overrides 指定的區（demo/測試用）
        return [self.get_weather(d) for d in self._overrides] if self._overrides else []


# ── 中央氣象署（正式；骨架，出向資安框架就位，實際 HTTP 待現場串接）──
class CWAWeatherSource(WeatherSource):
    """中央氣象署開放資料。骨架先就位出向資安框架；實際 httpx 呼叫待正式環境串接
    （demo 用 mock，避免開發期打外部 API）。"""
    name = "cwa"

    def get_weather(self, district: str) -> Optional[dict]:
        # 正式串接：_fetch(district) 帶 CWA_API_KEY(環境變數)、https、超時、重試上限、
        #           回應做型別/範圍檢查後才回傳（出向不可信輸入）。開發期不實際打 API。
        raise NotImplementedError("CWAWeatherSource 待正式環境串接（開發/demo 用 mock）")

    def get_all(self) -> list[dict]:
        raise NotImplementedError("CWAWeatherSource 待正式環境串接（開發/demo 用 mock）")


def detect_weather_shift(prev: dict, curr: dict) -> Optional[dict]:
    """比對同區前後兩快照，偵測「天氣突變（惡化）」→ 回突變事件；無突變回 None。

    突變 = 嚴重度上升 ≥ 2 級（如 sunny→rain、cloudy→heavy_rain），
    這種驟變最可能引發還車率暴增（雨來大家趕快騎回家/改搭車）。
    """
    if not prev or not curr:
        return None
    sp = _CONDITION_SEVERITY.get(prev.get("condition"), 0)
    sc = _CONDITION_SEVERITY.get(curr.get("condition"), 0)
    if sc - sp >= 2:
        return {
            "district": curr.get("district"),
            "from": prev.get("condition"),
            "to": curr.get("condition"),
            "severity_jump": sc - sp,
            "hint": "天氣驟變惡化，還車率可能暴增，建議該區提前備援（駐點/預備車）",
        }
    return None


# ── 工廠（依 config 切換，單例；比照 get_data_source）──
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
