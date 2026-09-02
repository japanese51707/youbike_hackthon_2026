"""
預測結果 Schema（對齊 api_contract §2.2）
只有「預測數字 + 不確定區間」。緊急度不在這裡（那是 calc_urgency 另外算，
放在 DispatchRecommendation.priority_score）。
"""

from enum import Enum
from typing import Optional
from pydantic import BaseModel


class HorizonSource(str, Enum):
    """前瞻窗口來源（C-03）"""
    dispatch = "dispatch"   # 派任務時，動態 = 調度到達時間
    default = "default"     # 警示掃描/歷史回填，固定 config.fleet.響應時間_分鐘


class Prediction(BaseModel):
    station_id: str
    predict_from: str               # 起算時間
    predict_target_time: str        # 目標時刻 = predict_from + horizon_minutes
    horizon_minutes: int            # 預測多久之後
    horizon_source: HorizonSource
    predicted_available: float      # 預測未來某時刻的可借車數（點估計）
    lower_bound: float              # 動態信賴區間下界（規則引擎吃這個觸發）
    upper_bound: float              # 動態信賴區間上界

    # B 只需保證回傳 predicted_available / lower_bound / upper_bound 三欄，
    # 其餘時間/識別欄位由 A 組裝 API 回應時補齊。
