"""
ADR-313：需調度清單快取（背景預算，顯示端點讀快取）
====================================================
recommendations / alerts 等「顯示用」端點原本每次 request 都對全 1606 站重跑
build_dispatch_list（逐站 LightGBM 預測），且多個端點各算一次 → 前端一進來同時打
好幾個端點，後端就同時跑好幾次全量預測，非常慢（recommendations 冷 22s／熱 14s）。

即時站況本身約 5 分鐘才更新，這期間預測結果不變，每次 request 重算是純浪費。
本模組用「背景 thread 每 N 秒預算一次全量，結果進 TTL 快取」，所有顯示端點直接讀快取秒回。

原則（守正確性）：
  - 顯示端點（recommendations/alerts/overview）讀快取——60 秒延遲對展示無妨。
  - 派工端點（組單三入口 _current_dispatch_list、confirm）維持即時重算——派工是關鍵決策，要最新。
  - 快取內容 = {stations, recs（apply_capacity=False 完整排序清單）, computed_at}。
  - 首次讀取或快取過期且背景還沒補上時，同步算一次（不回空）。
"""

from __future__ import annotations

import threading
import time
from typing import Optional


def _cfg() -> dict:
    from config_loader import get_config
    return get_config().get("dispatch_cache", {}) or {}


def _ttl() -> float:
    return float(_cfg().get("ttl_sec", 60))


_lock = threading.RLock()
_cache: Optional[dict] = None          # {"stations": [...], "recs": [...], "computed_at": float}
_stop_event: Optional[threading.Event] = None
_thread: Optional[threading.Thread] = None


def _compute() -> dict:
    """實際跑一次全量：站況 + 覆寫 → build_dispatch_list（完整排序，不套量能上限）。"""
    from core.data import get_stations_with_degradation
    from core.override_service import get_override_service
    from core import build_dispatch_list

    stations = get_stations_with_degradation()
    overrides = get_override_service().active_station_ids()
    recs = build_dispatch_list(stations, override_station_ids=overrides, apply_capacity=False)
    return {"stations": stations, "recs": recs, "computed_at": time.monotonic()}


def _refresh() -> dict:
    global _cache
    result = _compute()
    with _lock:
        _cache = result
    return result


def get_snapshot() -> dict:
    """回快取的 {stations, recs}。無快取或已過期 → 同步算一次補上（不回空）。"""
    with _lock:
        cur = _cache
    fresh = cur and (time.monotonic() - cur["computed_at"]) < _ttl()
    if fresh:
        return cur
    # 過期或無：同步算（背景 thread 可能也在算，但這裡確保呼叫端拿到不過期的結果）
    return _refresh()


def get_recommendations(limit: int = 15, priority: Optional[str] = None) -> list[dict]:
    """顯示用需調度清單（讀快取）。切 limit / 篩 priority 在讀取端做，不重算。

    ADR-330：剔除「已被進行中任務認領（pending）」的站——站一旦被派單，就不該再出現在
    緊急/次安排清單（改到分派任務狀況頁追蹤）。認領狀態即時查（不受 60 秒快取延遲），
    派單後立刻從清單消失。已完成的站規則引擎本就會判定不需調度而淡出。
    """
    recs = get_snapshot()["recs"]
    try:
        from core.task_execution import station_claim_map
        claimed = set(station_claim_map().keys())
    except Exception:  # noqa: BLE001
        claimed = set()
    if claimed:
        recs = [r for r in recs if str(r.get("station_id")) not in claimed]
    if priority:
        recs = [r for r in recs if r.get("priority_level") == priority]
    return recs[:limit]


# ── 背景刷新 thread（main.py lifespan 啟動）──
def _loop(interval: float, stop_event: threading.Event) -> None:
    while not stop_event.is_set():
        try:
            _refresh()
        except Exception as e:  # noqa: BLE001
            print(f"[dispatch_cache] 背景刷新失敗（略過本輪）：{e}")
        stop_event.wait(interval)


def start_background(mode: str) -> bool:
    """啟動背景預算。僅 config enabled 且真實源（非 mock）時啟。回傳是否啟動。"""
    global _stop_event, _thread
    cfg = _cfg()
    if not cfg.get("enabled", True):
        return False
    if mode in (None, "mock"):
        return False
    if _thread is not None and _thread.is_alive():
        return True
    _stop_event = threading.Event()
    _thread = threading.Thread(
        target=_loop, args=(_ttl(), _stop_event), daemon=True, name="dispatch-cache")
    _thread.start()
    return True


def stop_background() -> None:
    global _stop_event, _thread
    if _stop_event is not None:
        _stop_event.set()
    _thread = None


def reset() -> None:
    """測試用：清快取。"""
    global _cache
    with _lock:
        _cache = None
