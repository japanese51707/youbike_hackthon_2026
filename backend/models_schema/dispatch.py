"""
調度相關 Schema（對齊 api_contract §2.3 / 2.4）
- DispatchRecommendation：調度建議（含緊急度 priority_score 0~100）
- DispatchTask：調度任務（含路線、狀態機、Google Maps）
"""

from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class DispatchAction(str, Enum):
    supply = "補車"
    collect = "取車"


class PriorityLevel(str, Enum):
    high = "high"
    medium = "medium"
    low = "low"


class DispatchRecommendation(BaseModel):
    recommendation_id: str
    station_id: str
    station_name: str
    district: str
    action: DispatchAction
    quantity: int
    priority_score: float           # 緊急度分數 0~100（與 urgency 同尺度）
    priority_level: PriorityLevel
    reason: str                     # 人看得懂的中文觸發原因
    current_available: int
    predicted_at_arrival: float     # 預測調度員到達時的存量（前瞻窗口核心）
    lat: float
    lng: float


class TaskType(str, Enum):
    normal = "normal"        # 一般任務：綁定調度員，不可轉派
    emergency = "emergency"  # 緊急任務：未執行前可轉派


class TaskStatus(str, Enum):
    pending = "pending"                  # 待派發
    assigned = "assigned"                # 已指派、未開始（可轉派）
    in_progress = "in_progress"          # 執行中（鎖定）
    completed = "completed"              # 完成（已驗證）
    retryable = "retryable"              # 失敗可重試
    manual_required = "manual_required"  # 需人工介入
    cancelled = "cancelled"              # 已取消（如：來源覆寫到期，尚未開始的任務一併取消）


class StopStatus(str, Enum):
    pending = "pending"   # 尚未抵達
    done = "done"         # 完成
    skipped = "skipped"   # 跳過（已由他人處理）


class RouteStop(BaseModel):
    seq: int
    station_id: str
    station_name: str
    action: DispatchAction
    quantity: int
    lat: float
    lng: float
    stop_status: StopStatus = StopStatus.pending
    # ADR-123 逐站到達可行性（確認當下算定；None 代表尚未計算或超出預測視野）
    arrival_offset_min: Optional[float] = None   # 預估自出發起算的到達偏移（分鐘）
    horizon_used_min: Optional[int] = None       # 該站採用的預測視野（30/60/90/120）
    onboard_after: Optional[int] = None          # 完成該站後車上台數


class DispatchTask(BaseModel):
    task_id: str
    task_type: TaskType
    assigned_operator: Optional[str] = None   # 司機（主責）
    assigned_escort: Optional[str] = None     # ADR-308 隨車人員（可選第二名）
    task_status: TaskStatus = TaskStatus.pending
    route: list[RouteStop] = Field(default_factory=list)
    estimated_travel_minutes: Optional[int] = None
    estimated_work_minutes: Optional[int] = None
    estimated_total_minutes: Optional[int] = None
    estimated_distance_km: Optional[float] = None
    estimated_fuel_cost: Optional[float] = None
    route_map_url: Optional[str] = None      # Google Maps 導航連結
    assigned_at: Optional[str] = None
    # 若此任務因某站的③即時覆寫而產生，記來源站；覆寫到期時，仍在 assigned 者一併取消
    source_override_station_id: Optional[str] = None
    # ADR-123 車上載量（出車時算定／依載量計畫預估的收車載量）；None=未知
    onboard_start: Optional[int] = None
    onboard_planned_end: Optional[int] = None
