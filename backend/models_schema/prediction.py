"""
預測結果 Schema（對齊 api_contract §2.2，v4 多視野 ADR-107）
只有「預測數字 + 不確定區間」。緊急度不在這裡（那是 calc_urgency 另外算，
放在 DispatchRecommendation.priority_score）。

ADR-107：從單一視野改為 horizons[] 陣列（30/60/90/120 分）。
每個視野直接對「累積淨變化」訓練分位數（分位數不可加，不用單步相加）。
horizon_minutes 一律為分鐘數，不綁資料格數（粒度落差解法見 ADR-107/api_contract §2.2）。
"""

from enum import Enum
from pydantic import BaseModel, Field


class HorizonSource(str, Enum):
    """前瞻窗口來源（C-03）"""
    dispatch = "dispatch"   # 派任務時，動態 = 調度到達時間，挑最接近的 horizon
    default = "default"     # 警示掃描/歷史回填，用 30 分 horizon（config.fleet.響應時間_分鐘）


class HorizonPrediction(BaseModel):
    """單一視野的預測（horizons[] 的元素）。"""
    horizon_minutes: int            # 預測多少分鐘之後（分鐘數，不綁資料格數）
    predict_target_time: str        # 目標時刻 = predict_from + horizon_minutes
    predicted_available: float      # 該視野目標時刻的預測可借車數（點估計）
    lower_bound: float              # 動態區間下界（規則引擎吃下界觸發防空）
    upper_bound: float              # 動態區間上界（規則引擎吃上界觸發防滿）


class Prediction(BaseModel):
    station_id: str
    predict_from: str               # 起算時間（通常是現在）
    horizon_source: HorizonSource
    horizons: list[HorizonPrediction] = Field(default_factory=list)
    # 向後相容：陣列若只含一個元素等同舊的單一視野。
    # B 只需保證每個 horizon 回傳 predicted_available/lower_bound/upper_bound，
    # predict_from/target_time 等由 A 組裝 API 回應時補齊。
