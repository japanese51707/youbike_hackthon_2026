"""天氣端點（3.18，ADR-118）。by-location 接 CWA 即時（觀測站級）；舊 /weather 保留相容。"""

from fastapi import APIRouter, HTTPException
from mock_store import get_mock

router = APIRouter(prefix="/api/v1", tags=["weather"])


@router.get("/weather/by-location")
def weather_by_location(lat: float, lng: float):
    """3.18 指定座標的即時天氣（CWA 最近測站，ADR-118）。

    回：最近雨量站（now/past10/past1hr）+ 最近氣象站（condition/temp/humidity）。
    CWA 未就緒（無 key/連線失敗）時降級標記，不中斷。
    """
    try:
        from core.data.weather_source import get_weather_source
        src = get_weather_source()
        rain = src.get_rainfall_by_location(lat, lng)
        wx = src.get_weather_by_location(lat, lng)
        return {"source": src.name, "rainfall": rain, "weather": wx}
    except Exception as e:
        raise HTTPException(status_code=503,
                            detail=f"即時天氣源暫時不可用：{type(e).__name__}")


@router.get("/weather")
def weather(district: str = "中和區"):
    """3.18 天氣現況（相容端點，回 mock 摘要）。逐站即時請改用 /weather/by-location。"""
    return get_mock()["weather"]
