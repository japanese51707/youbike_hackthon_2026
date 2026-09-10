"""
② AI 每日最適化端點（3.12，ADR-120 做法 Y）
=============================================
optimizer 算偏差、產生調整係數建議（做法 Y：建議層真實，生效接線待補）。
approve → 寫 ai_optimized 版本（commit_optimized，可回溯）；reject → 不留版本。
"""

from fastapi import APIRouter, Depends, Body
from auth import require_role

router = APIRouter(prefix="/api/v1", tags=["optimization"])

# 簡易記憶體暫存（存最近一次 daily-review，供 approve/reject 用）
_pending_review: dict | None = None


@router.get("/optimization/daily-review")
def daily_review(review_date: str | None = None, lookback_days: int | None = None):
    """3.12 取得每日最適化待確認摘要（ADR-120 optimizer 真實分析）。

    分情境算偏差 → 調整係數建議 → 待核准清單。
    做法 Y：建議層真實、生效接線待補（見 effective_note）。
    """
    global _pending_review
    from optimization.param_optimizer import compute_daily_review
    _pending_review = compute_daily_review(review_date, lookback_days)
    return _pending_review


@router.post("/optimization/daily-review/station/{station_id}")
def review_station(station_id: str, body: dict = Body(...),
                   operator: dict = Depends(require_role("maintainer"))):
    """3.12 逐站二次定義（accept/keep/re_adjust）。修改暫存中的 station_changes。"""
    global _pending_review
    if not _pending_review:
        return {"message": "請先呼叫 GET /optimization/daily-review"}
    decision = body.get("decision", "accept")
    for ch in _pending_review.get("station_changes", []):
        if ch["station_id"] == station_id:
            ch["_decision"] = decision
            if decision == "re_adjust" and body.get("params"):
                ch["params"] = body["params"]
    return {"message": f"站點 {station_id} 記錄決定 {decision}"}


@router.post("/optimization/daily-review/approve")
def approve(operator: dict = Depends(require_role("maintainer"))):
    """3.12 確認套用（approve 後才存版本，ADR-120 人在迴圈閘門）。

    對 station_changes 中 decision!=keep 的站呼叫 commit_optimized 存 ai_optimized 版本。
    ★做法 Y：版本存了、閉環完整；調整係數生效接線待補（ADR-120 尚未解決項）。
    """
    global _pending_review
    if not _pending_review:
        return {"message": "無待確認的最適化建議"}
    from params import commit_optimized
    changes = _pending_review.get("station_changes", [])
    committed = []
    for ch in changes:
        if ch.get("_decision", "accept") == "keep":
            continue
        sid = ch["station_id"]
        # 把建議係數組成 params dict
        params = {p["param"]: p["new"] for p in ch.get("params", [])}
        if not params:
            continue
        try:
            reason = "；".join(p["reason"] for p in ch.get("params", []))
            commit_optimized(
                station_id=sid, params=params,
                reason=reason, operator=operator["operator_id"],
            )
            committed.append(sid)
        except Exception as e:
            committed.append(f"{sid}(失敗:{type(e).__name__})")
    _pending_review["status"] = "approved"
    return {
        "message": f"已套用最適化（{len(committed)} 站）並存版本",
        "committed_stations": committed,
        "effective_note": "做法Y:版本已存;調整係數生效接線待補(ADR-120)",
    }


@router.post("/optimization/daily-review/reject")
def reject(operator: dict = Depends(require_role("maintainer"))):
    """3.12 退回（維持原參數，不留版本）。"""
    global _pending_review
    _pending_review = None
    return {"message": "已退回，維持原參數，未存版本"}


@router.put("/optimization/config")
def set_config(body: dict = Body(...),
               operator: dict = Depends(require_role("maintainer"))):
    """3.12 設定回看天數（寫 config.yaml — 目前回顯示，正式環境改寫 config）。"""
    cfg = body.get("lookback_days")
    if cfg:
        return {"message": f"回看天數設為 {cfg}（目前顯示，正式環境需寫回 config）"}
    return {"message": "未提供 lookback_days"}
