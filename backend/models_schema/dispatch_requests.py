"""ADR-302：組单選項與確認請求；任務指令只能來自後端預覽。"""

from typing import Annotated
from pydantic import BaseModel, ConfigDict, Field

Identifier = Annotated[str, Field(strict=True, min_length=1)]


class DispatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class BuildVehicleRequest(DispatchRequest):
    vehicle_id: Identifier
    operator_id: Identifier
    district: Identifier | None = None


class BuildStationRequest(DispatchRequest):
    station_id: Identifier
    vehicle_id: Identifier | None = None
    operator_id: Identifier | None = None


class BuildEmergencyRequest(DispatchRequest):
    station_ids: list[Identifier] = Field(min_length=1)
    vehicle_id: Identifier | None = None
    operator_id: Identifier | None = None


class ConfirmReference(DispatchRequest):
    draft_id: Identifier
    version: int = Field(strict=True, ge=1)


class ConfirmDraft(DispatchRequest):
    draft: dict


class AddStationRequest(DispatchRequest):
    station_id: Identifier | None = None
    station: dict | None = None  # 相容舊封裝；除 station_id 外皆不用作指令
    reason: str = Field(default="", strict=True)
