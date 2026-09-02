"""
警示通知 Schema（對齊 api_contract §2.5）
題目明確點名：現行機關系統無警示通知功能 → 這是差異化亮點。
Alert 是「警示事件」，用緊急度決定 level；空滿率本身在 StationStatus。
"""

from enum import Enum
from typing import Optional
from pydantic import BaseModel


class AlertLevel(str, Enum):
    info = "info"          # 提示 → 藍
    warning = "warning"    # 警告（即將出問題）→ 黃
    critical = "critical"  # 緊急（已空/滿或必定發生）→ 紅


class Alert(BaseModel):
    alert_id: str
    level: AlertLevel
    station_id: str
    station_name: str
    district: str
    message: str                        # 警示內容（人話）
    triggered_at: str
    suggested_action: Optional[str] = None
    acknowledged: bool = False          # 是否已讀


class AlertSubscription(BaseModel):
    """機關 webhook 訂閱（正式上線用）。callback 需驗證來源（出向資安）。"""
    subscription_id: str
    callback_url: str
    levels: list[AlertLevel]
    districts: list[str]
    token: Optional[str] = None         # 驗證用
