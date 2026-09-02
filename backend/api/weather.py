"""天氣端點（3.18）。A0 回 mock。"""

from fastapi import APIRouter
from mock_store import get_mock

router = APIRouter(prefix="/api/v1", tags=["weather"])


@router.get("/weather")
def weather(district: str = "中和區"):
    """3.18 天氣現況（人性化顯示 + 預測外部因子）"""
    return get_mock()["weather"]
