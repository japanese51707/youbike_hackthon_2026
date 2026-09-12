from typing import Literal, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from core.rider_faults import add_report, list_summaries

router = APIRouter(prefix="/api/v1/rider", tags=["rider"])


class FaultReportIn(BaseModel):
    station_id: str = Field(min_length=1, max_length=40)
    station_name: Optional[str] = Field(default=None, max_length=80)
    issue: Literal["bike", "dock", "station", "other"]
    add_quantity: int = Field(default=1, ge=1, le=10)
    note: Optional[str] = Field(default=None, max_length=40)


@router.get("/fault-summaries")
def get_fault_summaries():
    return {"summaries": list_summaries()}


@router.post("/fault-reports")
def create_fault_report(body: FaultReportIn):
    result = add_report(
        station_id=body.station_id,
        issue=body.issue,
        add_quantity=body.add_quantity,
        station_name=body.station_name,
        note=body.note,
    )
    return {**result, "dispatches": False}
