"""空／滿站緊急時計與近 24 小時站況（ADR-324／328）。只讀彙總，不派工。"""

from fastapi import APIRouter, HTTPException

from core.service_problems import empty_board, snapshot, station_history
from core.data import get_stations_with_degradation

router = APIRouter(prefix="/api/v1", tags=["service-problems"])


@router.get("/service-problems")
def service_problems():
    """進行中空／滿時計＋窗口內已排除平均＋站況收集覆蓋。

    窗口是「現在往回最多 24 小時」，有多少算多少，不必等滿 24 小時。
    站況同步失敗不擋讀庫，避免看板整卡空白。
    """
    try:
        get_stations_with_degradation()
    except Exception as exc:  # noqa: BLE001
        print(f"[service_problems] 同步站況失敗（仍回既有時計）：{exc}")
    try:
        return snapshot()
    except Exception as exc:  # noqa: BLE001
        print(f"[service_problems] 讀時計失敗：{exc}")
        return empty_board()


@router.get("/station-history/{station_id}")
def station_history_api(station_id: str):
    """單一站近 24 小時背景快照。不觸發即時抓站。"""
    station_id = (station_id or "").strip()
    if not station_id:
        raise HTTPException(status_code=400, detail="缺少 station_id")
    return station_history(station_id)
