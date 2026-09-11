"""
② AI 每日最適化端點（3.12，ADR-120 做法 Y + ADR-304 套用一致性）
=================================================================
optimizer 算偏差、產生調整係數建議（做法 Y：建議層真實，生效接線待補）。
approve → 寫 ai_optimized 版本（commit_optimized_batch，全成或全退，可回溯）；reject → 不留版本。

ADR-304：
  - daily-review 回 status ∈ {ok, no_data, insufficient_samples, failed} + reason + diagnostics。
  - approve 必須帶 review_id：缺少 422、不符或過期 409、同一 review_id 重送回原結果（冪等）。
  - 一次 approve 內所有站在單一交易提交，任一站失敗全部回滾，不回傳「部分成功」。
  - 調整係數「仍未」被 rule_engine／dispatcher／prediction 讀取，effective_note 為誠實標記。
"""

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from auth import require_role

router = APIRouter(prefix="/api/v1", tags=["optimization"])

# 有界的記憶體暫存：review_id → review。單程序限制同 ADR-302 草稿（多實例需另行設計）。
_REVIEWS: dict[str, dict] = {}
_MAX_REVIEWS = 8


class ReviewRef(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    review_id: str = Field(min_length=1, strict=True)


class StationDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    decision: str = "accept"
    params: list | None = None
    review_id: str | None = None


def _remember(review: dict) -> dict:
    _REVIEWS[review["review_id"]] = review
    while len(_REVIEWS) > _MAX_REVIEWS:
        _REVIEWS.pop(next(iter(_REVIEWS)))
    return review


def _load(review_id: str) -> dict:
    review = _REVIEWS.get(review_id)
    if review is None:
        raise HTTPException(status_code=409,
                            detail="review_id 不存在或已過期，請重新取得 daily-review")
    return review


def _latest() -> dict | None:
    return next(reversed(_REVIEWS.values()), None) if _REVIEWS else None


def reset_reviews() -> None:
    """測試用：清空暫存。"""
    _REVIEWS.clear()


@router.get("/optimization/daily-review")
def daily_review(review_date: str | None = None, lookback_days: int | None = None):
    """3.12 取得每日最適化待確認摘要（ADR-120 optimizer 真實分析）。

    分情境算偏差 → 調整係數建議 → 待核准清單。status 明確區分
    ok / no_data / insufficient_samples / failed（ADR-304）。
    """
    from optimization.param_optimizer import compute_daily_review
    from params import current_mode
    review = compute_daily_review(review_date, lookback_days)
    # ADR-124/304：讓前端能誠實顯示「核准後到底會不會影響調度」，不靠前端自己猜
    review["coefficient_mode"] = current_mode()
    return _remember(review)


@router.post("/optimization/daily-review/station/{station_id}")
def review_station(station_id: str, body: StationDecision = Body(...),
                   operator: dict = Depends(require_role("maintainer"))):
    """3.12 逐站二次定義（accept/keep/re_adjust）。修改暫存中的 station_changes。

    review_id 選填：有帶就綁定該份建議，沒帶則沿用最近一次（相容既有呼叫端）。
    """
    review = _load(body.review_id) if body.review_id else _latest()
    if not review:
        raise HTTPException(status_code=409, detail="請先呼叫 GET /optimization/daily-review")
    if review.get("approval_state") in {"approved", "rejected"}:
        raise HTTPException(status_code=409, detail="這份建議已結案，請重新取得 daily-review")
    if body.decision not in {"accept", "keep", "re_adjust"}:
        raise HTTPException(status_code=422, detail="decision 必須是 accept/keep/re_adjust")
    for ch in review.get("station_changes", []):
        if ch["station_id"] == station_id:
            ch["_decision"] = body.decision
            if body.decision == "re_adjust" and body.params:
                ch["params"] = body.params
            return {"message": f"站點 {station_id} 記錄決定 {body.decision}",
                    "review_id": review["review_id"]}
    raise HTTPException(status_code=404, detail=f"建議清單中沒有站點 {station_id}")


@router.post("/optimization/daily-review/approve")
def approve(body: ReviewRef, operator: dict = Depends(require_role("maintainer"))):
    """3.12 確認套用（approve 後才存版本，ADR-120 人在迴圈閘門）。

    ADR-304：需帶 review_id；全成或全退；同一 review_id 重送回原結果（冪等）。
    ★做法 Y：版本存了、閉環完整；調整係數生效接線待補（ADR-120 尚未解決項）。
    """
    review = _load(body.review_id)
    if review.get("approval_state") == "approved":
        return review["_approve_result"]          # 冪等：重送回原結果，不重複寫版本
    if review.get("approval_state") == "rejected":
        raise HTTPException(status_code=409, detail="這份建議已退回，請重新取得 daily-review")
    if review.get("status") != "ok":
        raise HTTPException(
            status_code=409,
            detail=f"建議狀態為 {review.get('status')}，不可套用：{review.get('reason')}")

    items = []
    for ch in review.get("station_changes", []):
        if ch.get("_decision", "accept") == "keep":
            continue
        params = {p["param"]: p["new"] for p in ch.get("params", [])}
        if not params:
            continue
        items.append({"station_id": ch["station_id"], "params": params,
                      "reason": "；".join(p["reason"] for p in ch.get("params", []))})
    if not items:
        raise HTTPException(status_code=409, detail="沒有可套用的站點（全部 keep 或無參數）")

    from params import commit_optimized_batch
    try:
        commit_optimized_batch(items, operator["operator_id"])
    except ValueError as exc:                      # 例如缺調整原因
        raise HTTPException(status_code=422, detail=f"套用失敗，已整批回滾：{exc}") from exc
    except Exception as exc:
        raise HTTPException(status_code=409, detail=f"套用失敗，已整批回滾：{exc}") from exc

    result = {
        "message": f"已套用最適化（{len(items)} 站）並存版本",
        "review_id": review["review_id"],
        "committed_stations": [i["station_id"] for i in items],
        "effective_note": ("做法Y:版本已存;調整係數尚未被 rule_engine/dispatcher/prediction "
                           "讀取(ADR-120 未解決項)"),
    }
    review["approval_state"] = "approved"
    review["_approve_result"] = result
    return result


@router.post("/optimization/daily-review/reject")
def reject(body: ReviewRef | None = Body(default=None),
           operator: dict = Depends(require_role("maintainer"))):
    """3.12 退回（維持原參數，不留版本）。帶 review_id 則只退回該份。"""
    if body is not None:
        review = _load(body.review_id)
        if review.get("approval_state") == "approved":
            raise HTTPException(status_code=409, detail="這份建議已套用，請改用參數回溯")
        review["approval_state"] = "rejected"
        return {"message": "已退回，維持原參數，未存版本", "review_id": review["review_id"]}
    _REVIEWS.clear()
    return {"message": "已退回，維持原參數，未存版本"}


@router.put("/optimization/config")
def set_config(body: dict = Body(...),
               operator: dict = Depends(require_role("maintainer"))):
    """3.12 設定回看天數（寫 config.yaml — 目前回顯示，正式環境改寫 config）。"""
    cfg = body.get("lookback_days")
    if cfg:
        return {"message": f"回看天數設為 {cfg}（目前顯示，正式環境需寫回 config）"}
    return {"message": "未提供 lookback_days"}
