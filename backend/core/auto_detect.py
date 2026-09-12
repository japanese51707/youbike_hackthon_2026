"""
ADR-310：自動偵測調度完成
==========================
調度員執行任務時不必人工回報「拉/放了幾台車」。背景輪詢官方即時站況，
偵測進行中任務的待處理站是否已達派工目標（補車→可借車數上升逼近 target；
取車→下降逼近 target），達標即代呼叫既有 report_station(auto=True) 自動標記完成、
推進任務、最後一站自動結案並釋放資源。

判斷哲學（對齊 ADR-004 人在迴圈的補充）：不論車是調度員搬的、還是剛好有一批人
借/還造成的，只要該站已達目標水位，對該站而言「調度需求已消化」，任務對該站即完成。
與 _demand_resolved（抽離站點時判斷需求是否消化）同一思路。

只在真實資料源（非 mock）且 config 開關開啟時運作；判斷用即時序列的
「任務開始後基準值 vs 現值」，序列不足時退回用組單當下的 current_available 當基準。
"""

from __future__ import annotations

import threading
import time
from typing import Optional


def _cfg() -> dict:
    from config_loader import get_config
    return get_config().get("auto_detect", {}) or {}


def reached_target(stop: dict, current_available: float, baseline_available: float,
                   tolerance: float, min_change_ratio: float) -> bool:
    """單站是否已達派工目標（純函式，可獨立測試）。

    stop：任務的一個 route 站點，需含 action（補車/取車）、target_available、quantity。
    current_available：該站最新可借車數。
    baseline_available：任務開始時該站的可借車數（判斷變化方向與量）。
    tolerance：逼近目標的容差（台）——現值落在目標 ± 容差內即算逼近。
    min_change_ratio：最小變化量佔派工量的比例——變化需至少達 quantity×此比例，
                      避免把自然借還波動誤判成調度已完成。

    補車站：可借車數應「上升」且逼近（≥ target − 容差）。
    取車站：可借車數應「下降」且逼近（≤ target + 容差）。
    無 target 或無法判斷時回 False（保守：不自動完成）。
    """
    action = stop.get("action")
    target = stop.get("target_available")
    if target is None or action not in ("補車", "取車"):
        return False
    try:
        now = float(current_available)
        base = float(baseline_available)
        target = float(target)
    except (TypeError, ValueError):
        return False

    change = now - base
    quantity = float(stop.get("quantity") or stop.get("est_quantity") or 0)
    min_change = max(1.0, quantity * float(min_change_ratio))  # 至少變動 1 台

    if action == "補車":
        # 車數要上升，且升到接近/超過目標
        return change >= min_change and now >= target - tolerance
    # 取車：車數要下降，且降到接近/低於目標
    return -change >= min_change and now <= target + tolerance


def _baseline_for(stop: dict, station_row: Optional[dict], assigned_at: Optional[str]) -> Optional[float]:
    """該站在任務開始時的基準可借車數。

    優先用即時觀測序列中「任務開始（assigned_at）之後最早的點」；序列不足時退回
    組單當下記錄的 current_available（草稿產生時的站況）。都拿不到回 None（不判定）。
    """
    from core.data import observations
    from core.data.observations import parse_time

    if station_row is not None:
        series = observations.recent(station_row)  # [(ts, available_bikes), ...] 已排序
        if series:
            if assigned_at:
                try:
                    start = parse_time(assigned_at)
                    after = [v for (ts, v) in series if ts >= start]
                    if after:
                        return float(after[0])
                except (ValueError, TypeError):
                    pass
            # 沒有 assigned_at 或其後無點：用序列最早點當基準
            return float(series[0][1])
    # 退回組單當下車況
    cur = stop.get("current_available")
    return float(cur) if cur is not None else None


