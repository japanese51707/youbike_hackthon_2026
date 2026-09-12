"""戰情室顧問請求／回應（API 3.21，ADR-311）。"""

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator


class TwinMetric(BaseModel):
    label: str = Field(max_length=80)
    value: Any = None
    unit: Optional[str] = Field(default=None, max_length=20)


class TwinEvidence(BaseModel):
    label: Optional[str] = Field(default=None, max_length=120)
    detail: Optional[str] = Field(default=None, max_length=200)
    station_id: Optional[str] = Field(default=None, max_length=40)
    district: Optional[str] = Field(default=None, max_length=40)


class TwinLayerContext(BaseModel):
    key: str = Field(max_length=40)
    title: str = Field(max_length=80)
    data_mode: Optional[str] = Field(default=None, max_length=20)
    metrics: list[TwinMetric] = Field(default_factory=list, max_length=8)
    findings: list[str] = Field(default_factory=list, max_length=6)
    caveats: list[str] = Field(default_factory=list, max_length=6)
    evidence: list[TwinEvidence] = Field(default_factory=list, max_length=6)


class TwinStationHint(BaseModel):
    station_id: Optional[str] = Field(default=None, max_length=40)
    station_name: str = Field(max_length=80)
    district: Optional[str] = Field(default=None, max_length=40)
    status: Optional[str] = Field(default=None, max_length=20)
    available_bikes: Optional[int] = None


class TwinDistrictHint(BaseModel):
    district: str = Field(max_length=40)
    empty: int = 0
    count: int = 0
    empty_rate: float = 0


class TwinAnalysisNote(BaseModel):
    key: str = Field(max_length=40)
    name: str = Field(max_length=80)
    info: str = Field(max_length=600)


class TwinAssistantContext(BaseModel):
    mode: Literal["past", "live", "predict"] = "live"
    observed_at: Optional[str] = Field(default=None, max_length=64)
    n_stations: int = Field(default=0, ge=0, le=5000)
    stations_source: Optional[str] = Field(default=None, max_length=160)
    city_wide_ok: bool = False
    gate_reason: Optional[str] = Field(default=None, max_length=400)
    headline: Optional[str] = Field(default=None, max_length=600)
    active_layers: list[str] = Field(default_factory=list, max_length=12)
    layers: list[TwinLayerContext] = Field(default_factory=list, max_length=12)
    top_empty: list[TwinStationHint] = Field(default_factory=list, max_length=8)
    top_full: list[TwinStationHint] = Field(default_factory=list, max_length=8)
    top_districts: list[TwinDistrictHint] = Field(default_factory=list, max_length=8)
    analysis_notes: list[TwinAnalysisNote] = Field(default_factory=list, max_length=12)


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    text: str = Field(max_length=800)


class TwinAssistantRequest(BaseModel):
    question: Optional[str] = Field(default=None, max_length=500)
    context: TwinAssistantContext
    history: list[ChatTurn] = Field(default_factory=list, max_length=8)

    @field_validator("question")
    @classmethod
    def strip_question(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        text = value.strip()
        return text or None


class TwinAssistantResponse(BaseModel):
    text: str
    source: Literal["bedrock", "fallback"]
    model: Optional[str] = None
    advisory: bool = True
