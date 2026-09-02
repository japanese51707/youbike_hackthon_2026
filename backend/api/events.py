"""活動事件端點（3.15）。POST 會呼叫 event_impact 算影響（A0 回 mock）。"""

from fastapi import APIRouter, Body
from mock_store import get_mock

router = APIRouter(prefix="/api/v1", tags=["events"])


@router.get("/events")
def list_events():
    """3.15 生效中的活動"""
    return get_mock()["events"]


@router.post("/events")
def create_event(body: dict = Body(...)):
    """3.15 新增活動（後端呼叫 prediction/event_impact 算影響半徑+供需比）— A0 回 mock"""
    return get_mock()["events"][0]


@router.delete("/events/{event_id}")
def delete_event(event_id: str):
    """3.15 移除活動"""
    return {"message": f"mock：活動 {event_id} 已移除"}
