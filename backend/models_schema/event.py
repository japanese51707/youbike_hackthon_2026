"""
活動事件 Schema（對齊 api_contract §2.7 + 使用者新增 dispatch_requested）
影響程度用「供需比」：活動人數 / 半徑內站點總車柱數。
"""

from typing import Optional
from pydantic import BaseModel, Field


class AffectedStation(BaseModel):
    station_id: str
    distance_km: float
    influence_factor: float   # 影響度（供需比 × 距離衰減）


class Event(BaseModel):
    event_id: str
    event_name: str
    location: dict = Field(description='{"lat": ..., "lng": ...}')
    expected_attendance: int
    event_type: str                    # concert / sports / festival ...
    start_time: str
    end_time: str
    dispatch_requested: bool = False   # 是否申請 YouBike 調度（使用者新增）
    influence_radius_km: Optional[float] = None   # 系統換算，最遠約 2km
    affected_stations: list[AffectedStation] = Field(default_factory=list)
