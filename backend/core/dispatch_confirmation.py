"""ADR-302：驗證後端草稿並原子確認；收據保證重送不重派。"""

from datetime import datetime, timezone

from db.connection import atomic
from db import confirmations_repo, tasks_repo
from core import dispatch_drafts
from core.dispatch_errors import DispatchConflict, DispatchForbidden
from core.dispatch_guards import require_dispatcher


def _result(receipt):
    task = tasks_repo.get(receipt["task_id"])
    return {"trip_id": task["task_id"], "confirmed": True, "status": task["task_status"]}


def confirm(submitted, operator, skip_observation_recheck=False):
    # Network reads stay outside the SQLite write transaction. The atomic section
    # rechecks the proof's age and the draft, plus resource ownership.
    #
    # ADR-333：skip_observation_recheck 供「系統自動配單」用。人工組單會開著預覽一段時間才
    # 按確認，期間站況可能變，故確認時比對「組單當下 vs 即時」站況、不符就擋（防用過期預覽派工）。
    # 但自動配單是機器用當下清單即時組單+立刻確認，組單清單走 60 秒快取、即時站況來自 S3 中繼，
    # 兩者 observed_at 幾乎必然不同 → 觀測比對會把幾乎每張自動單都擋掉（實測 193 站 136 站被擋）。
    # 自動配單本就用最新清單決策，不需要「防人用舊預覽」那層保護；資源驗證/載量守恆/認領檢查
    # （validate_resources 等）仍全數保留，才是防重複配的真防線。
    require_dispatcher(operator)
    if (not isinstance(submitted, dict) or not isinstance(submitted.get("draft_id"), str)
            or type(submitted.get("version")) is not int or submitted["version"] < 1):
        raise ValueError("需有效的 draft_id 與 version")
    receipt = confirmations_repo.get(submitted["draft_id"])
    snapshots = None
    if not receipt and isinstance(submitted, dict):
        from config_loader import get_config
        mode = get_config().get("data_source", {}).get("mode", "mock")
        draft = dispatch_drafts.get(submitted.get("draft_id"), submitted.get("version"))
        if draft.get("data_mode", "mock") != mode:
            raise DispatchConflict("資料模式已改變，請重新預覽")
        if mode != "mock" and not skip_observation_recheck:
            from core.data import get_stations_with_degradation
            snapshots = {s["station_id"]: s for s in get_stations_with_degradation()}
    return _confirm(submitted, operator, snapshots)


@atomic
def _confirm(submitted, operator, snapshots):
    require_dispatcher(operator)
    if not isinstance(submitted, dict):
        raise ValueError("需草稿 ID 與版本")
    draft_id, version = submitted.get("draft_id"), submitted.get("version")
    if not isinstance(draft_id, str) or type(version) is not int or version < 1:
        raise ValueError("需有效的 draft_id 與 version")
    full_draft = set(submitted) != {"draft_id", "version"}
    receipt = confirmations_repo.get(draft_id)
    if receipt:
        if receipt["confirmed_by"] != operator:
            raise DispatchForbidden("這張草稿已由其他人確認")
        if receipt["version"] != version or (
            full_draft and receipt["fingerprint"] != dispatch_drafts.fingerprint(submitted)
        ):
            raise DispatchConflict("已確認草稿不可修改")
        return _result(receipt)

    draft = dispatch_drafts.get(draft_id, version)
    if draft.get("created_by") not in (None, operator):
        raise DispatchForbidden("只能確認自己建立的草稿")
    digest = dispatch_drafts.fingerprint(draft)
    if full_draft and dispatch_drafts.fingerprint(submitted) != digest:
        raise DispatchConflict("草稿內容已變更，請重新組單預覽")
    if snapshots is not None:
        from core.data.observations import normalize
        from config_loader import get_config
        ds = get_config().get("data_source", {})
        for stop in draft["stations"]:
            current = snapshots.get(stop["station_id"])
            if current:
                current = normalize(current, ds["mode"], ds.get("stale_after_sec", 600))
            if not current or not current["dispatch_eligible"]:
                raise DispatchConflict("站點資料已過期、停用或不可用，請重新預覽")
            if (current["available_bikes"] != stop.get("current_available")
                    or current["total_docks"] != stop.get("total_docks")
                    or current["observed_at"] != stop.get("observed_at")):
                raise DispatchConflict("站點觀測已更新，請重新預覽")
    from core.dispatcher import _persist_trip
    from db import tasks_repo
    # ADR-330：改用人類可讀編號（20260911-早001）。冪等由上方收據保證——同一 draft 重送
    # 會先命中 receipt 直接回傳，不會再進到這裡產生第二個編號。編號在寫入交易內原子遞增。
    assigned_at = datetime.now(timezone.utc).isoformat()
    trip = {**draft, "trip_id": tasks_repo.next_task_id(draft.get("shift")), "assigned_at": assigned_at}
    _persist_trip(trip)
    receipt = {"draft_id": draft_id, "version": version, "fingerprint": digest,
               "task_id": trip["trip_id"], "confirmed_by": operator,
               "confirmed_at": assigned_at}
    confirmations_repo.insert(receipt)
    from core.audit import get_audit_service
    get_audit_service().record(
        type="task_report", operator=operator,
        action=f"確認派工單 {trip['trip_id']}（{trip.get('mode')}，{len(trip['stations'])} 站）",
        reason=draft.get("note"))
    return _result(receipt)