def scan_once() -> list[dict]:
    """掃描一次：對所有進行中任務的待處理站，達標者自動回報完成。

    回傳本輪自動完成的紀錄清單（供測試/日誌）。任何單站錯誤都吞掉，不讓迴圈崩。
    """
    from core.data.degradation import get_stations_with_degradation
    from core.task_manager import get_task_manager
    from core import task_execution
    from core.dispatch_errors import DispatchConflict

    cfg = _cfg()
    tolerance = float(cfg.get("逼近容差_台數", cfg.get("tolerance_bikes", 2)))
    min_ratio = float(cfg.get("最小變化比例", cfg.get("min_change_ratio", 0.5)))

    # 取最新即時站況（副作用會 record 進 observations 序列），建索引
    try:
        rows = get_stations_with_degradation()
    except Exception:
        return []  # 站況暫時拿不到，這輪跳過
    by_id = {str(r.get("station_id")): r for r in rows}

    completed: list[dict] = []
    tm = get_task_manager()
    for task in tm.pending_or_active():
        if task.get("resources_released") or task.get("task_status") not in ("assigned", "in_progress"):
            continue
        assigned_at = task.get("assigned_at")
        for stop in task.get("route", []) or []:
            if not isinstance(stop, dict) or stop.get("station_status", "pending") != "pending":
                continue
            sid = str(stop.get("station_id"))
            row = by_id.get(sid)
            if row is None:
                continue
            # 只採用可用於決策的即時資料（live/mock；stale/offline 不自動判定）
            if not row.get("dispatch_eligible", True):
                continue
            now_avail = row.get("available_bikes")
            baseline = _baseline_for(stop, row, assigned_at)
            if now_avail is None or baseline is None:
                continue
            if not reached_target(stop, now_avail, baseline, tolerance, min_ratio):
                continue
            try:
                res = task_execution.report_station(
                    task["task_id"], sid, int(now_avail),
                    operator=task.get("assigned_operator") or "system-auto", auto=True)
                completed.append({"task_id": task["task_id"], "station_id": sid,
                                  "available_bikes": int(now_avail),
                                  "target": stop.get("target_available"),
                                  "status": res.get("status")})
            except (DispatchConflict, KeyError):
                # 已被人工回報/站已移除/任務狀態改變：略過，不中斷迴圈
                continue
            except Exception:
                continue
    return completed


# ── 背景輪詢迴圈（daemon thread；main.py lifespan 啟動）──
_stop_event: Optional[threading.Event] = None
_thread: Optional[threading.Thread] = None


def _loop(interval_sec: float, stop_event: threading.Event) -> None:
    while not stop_event.is_set():
        try:
            found = scan_once()
            if found:
                print(f"[auto_detect] 自動偵測達標並回報 {len(found)} 站："
                      f"{[(c['station_id'], c['status']) for c in found]}")
        except Exception as e:  # noqa: BLE001
            print(f"[auto_detect] 輪詢發生錯誤（略過本輪）：{e}")
        stop_event.wait(interval_sec)


def start_background(mode: str) -> bool:
    """啟動背景自動偵測（daemon thread）。回傳是否有啟動。

    僅在 config auto_detect.enabled 為真、且資料源為真實源（非 mock/None）時啟動。
    """
    global _stop_event, _thread
    cfg = _cfg()
    if not cfg.get("enabled", False):
        return False
    if mode in (None, "mock"):
        return False  # mock 資料不動，沒有自動偵測的意義
    if _thread is not None and _thread.is_alive():
        return True   # 已在跑
    interval = float(cfg.get("輪詢間隔_秒", cfg.get("interval_sec", 60)))
    _stop_event = threading.Event()
    _thread = threading.Thread(
        target=_loop, args=(interval, _stop_event), daemon=True, name="auto-detect")
    _thread.start()
    return True


def stop_background() -> None:
    """停止背景輪詢（測試/關機用）。"""
    global _stop_event, _thread
    if _stop_event is not None:
        _stop_event.set()
    _thread = None
