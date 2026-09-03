"""
假日因子（features.calendar_holiday）— ADR-011
================================================
用政府行政機關辦公日曆表判斷任一日期是否放假、節日類型、是否為連假。
影響：假日的騎乘型態與平日不同（通勤 vs 休閒），是重要特徵。

資料源：新北市開放平台 dataset 308DCD75（涵蓋 2018~2027）。
  欄位：date(YYYYMMDD)、isholiday(是/否)、holidaycategory、name、description
  只列「放假日 + 補行上班日 + 特定節日」，一般平日不在表內。
  抓一次存本地快取（假日表一年更新一次，不需每次打 API）。

判斷邏輯：
  - 日期在表中且 isholiday=是 → 放假（再細分：國定假日 / 週末 / 補假 / 調整放假）
  - 日期在表中且 category=補行上班日 → 上班（即使是週末）
  - 不在表中 → 依星期判斷（週一~五上班、週末放假）

對外暴露：
    get_holiday_feature(date) -> dict   # {is_holiday, category, name, is_national_holiday, is_long_weekend}
"""

from __future__ import annotations
import datetime as _dt
import json
from pathlib import Path
from typing import Optional

_CACHE_PATH = Path(__file__).parent / "_holiday_cache.json"
_DATASET = "308DCD75-6434-45BC-A95F-584DA4FED251"
_API = f"https://data.ntpc.gov.tw/api/datasets/{_DATASET}/json?size=5000"

# 國定假日類型（真正的節日放假，非單純週末）
_NATIONAL_CATEGORIES = {"放假之紀念日及節日", "特定節日", "調整放假日", "補假"}
_WORKDAY_CATEGORY = "補行上班日"


def _normalize(d: str) -> str:
    """統一日期格式成 YYYYMMDD。接受 '2026-06-15' 或 '20260615'。"""
    return d.replace("-", "").replace("/", "")[:8]


def _load_table() -> dict:
    """載入假日表（date → 該筆資料）。優先讀本地快取，無則抓 API 並存快取。"""
    if _CACHE_PATH.exists():
        return json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
    import httpx
    # 政府開放平台憑證鏈問題（見 tasks I-3 SSL 備註），此為一次性抓取歷史假日表
    r = httpx.get(_API, timeout=60, verify=False)
    r.raise_for_status()
    table = {row["date"]: row for row in r.json()}
    _CACHE_PATH.write_text(json.dumps(table, ensure_ascii=False), encoding="utf-8")
    return table


def _reset_cache() -> None:
    """測試/更新用：刪快取，下次重抓。"""
    if _CACHE_PATH.exists():
        _CACHE_PATH.unlink()


def get_holiday_feature(date: str) -> dict:
    """回傳某日期的假日特徵。

    is_holiday：當天是否放假
    category：假日類型（國定假日/週末/補假/調整放假/補行上班日/一般工作日）
    name：節日名稱（若有）
    is_national_holiday：是否為國定假日（非單純週末）
    is_long_weekend：是否為連假的一部分（前後含當天連續 ≥3 天放假）
    """
    table = _load_table()
    key = _normalize(date)
    d = _dt.datetime.strptime(key, "%Y%m%d").date()

    row = table.get(key)
    if row is not None:
        if row["holidaycategory"] == _WORKDAY_CATEGORY:
            is_holiday, category = False, "補行上班日"
        else:
            is_holiday = (row.get("isholiday") == "是")
            category = ("國定假日" if row["holidaycategory"] in _NATIONAL_CATEGORIES
                        else ("週末" if row["holidaycategory"] == "星期六、星期日"
                              else row["holidaycategory"]))
        name = row.get("name")
        is_national = row["holidaycategory"] in _NATIONAL_CATEGORIES
    else:
        # 不在表中：依星期判斷（週一=0 ... 週日=6）
        is_weekend = d.weekday() >= 5
        is_holiday = is_weekend
        category = "週末" if is_weekend else "一般工作日"
        name = None
        is_national = False

    return {
        "date": key,
        "is_holiday": is_holiday,
        "category": category,
        "name": name,
        "is_national_holiday": is_national,
        "is_long_weekend": _is_long_weekend(d, table),
    }


def _is_day_off(d: _dt.date, table: dict) -> bool:
    """某日是否放假（給連假判斷用，內部）。"""
    key = d.strftime("%Y%m%d")
    row = table.get(key)
    if row is not None:
        if row["holidaycategory"] == _WORKDAY_CATEGORY:
            return False
        return row.get("isholiday") == "是"
    return d.weekday() >= 5


def _is_long_weekend(d: _dt.date, table: dict) -> bool:
    """當天是否屬於連續 ≥3 天的放假（連假）。"""
    if not _is_day_off(d, table):
        return False
    # 往前往後數連續放假天數
    run = 1
    prev = d - _dt.timedelta(days=1)
    while _is_day_off(prev, table):
        run += 1
        prev -= _dt.timedelta(days=1)
    nxt = d + _dt.timedelta(days=1)
    while _is_day_off(nxt, table):
        run += 1
        nxt += _dt.timedelta(days=1)
    return run >= 3
