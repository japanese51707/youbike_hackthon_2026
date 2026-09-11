"""ADR-302：外勤回報使用嚴格數量，不接受小數、字串或布林。"""

from pydantic import BaseModel, ConfigDict, Field


class StationReportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    station_id: str = Field(min_length=1, strict=True)
    actual_available: int = Field(ge=0, strict=True)


class TaskReturnRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    reason: str = Field(min_length=1, strict=True)
