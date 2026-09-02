"""② AI 每日最適化端點（3.12）。需 maintainer 權限。A0 回 mock。"""

from fastapi import APIRouter, Depends, Body
from auth import require_role

router = APIRouter(prefix="/api/v1", tags=["optimization"])


@router.get("/optimization/daily-review")
def daily_review():
    """3.12 取得每日最適化待確認摘要（逐站對比）"""
    return {
        "review_id": "REV-20260602",
        "review_date": "2026-06-02",
        "lookback_days": 3,
        "excluded_abnormal_days": ["2026-05-31"],
        "summary": {"total_stations_adjusted": 156, "avg_change_pct": 3.2, "significant_count": 8},
        "station_changes": [
            {"station_id": "500101001", "station_name": "捷運南勢角站", "is_significant": True,
             "params": [{"param": "outflow_rate", "old": 1.20, "new": 1.35, "change_pct": 12.5,
                         "reason": "近3日早高峰借車量持續高於預測"}]}
        ],
        "status": "pending_approval",
    }


@router.post("/optimization/daily-review/station/{station_id}")
def review_station(station_id: str, body: dict = Body(...),
                   operator: dict = Depends(require_role("maintainer"))):
    """3.12 逐站二次定義（accept/keep/re_adjust）"""
    return {"message": f"mock：站點 {station_id} 已記錄決定"}


@router.post("/optimization/daily-review/approve")
def approve(operator: dict = Depends(require_role("maintainer"))):
    """3.12 確認套用（approve 後才存版本）"""
    return {"message": "mock：已套用最適化並存版本"}


@router.post("/optimization/daily-review/reject")
def reject(operator: dict = Depends(require_role("maintainer"))):
    """3.12 退回（維持原參數，不留版本）"""
    return {"message": "mock：已退回，維持原參數"}


@router.put("/optimization/config")
def set_config(body: dict = Body(...), operator: dict = Depends(require_role("maintainer"))):
    """3.12 設定回看天數"""
    return {"message": "mock：已更新回看天數"}
