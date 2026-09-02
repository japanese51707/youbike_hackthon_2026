"""調度員端點（3.16）。A0 回 mock。"""

from fastapi import APIRouter, HTTPException
from mock_store import get_mock

router = APIRouter(prefix="/api/v1", tags=["operators"])


@router.get("/operators")
def list_operators():
    """3.16 所有調度員清單 + 狀態 + 今日統計"""
    return get_mock()["operators"]


@router.get("/operators/{operator_id}")
def operator_detail(operator_id: str):
    """3.16 單一調度員（含任務佇列）"""
    ops = get_mock()["operators"]
    for o in ops:
        if o["operator_id"] == operator_id:
            return o
    raise HTTPException(status_code=404, detail="查無此調度員")


@router.get("/operators/{operator_id}/stream")
def operator_stream(operator_id: str):
    """NFR-9 只推該調度員工作範圍內的即時更新（A0 骨架，之後改 SSE）"""
    return {"message": "mock：SSE 串流端點，A2/A3 實作", "operator_id": operator_id}
