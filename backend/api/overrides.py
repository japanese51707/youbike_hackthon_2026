"""③ 即時緊急覆寫端點（3.20，與②最適化分開）。需 dispatcher/主管。接 override_service。"""

from fastapi import APIRouter, Depends, HTTPException
from auth import require_role
from core.override_service import get_override_service
from models_schema.override import OverrideRequest

router = APIRouter(prefix="/api/v1", tags=["overrides"])


@router.post("/stations/{station_id}/emergency-override")
def apply_override(
    station_id: str,
    body: OverrideRequest,
    operator: dict = Depends(require_role("dispatcher", "maintainer")),
):
    """3.20 即時緊急覆寫（dispatcher 排序當最前綴，不改 urgency 分數）"""
    entry = get_override_service().apply(
        station_id=station_id,
        reason=body.reason,
        operator=body.operator or operator["operator_id"],
        expire_minutes=body.expire_minutes,
    )
    return {"message": f"站點 {station_id} 已設緊急覆寫", **entry}


@router.delete("/stations/{station_id}/emergency-override")
def cancel_override(
    station_id: str,
    operator: dict = Depends(require_role("dispatcher", "maintainer")),
):
    """3.20 取消覆寫"""
    ok = get_override_service().cancel(station_id, operator=operator["operator_id"])
    if not ok:
        raise HTTPException(status_code=404, detail=f"站點 {station_id} 無生效中的覆寫")
    return {"message": f"站點 {station_id} 覆寫已取消"}


@router.get("/overrides/active")
def active_overrides():
    """3.20 目前生效中的覆寫（已過期自動恢復）"""
    return get_override_service().active_overrides()
