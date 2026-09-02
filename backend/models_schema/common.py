"""
共用 Schema（對齊 api_contract §2.6 / 2.10）
- AuditLog：稽核記錄（含參數編輯、緊急覆寫、任務轉派等「誰做了什麼」）
- Weather：天氣現況（人性化顯示 + 預測外部因子）
"""

from enum import Enum
from typing import Optional
from pydantic import BaseModel


class AuditType(str, Enum):
    emergency_override = "emergency_override"  # ③ 即時覆寫
    task_transfer = "task_transfer"            # 動態轉派
    optimization = "optimization"              # ② 每日最適化套用
    param_edit = "param_edit"                  # 參數人工編輯
    task_report = "task_report"                # 任務回報


class AuditLog(BaseModel):
    log_id: str
    type: AuditType
    station_id: Optional[str] = None
    operator: str                       # 操作人
    action: str                         # 做了什麼
    reason: Optional[str] = None
    timestamp: str
    expired_at: Optional[str] = None            # 覆寫到期時間
    task_duration_minutes: Optional[int] = None  # 任務花費


class WeatherCondition(str, Enum):
    sunny = "sunny"
    cloudy = "cloudy"
    rain = "rain"
    heavy_rain = "heavy_rain"
    typhoon = "typhoon"


class Weather(BaseModel):
    district: str
    condition: WeatherCondition
    temperature: float
    rain_probability: int               # 0~100
    description: str                    # 人性化說明
    timestamp: str
