"""
三層參數疊加（params.param_layers）
====================================
對齊 model_architecture「三層參數來源」：
    ③ 即時人工覆寫（最高，臨時）  ← 不寫參數，只影響 dispatcher 排序（見 A2/A3）
    ② AI 每日最適化參數           ← approve 後存版本
    ① 規則化基礎參數（最底層）     ← 建置時設

「當前生效參數」的組裝規則（重點：③不改參數值）：
  - 參數值 = 該站最新生效版本的 params（可能是 base 或 ai_optimized）
  - param_source = 該版本來源（base / ai_optimized）——不會是 emergency_override
  - override_active = 該站目前有無生效中的③覆寫（bool 狀態旗標）

為什麼③不併進參數：
  ③ 覆寫是「排序層」的臨時介入（dispatcher 最前綴），不竄改模型參數，
  否則同一件事會有兩個真相（review 提醒 #1/#2）。後台要顯示「覆寫中」讀 override_active。

對外暴露：
    get_effective_params(station_id) -> dict | None   # 當前生效參數 + override_active
"""

from __future__ import annotations
from typing import Optional

from db import params_repo


def get_effective_params(station_id: str) -> Optional[dict]:
    """回傳該站當前生效參數（含 param_source、override_active、target_usage_rate）。

    override_active 以「即時覆寫服務的實際狀態」為準（同步 DB 旗標），
    避免旗標與覆寫服務不一致。
    """
    active = params_repo.get_active(station_id)
    if active is None:
        return None

    # 以覆寫服務的實際狀態為準，順便回寫旗標保持一致
    from core.override_service import get_override_service
    is_overridden = get_override_service().is_active(station_id)
    if bool(active.get("override_active")) != is_overridden:
        params_repo.set_override_active(station_id, is_overridden)
        active = params_repo.get_active(station_id)

    # 附上換算好的 target_usage_rate（與 usage_rate 同尺度，見 I-3）
    tl = active.get("params", {}).get("target_level")
    if tl is not None:
        active["target_usage_rate"] = round(float(tl) * 100, 1)

    return active
