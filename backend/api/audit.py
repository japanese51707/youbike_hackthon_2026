"""稽核記錄端點（3.14）。接 audit_service（覆寫/轉派/最適化等留痕）。"""

from fastapi import APIRouter
from core.audit import get_audit_service

router = APIRouter(prefix="/api/v1", tags=["audit"])


@router.get("/audit/logs")
def audit_logs(type: str | None = None, station_id: str | None = None,
               operator: str | None = None):
    """3.14 稽核記錄（誰、何時、做了什麼）"""
    return get_audit_service().query(type=type, station_id=station_id, operator=operator)
