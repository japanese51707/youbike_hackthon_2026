"""警示端點（3.11）。★題目要求：現行系統無警示。接 alert_service。"""

from fastapi import APIRouter, Body, HTTPException
from core.alert_service import get_alert_service
from core.data import get_stations_with_degradation
from core import build_dispatch_list

router = APIRouter(prefix="/api/v1", tags=["alerts"])


@router.get("/alerts")
def list_alerts(level: str | None = None, acknowledged: bool | None = None):
    """3.11 取得警示

    即時掃描站點 + 調度建議產生警示（分級 info/warning/critical），再依條件篩選。
    """
    svc = get_alert_service()
    stations = get_stations_with_degradation()
    recs = build_dispatch_list(stations)
    svc.generate_from_stations(stations, recs)
    return svc.list_alerts(level=level, acknowledged=acknowledged)


@router.post("/alerts/{alert_id}/acknowledge")
def acknowledge(alert_id: str):
    """3.11 確認警示已讀"""
    a = get_alert_service().acknowledge(alert_id)
    if a is None:
        raise HTTPException(status_code=404, detail=f"找不到警示 {alert_id}")
    return {"message": f"警示 {alert_id} 已標記為已讀", "alert": a}


@router.post("/alerts/subscribe")
def subscribe(body: dict = Body(...)):
    """3.11 機關訂閱警示 webhook（出向資安：callback 須 https 且非內網）"""
    try:
        sub = get_alert_service().subscribe(
            callback_url=body["callback_url"],
            levels=body.get("levels", ["warning", "critical"]),
            districts=body.get("districts", []),
            token=body.get("token"),
        )
    except (KeyError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"message": "已登記 webhook 訂閱", **sub}


@router.get("/alerts/stream")
def alert_stream():
    """3.11 前端即時警示串流（骨架：回傳待推佇列。正式改 SSE EventSource）"""
    return {"events": get_alert_service().drain_sse()}
