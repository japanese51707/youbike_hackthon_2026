"""
時間衍生因子（features.time_features）— ADR-012
================================================
從 timestamp 衍生時間類特徵，零外部資料。時間是需求預測最基本且強的訊號：
通勤尖峰借還爆量、週末休閒型態、季節差異。

尖峰定義（可 config 覆寫）：早尖峰 07-09、晚尖峰 17-19。
季節：3-5 春、6-8 夏、9-11 秋、12-2 冬。

對外暴露：
    get_time_feature(timestamp) -> dict
        {hour, minute, weekday, is_weekend, is_morning_peak, is_evening_peak,
         is_peak, month, season, time_slot}
"""

from __future__ import annotations
import datetime as _dt

_WEEKDAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _parse(ts: str) -> _dt.datetime:
    s = str(ts).replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return _dt.datetime.strptime(s[:len(fmt) + 2] if fmt.endswith("%S") else s, fmt)
        except ValueError:
            continue
    # 寬鬆退回
    return _dt.datetime.fromisoformat(s[:19])


def _season(month: int) -> str:
    if month in (3, 4, 5):
        return "spring"
    if month in (6, 7, 8):
        return "summer"
    if month in (9, 10, 11):
        return "autumn"
    return "winter"


def get_time_feature(timestamp: str, config: dict | None = None) -> dict:
    """從時間戳衍生時間特徵。config 可覆寫尖峰時段。"""
    cfg = config or {}
    peak = cfg.get("peak_hours", {})
    am = peak.get("morning", (7, 9))    # [起, 迄) 小時
    pm = peak.get("evening", (17, 19))

    dt = _parse(timestamp)
    hour = dt.hour
    weekday = dt.weekday()          # 0=Mon ... 6=Sun
    is_weekend = weekday >= 5
    is_morning_peak = (am[0] <= hour < am[1]) and not is_weekend
    is_evening_peak = (pm[0] <= hour < pm[1]) and not is_weekend

    # 時段（半小時解析度，對齊 YouBike 資料）：0~47
    time_slot = hour * 2 + (1 if dt.minute >= 30 else 0)

    return {
        "hour": hour,
        "minute": dt.minute,
        "weekday": weekday,
        "weekday_name": _WEEKDAY_NAMES[weekday],
        "is_weekend": is_weekend,
        "is_morning_peak": is_morning_peak,
        "is_evening_peak": is_evening_peak,
        "is_peak": is_morning_peak or is_evening_peak,
        "month": dt.month,
        "season": _season(dt.month),
        "time_slot": time_slot,
    }
