"""
熱門站設備故障偵測（core.fault_detection）— ADR-336
==================================================
概念：熱門站在尖峰流量大時，正常應該有機會被借到接近全空、或被還到接近全滿。若一個
熱門站在尖峰時段的近半小時內，可借車數一直「卡在某下限值上不去/下不去、始終碰不到全空
或全滿」，那很可能有設備故障把車或柱卡死了：

  - 疑似「車故障」：available_bikes 半小時卡在下限 L 借不走（一直有 L 台借不出）
      → 那 L 台疑似是壞車鎖在柱上。故障數 ≈ L。
  - 疑似「柱故障」：available_docks 半小時卡在下限 M 還不進（一直有 M 個柱還不了）
      → 那 M 個柱疑似故障。故障數 ≈ M。

判定條件（三重保守，降低誤判）：
  1. 熱門站：站×當前小時的歷史周轉量 ≥ 全市 P90（前 10%，最活躍的大站）。
  2. 近半小時序列 ≥ 最小筆數（預設 5，官方 5 分一筆≈半小時 6 筆）。
  3. 卡住：整段都沒碰到極值（沒空/沒滿）、且變化範圍窄（≤ 容差），下限穩定。

偵測只回「疑似故障」標記與估計數量；扣除重算（空滿率、緊急度）與顯示由呼叫端處理。
純函式為主，可獨立測試；只讀既有站況序列，不寫入。
"""

from __future__ import annotations

import datetime as _dt
from typing import Optional

_TURNOVER = None  # 站×hour 周轉表快取


def _cfg() -> dict:
    from config_loader import get_config
    return get_config().get("fault_detection", {}) or {}


def _load_turnover() -> dict:
    global _TURNOVER
    if _TURNOVER is None:
        import json
        from pathlib import Path
        p = Path(__file__).parent.parent / "features" / "station_hour_turnover.json"
        _TURNOVER = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {
            "by_station_hour": {}, "station_avg": {}, "global_p90": 2.323}
    return _TURNOVER


def is_hot_station(station: dict) -> bool:
    """熱門站：站×當前小時的歷史周轉量 ≥ 全市 P90（config 可改 P 分位）。

    用 station_key（lat_lng）+ hour 查 station_hour_turnover.json，
    查無該站×時就退回該站整體平均，仍查無視為非熱門。
    """
    t = _load_turnover()
    threshold = float(_cfg().get("熱門周轉門檻", t.get("global_p90", 2.323)))
    sk = station.get("station_key") or ""
    hour = station.get("hour")
    if hour is None:
        return False
    by = t.get("by_station_hour", {}).get(str(sk), {})
    val = by.get(str(int(hour)))
    if val is None:
        val = t.get("station_avg", {}).get(str(sk))
    if val is None:
        return False
    return float(val) >= threshold


def _series_since(station_id: str, minutes: int) -> list[dict]:
    """近 minutes 分鐘的單站快照序列（含 available_bikes/docks/total）。

    優先用 station_snapshots_repo（ADR-328 的 24h 快照 DB，欄位齊全、可 since 過濾）；
    讀不到（獨立時計庫不可用）回空 list，偵測那站這輪跳過。
    """
    try:
        from db import station_snapshots_repo
        from core.data.observations import TAIPEI
        since = (_dt.datetime.now(TAIPEI) - _dt.timedelta(minutes=minutes)).isoformat(timespec="seconds")
        return station_snapshots_repo.list_for_station(station_id, since=since)
    except Exception:  # noqa: BLE001
        return []


def detect_fault(station: dict) -> Optional[dict]:
    """偵測單一（熱門）站是否疑似設備故障。回故障資訊 dict 或 None（無疑似故障）。

    回傳：{"fault_type": "vehicle"|"dock", "fault_count": int, "reason": str}
      vehicle：疑似車故障（壞車鎖住借不出）；dock：疑似柱故障（壞柱還不進）。
    只對熱門站判定；非熱門、序列不足、有碰到極值、或變化過大者一律回 None（不誤標）。
    """
    cfg = _cfg()
    if not cfg.get("enabled", True):
        return None
    if not is_hot_station(station):
        return None

    window = int(cfg.get("視窗分鐘", 30))
    min_points = int(cfg.get("最小筆數", 5))
    tol = int(cfg.get("卡住變化容差_台數", 2))   # 半小時內變化 ≤ 此值視為「卡住不動」

    sid = str(station.get("station_id"))
    series = _series_since(sid, window)
    if len(series) < min_points:
        return None

    bikes = [int(p["available_bikes"]) for p in series if p.get("available_bikes") is not None]
    docks = [int(p["available_docks"]) for p in series if p.get("available_docks") is not None]
    if len(bikes) < min_points or len(docks) < min_points:
        return None

    bike_lo, bike_hi = min(bikes), max(bikes)
    dock_lo, dock_hi = min(docks), max(docks)

    bike_stuck = bike_lo > 0 and (bike_hi - bike_lo) <= tol   # 可借車數卡住、從沒借到空
    dock_stuck = dock_lo > 0 and (dock_hi - dock_lo) <= tol   # 可還位卡住、從沒還到滿

    # 站接近哪一端卡住，決定是車故障還是柱故障——避免「柱故障導致車還不進、可借一直高」被
    # 誤判成車故障（反之亦然）。判準：比較卡住那端離極值多近（下限誰更小＝更接近該極值）。
    #   車故障：站偏空側卡住（可借下限 L 比可還下限更接近 0）→ 那 L 台疑似壞車借不走。
    #   柱故障：站偏滿側卡住（可還下限 M 比可借下限更接近 0）→ 那 M 個柱疑似故障還不進。
    if bike_stuck and dock_stuck:
        # 兩端都卡（少見）：取更接近極值的那端為主因。
        if bike_lo <= dock_lo:
            dock_stuck = False
        else:
            bike_stuck = False

    if bike_stuck:
        return {
            "fault_type": "vehicle",
            "fault_count": bike_lo,
            "reason": (f"熱門站近 {window} 分鐘可借車數卡在 {bike_lo}~{bike_hi} 台、"
                       f"始終借不到全空，疑似 {bike_lo} 台故障車鎖住借不出"),
        }
    if dock_stuck:
        return {
            "fault_type": "dock",
            "fault_count": dock_lo,
            "reason": (f"熱門站近 {window} 分鐘可還位數卡在 {dock_lo}~{dock_hi} 個、"
                       f"始終還不到全滿，疑似 {dock_lo} 個柱位故障還不進"),
        }
    return None
