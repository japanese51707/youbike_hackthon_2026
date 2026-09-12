"""道路實走路線端點（呈現層）。

前端把「起點 + 停靠點順序」丟進來，拿回沿著道路的折線幾何去畫地圖。
金鑰與外部服務都留在後端（比照天氣/預測），前端不需要任何金鑰。
路由服務不可用時回 mode="straight"，前端必須照實標示為直線示意。
"""

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

router = APIRouter(prefix="/api/v1", tags=["routing"])


class RoadRouteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # [[lng, lat], ...]，已排好的行駛順序
    coordinates: list[list[float]] = Field(min_length=2, max_length=25)


@router.post("/routing/road")
def road_route(body: RoadRouteRequest):
    """3.24 依序經過各座標的實走道路折線。

    回：{ mode: "road"|"straight", provider, geometry: [[lng,lat],...],
          distance_m, duration_s, note }
    """
    from core.road_routing import road_route as compute
    # 邊界防護（ADR-007）：只收合法經緯度，其他一律擋在外面
    cleaned = []
    for point in body.coordinates:
        if len(point) != 2:
            continue
        lng, lat = float(point[0]), float(point[1])
        if -180 <= lng <= 180 and -90 <= lat <= 90:
            cleaned.append([lng, lat])
    if len(cleaned) < 2:
        return {
            "mode": "straight", "provider": None, "geometry": cleaned,
            "distance_m": None, "duration_s": None, "note": "有效座標不足兩點",
        }
    return compute(cleaned)
