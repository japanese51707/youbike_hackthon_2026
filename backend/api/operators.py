"""調度員 + 車隊端點（3.16, ADR-114/116/119）。接 operators_repo / vehicles_repo。"""

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/v1", tags=["operators"])


@router.get("/operators")
def list_operators(role_type: str | None = None, active_only: bool = True):
    """3.16 調度員清單（接 operators_repo）。可篩營運角色 role_type（driver/stationed/controller/depot_standby）。"""
    from db import operators_repo as repo
    if role_type:
        return repo.list_by_role_type(role_type, active_only=active_only)
    return repo.list_operators(active_only=active_only)


@router.get("/operators/{operator_id}")
def operator_detail(operator_id: str):
    """3.16 單一調度員"""
    from db import operators_repo as repo
    o = repo.get_operator(operator_id)
    if o is None:
        raise HTTPException(status_code=404, detail="查無此調度員")
    return o


@router.get("/vehicles")
def list_vehicles(status: str | None = None, active_only: bool = True):
    """ADR-114 車隊清單（接 vehicles_repo）。含 max_capacity/status/is_depot/current_district。"""
    from db import vehicles_repo as repo
    return repo.list_vehicles(status=status, active_only=active_only)


@router.get("/vehicles/standby")
def standby_vehicles():
    """ADR-118 待命車：預備車（保留率 standby）+ 總站待命車（is_depot），供緊急/支援調度。"""
    from db import vehicles_repo as repo
    return {"reserve_standby": repo.list_standby(), "depot_standby": repo.list_depot_standby()}


@router.get("/vehicles/{vehicle_id}")
def vehicle_detail(vehicle_id: str):
    """ADR-114 單一調度車"""
    from db import vehicles_repo as repo
    v = repo.get_vehicle(vehicle_id)
    if v is None:
        raise HTTPException(status_code=404, detail="查無此調度車")
    return v


@router.get("/operators/{operator_id}/stream")
def operator_stream(operator_id: str):
    """NFR-9 只推該調度員工作範圍內的即時更新（A0 骨架，之後改 SSE）"""
    return {"message": "mock：SSE 串流端點，A2/A3 實作", "operator_id": operator_id}
