"""
日出日落因子（features.daylight）— ADR-013
============================================
天黑後騎乘意願下降。用天文公式（NOAA 演算法簡化版）計算日出/日落時間，
判斷某時刻是否白天、距日出/日落多久。純計算、無外部資料，全市共用（新北緯度差異可忽略）。

可得性：已知未來確定（天文可算）｜更新頻率：靜態算｜涵蓋範圍：全市共用。

對外暴露：
    sun_times(date, lat, lng) -> (sunrise_hour, sunset_hour)   # 當日日出日落（小時，浮點）
    get_daylight_feature(timestamp, lat, lng) -> dict
        {is_daylight, hour, sunrise, sunset, mins_from_sunrise, mins_to_sunset}
"""

from __future__ import annotations
import datetime as _dt
import math

# 新北市代表座標（全市共用，緯度差異對日出日落影響 < 幾分鐘）
_DEFAULT_LAT = 25.01
_DEFAULT_LNG = 121.46
_TZ_OFFSET = 8.0   # 台灣 UTC+8


def sun_times(date: str, lat: float = _DEFAULT_LAT, lng: float = _DEFAULT_LNG):
    """回傳當日日出、日落時間（當地時間，小時浮點）。用 NOAA 簡化演算法。"""
    d = _dt.date.fromisoformat(str(date)[:10]) if "-" in str(date) else \
        _dt.datetime.strptime(str(date)[:8], "%Y%m%d").date()
    n = d.timetuple().tm_yday   # 年積日

    # 太陽赤緯（近似）
    decl = 23.45 * math.sin(math.radians(360.0 / 365.0 * (n - 81)))
    lat_r = math.radians(lat)
    decl_r = math.radians(decl)

    # 時角（日出/日落時太陽在地平線）
    cos_h = -math.tan(lat_r) * math.tan(decl_r)
    cos_h = max(-1.0, min(1.0, cos_h))
    hour_angle = math.degrees(math.acos(cos_h))   # 度

    # 均時差（近似）
    b = math.radians(360.0 / 365.0 * (n - 81))
    eot = 9.87 * math.sin(2 * b) - 7.53 * math.cos(b) - 1.5 * math.sin(b)  # 分鐘

    # 太陽正午（當地時間，小時）
    solar_noon = 12.0 - (lng - _TZ_OFFSET * 15.0) / 15.0 - eot / 60.0
    sunrise = solar_noon - hour_angle / 15.0
    sunset = solar_noon + hour_angle / 15.0
    return round(sunrise, 2), round(sunset, 2)


def get_daylight_feature(timestamp: str, lat: float = _DEFAULT_LAT,
                         lng: float = _DEFAULT_LNG) -> dict:
    """某時刻的日照特徵。"""
    ts = str(timestamp).replace("T", " ")
    date = ts[:10]
    dt = _dt.datetime.fromisoformat(ts[:19]) if len(ts) >= 19 else \
        _dt.datetime.strptime(ts[:16], "%Y-%m-%d %H:%M")
    hour_f = dt.hour + dt.minute / 60.0

    sunrise, sunset = sun_times(date, lat, lng)
    is_daylight = sunrise <= hour_f <= sunset
    return {
        "hour": round(hour_f, 2),
        "sunrise": sunrise,
        "sunset": sunset,
        "is_daylight": is_daylight,
        "mins_from_sunrise": round((hour_f - sunrise) * 60),
        "mins_to_sunset": round((sunset - hour_f) * 60),
    }
