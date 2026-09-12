"""空／滿站緊急時計與今日排除時間（ADR-318）。只讀彙總，不派工。"""

from fastapi import APIRouter

from core.service_problems import snapshot
from core.data import get_stations_with_degradation

router = APIRouter(prefix="/api/v1", tags=["service-problems"])


@router.get("/service-problems")
def service_problems():
    """進行中空／滿時計＋今日各區平均排除時間。"""
    get_stations_with_degradation()
    return snapshot()
