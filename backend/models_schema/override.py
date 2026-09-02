"""
③即時覆寫請求 Schema（對齊 api_contract 3.20）
用 Pydantic 驗證取代 raw dict：reason 必填、expire_minutes 有範圍限制。
"""

from typing import Optional
from pydantic import BaseModel, Field


class OverrideRequest(BaseModel):
    reason: str = Field(..., min_length=1, description="覆寫原因（必填，供稽核）")
    expire_minutes: Optional[int] = Field(
        default=None, ge=1, le=1440,
        description="時效分鐘數（1~1440，未給用 config 預設）",
    )
    operator: Optional[str] = Field(default=None, description="操作者（未給用驗證身分）")
