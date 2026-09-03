"""
特殊天氣因子（features.weather_alert）— ADR-012
================================================
標記「異常天氣日」：颱風、豪大雨特報、停班停課。呼應 model_architecture 異常日標籤：
  - 訓練時可排除這些日子（避免把模型教壞）
  - 保留標籤，未來遇同類情境（颱風天）可調出當依據做「特殊情境預估」

兩個來源：
  1. 規則判定：從天氣因子的雨量/風速，套中央氣象署特報標準閾值判「豪大雨/強風」
  2. 停班課日表 typhoon_days.json：颱風/災害停班課是行政公告（非純氣象），手動維護
     （現場/補資料時填入；也可日後接中央氣象署災防公告）

閾值（config 可覆寫，暫用氣象署概念值）：
  豪雨：日雨量 ≥ 200mm 或時雨量 ≥ 40mm
  大雨：日雨量 ≥ 80mm 或時雨量 ≥ 40mm
  強風：10 分鐘平均風速 ≥ 14 m/s（約 7 級風）

對外暴露：
    is_suspended_day(date) -> bool                       # 是否停班課（查日表）
    get_weather_alert_feature(lat, lng, timestamp) -> dict
        {is_abnormal, alert_level, is_suspended, rain_alert, wind_alert}
"""

from __future__ import annotations
import json
from pathlib import Path

_SUSPEND_PATH = Path(__file__).parent / "typhoon_days.json"

# 特報閾值（時雨量 mm、風速 m/s）— 可 config 覆寫
_HEAVY_RAIN_HOURLY = 40.0    # 豪/大雨時雨量門檻
_TORRENTIAL_HOURLY = 100.0   # 超大豪雨等級（極端）
_STRONG_WIND = 14.0          # 強風（約 7 級）


def _load_suspend_days() -> set:
    """停班課日表（YYYY-MM-DD 集合）。無檔案回空集合。"""
    if not _SUSPEND_PATH.exists():
        return set()
    data = json.loads(_SUSPEND_PATH.read_text(encoding="utf-8"))
    return set(data.get("suspended_days", []))


def is_suspended_day(date: str) -> bool:
    """某日是否為停班停課日（颱風/災害行政公告）。"""
    return str(date)[:10] in _load_suspend_days()


def get_weather_alert_feature(lat: float, lng: float, timestamp: str) -> dict:
    """回傳該站點該時刻的特殊天氣特徵。

    結合天氣因子的雨量/風速（規則判特報）+ 停班課日表。
    is_abnormal：是否異常日（供訓練排除/情境預估的標籤）。
    """
    date = str(timestamp)[:10]
    suspended = is_suspended_day(date)

    # 取該時刻天氣（雨量/風速）判特報
    rain_alert, wind_alert = None, False
    try:
        from features.weather import get_weather_feature
        w = get_weather_feature(lat, lng, timestamp)
        precp = w.get("precipitation")
        wind = w.get("wind_speed")
        if precp is not None:
            if precp >= _TORRENTIAL_HOURLY:
                rain_alert = "torrential"   # 超大豪雨
            elif precp >= _HEAVY_RAIN_HOURLY:
                rain_alert = "heavy"        # 豪/大雨
        if wind is not None and wind >= _STRONG_WIND:
            wind_alert = True
    except Exception:
        pass  # 天氣拿不到 → 只靠停班課日表

    is_abnormal = suspended or (rain_alert is not None) or wind_alert
    # 分級：停班課最嚴重
    if suspended:
        alert_level = "suspended"
    elif rain_alert == "torrential" or wind_alert:
        alert_level = "severe"
    elif rain_alert == "heavy":
        alert_level = "warning"
    else:
        alert_level = "normal"

    return {
        "date": date,
        "is_abnormal": is_abnormal,
        "alert_level": alert_level,
        "is_suspended": suspended,
        "rain_alert": rain_alert,
        "wind_alert": wind_alert,
    }
