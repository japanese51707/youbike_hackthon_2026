"""
資料降級策略（NFR-10）
=======================
即時資料源掛掉或資料過期時，系統不能直接崩潰或給錯資料，而是「優雅降級」：
退回歷史同時段推估，並明確標記資料新鮮度，讓上層與前端知道「這不是即時值」。

呼應原則：
  - steering §4 失敗要看得見：降級要標記，不靜默假裝即時
  - NFR-10：即時源不可用時走歷史同時段，資料標 data_freshness

data_freshness 語意（寫進每筆站點）：
  - live       ：即時源正常
  - stale      ：即時源有回應但資料太舊（超過門檻）
  - historical ：即時源掛了，改用歷史同時段推估（降級）
  - degraded   ：連歷史都取不到，回最後已知或空（最嚴重）

對外暴露：
  get_stations_with_degradation(district, status) -> list[dict]
  這是「有降級保護」的取站點入口，API 層應呼叫這個而非直接打即時源。
"""

from __future__ import annotations
from datetime import datetime, timedelta
from typing import Optional

from .data_source import get_data_source


def _cfg() -> dict:
    from config_loader import get_config
    c = get_config()
    ds = c.get("data_source", {})
    return {
        "mode": ds.get("mode", "mock"),
        # 即時資料超過幾秒算過期（沒設就用 refresh 的 3 倍當寬容值）
        "stale_after_sec": ds.get("stale_after_sec", ds.get("refresh_interval_sec", 60) * 3),
    }


def _is_stale(source_timestamp: Optional[str], stale_after_sec: int) -> bool:
    """判斷單筆資料是否過期（source_timestamp 距今超過門檻）。"""
    if not source_timestamp:
        return True
    try:
        ts = datetime.fromisoformat(source_timestamp)
    except (ValueError, TypeError):
        return True
    return datetime.now() - ts > timedelta(seconds=stale_after_sec)


def get_stations_with_degradation(
    district: Optional[str] = None,
    status: Optional[str] = None,
) -> list[dict]:
    """有降級保護的取站點：即時源掛了/過期就退回歷史，並標記 data_freshness。

    流程：
      1. mock 模式：直接回 mock（開發階段不需降級）
      2. 即時源健康 → 取即時；若個別站資料過期，逐筆標 stale
      3. 即時源不健康 → 退回 historical 同時段，整批標 historical
      4. 連 historical 都失敗 → 回空並在旁記錄（呼叫端可再 fallback）
    """
    cfg = _cfg()
    mode = cfg["mode"]

    # mock / historical 本身就是穩定源，不需降級，直接回
    if mode in ("mock", "historical"):
        return get_data_source().get_stations(district, status)

    # 即時源（tdx / youbike_official）：檢查健康
    primary = get_data_source()
    health = primary.health()

    if health.get("available"):
        try:
            rows = primary.get_stations(district, status)
            # 逐筆檢查過期
            for r in rows:
                if _is_stale(r.get("source_timestamp"), cfg["stale_after_sec"]):
                    r["data_freshness"] = "stale"
            return rows
        except Exception:
            pass  # 即時取用失敗 → 往下降級

    # 降級：退回歷史
    try:
        fallback = get_data_source(force_mode="historical")
        rows = fallback.get_stations(district, status)
        for r in rows:
            r["data_freshness"] = "historical"   # 明確標記為降級來源
        return rows
    except Exception:
        # 連歷史都掛：回空，不假裝有資料（失敗要看得見）
        return []


def degradation_status() -> dict:
    """回報目前資料源與降級狀態（給監控/前端顯示用）。"""
    cfg = _cfg()
    primary = get_data_source()
    h = primary.health()
    degrading = cfg["mode"] in ("tdx", "youbike_official") and not h.get("available")
    return {
        "mode": cfg["mode"],
        "primary_available": h.get("available"),
        "primary_detail": h.get("detail"),
        "degrading_to_historical": degrading,
        "stale_after_sec": cfg["stale_after_sec"],
    }
