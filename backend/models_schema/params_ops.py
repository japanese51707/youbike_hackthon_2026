"""參數操作請求 Schema（A5 I-10）。"""

from pydantic import BaseModel, Field


class ParamsRollbackRequest(BaseModel):
    version: str = Field(..., min_length=1, description="要回溯到的版本號")
