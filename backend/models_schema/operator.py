"""
調度員相關 Schema（對齊 api_contract §2.8 / 2.9）
- Operator：調度員狀態、位置、任務佇列、今日統計
- DispatchOverview：全域調度總覽（給後台/長官）
注意：「誰做了什麼、何時完成」的操作紀錄放 AuditLog（common.py），
      Operator 存的是「這個人現在的狀態」。
"""

from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class OperatorRole(str, Enum):
    operator = "operator"       # 外勤調度員（只能回報自己任務）
    dispatcher = "dispatcher"   # 後台調派員（可確認派發、緊急覆寫）
    maintainer = "maintainer"   # 維護人員（可審核每日最適化、調參）


class OperatorStatus(str, Enum):
    on_duty = "on_duty"     # 上班中，可派任務
    busy = "busy"           # 執行任務中
    resting = "resting"     # 休息中（法定/疲勞）
    off_duty = "off_duty"   # 下班


class Coordinate(BaseModel):
    lat: float
    lng: float


class TodayStats(BaseModel):
    completed_tasks: int = 0
    total_bikes_moved: int = 0
    total_work_minutes: int = 0
    on_duty_since: Optional[str] = None


class Operator(BaseModel):
    operator_id: str
    name: str
    role: OperatorRole = OperatorRole.operator
    status: OperatorStatus = OperatorStatus.off_duty
    current_location: Optional[Coordinate] = None
    current_task_id: Optional[str] = None
    task_queue: list[str] = Field(default_factory=list)  # 任務佇列（有序）
    today_stats: TodayStats = Field(default_factory=TodayStats)


class OperatorCounts(BaseModel):
    on_duty: int = 0
    busy: int = 0
    resting: int = 0
    off_duty: int = 0


class TodayTotals(BaseModel):
    completed_tasks: int = 0
    pending_tasks: int = 0
    emergency_tasks: int = 0
    total_bikes_moved: int = 0
    total_distance_km: float = 0
    estimated_fuel_cost: float = 0


class StationSummary(BaseModel):
    empty_stations: int = 0
    full_stations: int = 0
    need_dispatch: int = 0


class DispatchOverview(BaseModel):
    """全域調度總覽（宏觀儀表板，給後台調派員 + 長官）"""
    timestamp: str
    operators: OperatorCounts
    today_totals: TodayTotals
    station_summary: StationSummary
