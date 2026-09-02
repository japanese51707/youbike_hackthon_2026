"""
帳號管理請求 Schema（A5）
用 Pydantic 驗證取代 raw dict：建立帳號、登入。
"""

from typing import Optional
from pydantic import BaseModel, Field


class CreateAccountRequest(BaseModel):
    operator_id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    role: str = Field(..., description="operator / dispatcher / maintainer")
    password: str = Field(..., min_length=6, description="至少 6 字元")


class LoginRequest(BaseModel):
    operator_id: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)
