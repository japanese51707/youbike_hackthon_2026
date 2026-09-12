"""
班別與排程模式判斷 + 勞動工時檢查（core.shift）— ADR-116
========================================================
給定時間點 → 判斷屬哪個班別（morning/evening/night）、該用哪種排程模式
（peak_shuttle / offpeak / night），以及該班是否允許跨區。
另提供勞基法工時檢查：連續工時是否達上限、是否該預警休息。

職責（單一）：只做「時間→班別/模式」與「工時→是否可派/預警」的判斷。
不做：排程本身（在 dispatcher）、任務狀態（在 task_manager）。

對外暴露：
    current_shift(now) -> str | None          # morning/evening/night
    shift_of(now) -> dict                      # 該班完整設定（含 allow_cross_district、尖峰）
    current_mode(now) -> str                   # peak_shuttle / offpeak / night
    allow_cross_district(now) -> bool          # 當前班別是否允許跨區
    is_in_peak(now) -> bool                    # 當前是否在尖峰時段
    check_labor(work_minutes) -> dict          # 工時檢查：可否派任務、是否預警、建議休息
"""

from __future__ import annotations
import datetime as _dt
from typing import Optional

from config_loader import get_config


def _to_min(hhmm: str) -> int:
    """'HH:MM' → 當日分鐘數。空字串回 -1。"""
    if not hhmm:
        return -1
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def _now_min(now: Optional[_dt.datetime]) -> int:
    # 班別時段以台灣時間定義；雲端容器為 UTC，未給 now 時一律取台北現在時間，
    # 否則會判錯班別（如 UTC 09:00 誤判早班，實際台灣 17:00 是晚班）。
    # 傳入的 now（測試/指定）視為台北時間，直接用其時分。
    if now is None:
        now = _dt.datetime.now(_dt.timezone(_dt.timedelta(hours=8)))
    return now.hour * 60 + now.minute


def _in_window(cur: int, start: int, end: int) -> bool:
    """cur 是否落在 [start, end)。end < start 視為跨午夜。"""
    if start <= end:
        return start <= cur < end
    # 跨午夜（如 22:00–06:30）：cur >= start 或 cur < end
    return cur >= start or cur < end


def current_shift(now: Optional[_dt.datetime] = None) -> Optional[str]:
    """回傳當前班別 key（morning/evening/night），無對應回 None（理論上三班連續覆蓋不會 None）。"""
    cfg = get_config().get("shifts", {})
    cur = _now_min(now)
    for name, s in cfg.items():
        if _in_window(cur, _to_min(s["start"]), _to_min(s["end"])):
            return name
    return None


def shift_of(now: Optional[_dt.datetime] = None) -> dict:
    """回傳當前班別的完整設定 dict（含 name）；無對應回空 dict。"""
    name = current_shift(now)
    if name is None:
        return {}
    s = dict(get_config()["shifts"][name])
    s["name"] = name
    return s


def is_in_peak(now: Optional[_dt.datetime] = None) -> bool:
    """當前是否在所屬班別的尖峰時段。"""
    s = shift_of(now)
    if not s or not s.get("peak_start"):
        return False
    cur = _now_min(now)
    return _in_window(cur, _to_min(s["peak_start"]), _to_min(s["peak_end"]))


def current_mode(now: Optional[_dt.datetime] = None) -> str:
    """排程模式（ADR-117）：
    - night 班 → 'night'（跨區大宗復原）
    - 其他班且在尖峰 → 'peak_shuttle'（折返）
    - 其他班非尖峰 → 'offpeak'（效率最大化）
    無班別對應時退回 'offpeak'（安全預設）。
    """
    name = current_shift(now)
    if name == "night":
        return "night"
    if name is None:
        return "offpeak"
    return "peak_shuttle" if is_in_peak(now) else "offpeak"


def allow_cross_district(now: Optional[_dt.datetime] = None) -> bool:
    """是否允許跨區調度。ADR-316：所有時段（早/晚/大夜）皆允許跨區——調度以「同區優先、
    跨區次之」的排序達成，不再用班別硬性禁止跨區（原早晚班 False 已移除）。

    仍保留 config 開關：shifts[班].allow_cross_district 明確設 false 時才禁（預設允許）。
    """
    s = shift_of(now)
    return bool(s.get("allow_cross_district", True))


def check_labor(work_minutes: float) -> dict:
    """勞基法工時檢查（ADR-116）。

    work_minutes：該人員「連續工作」累計分鐘。
    回傳：
      can_dispatch：是否還可接新任務（未達連續工時上限）
      needs_warning：是否進入預警區（接近上限，該準備休息）
      rest_required：是否已達上限、必須休息
      rest_minutes：建議休息時長
      message：人看得懂的說明
    """
    labor = get_config().get("labor", {})
    cap = float(labor.get("連續工時上限_分鐘", 240))
    warn = float(labor.get("工時預警_分鐘", 180))
    rest = int(labor.get("休息時間_分鐘", 30))

    if work_minutes >= cap:
        return {
            "can_dispatch": False, "needs_warning": True, "rest_required": True,
            "rest_minutes": rest,
            "message": (f"已連續工作 {work_minutes:.0f} 分鐘，達上限 {cap:.0f} 分鐘"
                        f"（勞基法），須休息 {rest} 分鐘後才可接任務"),
        }
    if work_minutes >= warn:
        remain = cap - work_minutes
        return {
            "can_dispatch": True, "needs_warning": True, "rest_required": False,
            "rest_minutes": rest,
            "message": (f"已連續工作 {work_minutes:.0f} 分鐘，距上限 {cap:.0f} 分鐘剩 "
                        f"{remain:.0f} 分鐘，建議安排休息"),
        }
    return {
        "can_dispatch": True, "needs_warning": False, "rest_required": False,
        "rest_minutes": 0, "message": "工時正常",
    }
