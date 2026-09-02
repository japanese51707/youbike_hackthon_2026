"""core：後端核心業務邏輯（資料源、規則引擎、調度、任務狀態機等）。

注意：資料源層在 core.data 子套件（from core.data import ...），
不在這裡重匯出，避免載入 core 就強制載入 boto3/pandas 等重依賴。
"""

from .rule_engine import evaluate_station, generate_recommendations
from .dispatcher import build_dispatch_list
from .task_manager import TaskManager, IllegalTransition
from .interfaces import (
    PredictionInterval,
    get_predictor,
    get_urgency_calculator,
)
from .audit import get_audit_service
from .override_service import get_override_service
from .alert_service import get_alert_service, classify_alert_level

__all__ = [
    "evaluate_station",
    "generate_recommendations",
    "build_dispatch_list",
    "TaskManager",
    "IllegalTransition",
    "PredictionInterval",
    "get_predictor",
    "get_urgency_calculator",
    "get_audit_service",
    "get_override_service",
    "get_alert_service",
    "classify_alert_level",
]
