"""
站點相關 Schema（對齊 api_contract §2.1 / 2.11 / 2.12）
- StationStatus：站點即時狀態
- StationParams：站點模型參數（三層架構）
- HistoryPoint：歷史趨勢點（時間軸/趨勢圖）
"""

from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class StationStatusEnum(str, Enum):
    """站點空滿現況（僅顯示分級，非緊急度）"""
    offline = "offline"
    empty = "empty"      # 空站（可借=0）→ 紅
    low = "low"          # 低水位（<15%）→ 橘
    normal = "normal"    # 正常 → 綠
    high = "high"        # 高水位（>85%）→ 紫
    full = "full"        # 滿站（可還=0）→ 深紅


class AreaType(str, Enum):
    residential = "residential"   # 住宅區
    commercial = "commercial"     # 商業區
    school = "school"             # 學區
    transit = "transit"           # 捷運/交通樞紐
    leisure = "leisure"           # 休閒/景點
    mixed = "mixed"               # 混合型


class Terrain(str, Enum):
    """地形 7 分類（坡度 × 坡向）"""
    flat = "flat"                    # 平地 0~3%
    gentle_up = "gentle_up"          # 緩坡上 3~5%
    gentle_down = "gentle_down"      # 緩坡下 3~5%
    moderate_up = "moderate_up"      # 中坡上 5~8%
    moderate_down = "moderate_down"  # 中坡下 5~8%
    steep_up = "steep_up"            # 陡坡上 >8%
    steep_down = "steep_down"        # 陡坡下 >8%


class DataFreshness(str, Enum):
    """資料新鮮度（NFR-10 降級標記）"""
    mock = "mock"
    historical = "historical"
    live = "live"                              # 即時
    stale = "stale"                            # 過期（用最後成功資料）
    historical_fallback = "historical_fallback"  # 歷史同時段估計


class StationStatus(BaseModel):
    station_id: str                       # TDX StationUID
    station_name: str
    station_key: str | None = None
    hour: int | None = None
    district: str
    lat: float
    lng: float
    total_docks: int                      # 總車柱數
    available_bikes: int                  # 可借車數
    available_docks: int                  # 可還位數（空車位）
    usage_rate: float                     # 借用率 0~100（%），= available_bikes/total_docks*100
    status: StationStatusEnum
    service_available: bool = True        # 是否啟用（TDX ServiceStatus）
    area_type: Optional[AreaType] = None  # 加值分析
    terrain: Optional[Terrain] = None     # 加值分析
    timestamp: str | None                # 官方觀測時間（相容欄位）
    source: str | None = None
    observed_at: str | None = None
    received_at: str | None = None
    observation_age_sec: float | None = None
    quality_reasons: list[str] = Field(default_factory=list)
    dispatch_eligible: bool = False
    source_timestamp: Optional[str] = None  # 資料源更新時間（TDX SrcUpdateTime）
    yb2_quantity: int | None = None
    eyb_quantity: int | None = None
    data_freshness: DataFreshness = DataFreshness.live


class ParamSource(str, Enum):
    base = "base"                  # ① 規則化基礎
    ai_optimized = "ai_optimized"  # ② AI 每日最適化
    # ③ 覆寫不寫參數，用 override_active 表示


class StationParams(BaseModel):
    """站點模型參數（三層架構）。target_level/buffer_level 為 0~1 比例。"""
    station_id: str
    params: dict = Field(
        default_factory=dict,
        description="outflow_rate/inflow_rate/target_level(0~1)/buffer_level(0~1)/nearby_stations/capacity_class",
    )
    target_usage_rate: float | None = None
    param_source: ParamSource = ParamSource.base
    override_active: bool = False          # ③ 是否有生效中的即時覆寫
    conditions: list = Field(default_factory=list)  # 參數背後條件說明
    last_optimized: Optional[str] = None


class HistoryPoint(BaseModel):
    """某站某歷史時間點的完整快照（時間軸/趨勢圖用）"""
    source: str | None = None
    identity_source: str | None = None
    station_id: str | None = None
    timestamp: str
    available_bikes: int
    available_docks: int
    usage_rate: float               # 0~100（%）
    urgency_score: float | None = None  # 緊急指數 0~100（回填歷史）
    status: StationStatusEnum
    anomaly_tags: list[str] = Field(
        default_factory=list,
        description="dispatch_intervention/event/holiday/school_vacation/weather_extreme/station_change/data_error",
    )


class HistoryStatus(BaseModel):
    status: str
    source: str = "historical"
    requested_start: str | None = None
    requested_end: str | None = None
    reason: str | None = None


class StationDetail(BaseModel):
    current: StationStatus
    prediction: "Prediction"
    params: StationParams | None = None
    history: list[HistoryPoint] = Field(default_factory=list)
    history_status: HistoryStatus


from .prediction import Prediction
StationDetail.model_rebuild()
