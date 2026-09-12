"""空／滿站緊急時計與近 24 小時站況（ADR-324／328）。只讀彙總，不派工。"""

from fastapi import APIRouter, HTTPException

from core.service_problems import snapshot, station_history
from core.data import get_stations_with_degradation

router = APIRouter(prefix="/api/v1", tags=["service-problems"])


@router.get("/service-problems")
def service_problems():
    """進行中空／滿時計＋近 24 小時排除平均＋站況收集覆蓋。"""
    get_stations_with_degradation()
    return snapshot()


@router.get("/station-history/{station_id}")
def station_history_api(station_id: str):
    """單一站近 24 小時背景快照。不觸發即時抓站。"""
    station_id = (station_id or "").strip()
    if not station_id:
        raise HTTPException(status_code=400, detail="缺少 station_id")
    return station_history(station_id)
