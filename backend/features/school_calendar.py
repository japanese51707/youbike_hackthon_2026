"""
學期/學生數因子（features.school_calendar）— ADR-101
=====================================================
判斷某日期是否為學期中/寒假/暑假，並推估新北市當期「在學影響人口」。
影響：學期中學生通勤帶動 YouBike 借還（尤其國高中大學通學站），寒暑假需求型態改變。

兩部分：
  1. 學期日曆：判斷某日各級（國小/國中/高中/大學）是否在學期中
     台灣學制規律固定：上學期約 9/1~1月下旬、寒假約1月下~2月中（與農曆年連動）、
     下學期約 2月中~6月底、暑假 7~8月。各學年精確日期可在 config 覆寫。
  2. 學生數：各級在學學生數（student_population.json，新北市粗估，之後校準）

輸出「影響人口」= Σ(在學期中的級別 × 學生數 × 騎乘影響係數)。
係數為初期粗估（ADR-101 owner 核准），之後以教育部統計校準。

對外暴露：
    get_school_feature(date) -> dict
        {in_semester_levels, is_winter_break, is_summer_break, influence_population}
"""

from __future__ import annotations
import datetime as _dt
import json
from pathlib import Path

_POP_PATH = Path(__file__).parent / "student_population.json"

# 暑假（固定月份區間，各級一致）：7/1 ~ 8/31
_SUMMER = ((7, 1), (8, 31))

# 寒假與農曆年連動，逐年不同。這裡放各學年寒假區間（可在 config 覆寫/擴充）。
# 格式：{ "西元年": (起, 迄) }，日期為該西元年的寒假。
# 2026 寒假約在春節（2026 春節為 2/17 前後）前後，抓 1/21 ~ 2/15 為概估。
_WINTER_BREAK = {
    2025: ("2025-01-21", "2025-02-11"),
    2026: ("2026-01-21", "2026-02-15"),
    2027: ("2027-02-06", "2027-02-21"),
}


def _load_population() -> dict:
    return json.loads(_POP_PATH.read_text(encoding="utf-8"))["levels"]


def _in_summer(d: _dt.date) -> bool:
    (m1, d1), (m2, d2) = _SUMMER
    start = _dt.date(d.year, m1, d1)
    end = _dt.date(d.year, m2, d2)
    return start <= d <= end


def _in_winter(d: _dt.date) -> bool:
    wb = _WINTER_BREAK.get(d.year)
    if not wb:
        # 無該年資料 → 用概估：1/20~2/15（農曆年多落此區間）
        start = _dt.date(d.year, 1, 20)
        end = _dt.date(d.year, 2, 15)
    else:
        start = _dt.date.fromisoformat(wb[0])
        end = _dt.date.fromisoformat(wb[1])
    return start <= d <= end


def get_school_feature(date: str) -> dict:
    """回傳某日期的學期/學生影響特徵。

    in_semester：該日是否在學期中（非寒暑假）
    is_winter_break / is_summer_break：是否寒/暑假
    influence_population：在學期中時的影響人口推估（寒暑假則為 0，代表通學需求消失）
    by_level：各級是否在學期中 + 該級影響人口
    """
    d = _dt.date.fromisoformat(str(date)[:10]) if "-" in str(date) else \
        _dt.datetime.strptime(str(date)[:8], "%Y%m%d").date()

    is_summer = _in_summer(d)
    is_winter = _in_winter(d)
    in_semester = not (is_summer or is_winter)

    pop = _load_population()
    by_level = {}
    total_influence = 0.0
    for level, info in pop.items():
        # 初期：各級寒暑假一致停課（未細分大學與中小學的學期差異，之後可加）
        level_in_semester = in_semester
        influence = (info["students"] * info["cycle_influence"]) if level_in_semester else 0.0
        by_level[level] = {
            "label": info["label"],
            "in_semester": level_in_semester,
            "students": info["students"],
            "influence": round(influence),
        }
        total_influence += influence

    return {
        "date": d.isoformat(),
        "in_semester": in_semester,
        "is_winter_break": is_winter,
        "is_summer_break": is_summer,
        "influence_population": round(total_influence),
        "by_level": by_level,
    }
