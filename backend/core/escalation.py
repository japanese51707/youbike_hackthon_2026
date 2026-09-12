"""
緊急調度案件的升級追蹤（core.escalation）— ADR-309
====================================================
警示只負責「現在有事」，案件負責「這件事已經沒人管多久了」。

為什麼不能把計時器加在警示上（ADR-309 背景）：
  警示每次查詢即時重算，站況恢復或訊息過時就整筆刪除重建，alert_id 會換、
  triggered_at 會歸零；而且去重只看未讀警示，按一次「已讀」時鐘就重算。

本模組的規則全部是確定性的——階段由 (now − opened_at) 與設定值比較得出，
關案由「有未結案任務涵蓋該站」或「站況已恢復」判定。沒有任何一步經過模型。

職責：
  1. sync_cases：依即時站況與任務開案／關案
  2. stage_of / describe：算階段、等待分鐘、下一階段時間
  3. record_action：寫稽核軌跡（已讀靜音／已電話聯絡／延後）
不做：警示產生本身（alert_service）、派工（dispatch_builder）。
"""

from __future__ import annotations

import datetime as _dt
import json
import uuid
from typing import Iterable, Optional

CLOSE_DISPATCHED = "dispatched"
CLOSE_RECOVERED = "recovered"

ACTION_ACK = "acknowledged"
ACTION_CALLED = "called"
ACTION_DEFERRED = "deferred"
ACTION_DISPATCH = "dispatch"
VALID_ACTIONS = (ACTION_ACK, ACTION_CALLED, ACTION_DEFERRED, ACTION_DISPATCH)

# 任務還在路上、還算「已處理」的狀態；completed/cancelled 不算。
OPEN_TASK_STATUS = ("pending", "assigned", "in_progress", "retryable", "manual_required")

# 階段預設值；設定不合法時整組退回這個
DEFAULT_STAGES = (30, 45)


def _now() -> _dt.datetime:
    return _dt.datetime.now()


def _iso(moment: _dt.datetime) -> str:
    return moment.isoformat(timespec="seconds")


def _parse(value) -> Optional[_dt.datetime]:
    if not value:
        return None
    try:
        return _dt.datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _settings(config: Optional[dict] = None) -> dict:
    if config is None:
        from config_loader import get_config
        config = get_config()
    cfg = (config or {}).get("escalation", {}) or {}
    stages = cfg.get("階段") or DEFAULT_STAGES
    # 階段必須是遞增的正整數，否則「下一階段」會算出往回走的時間。
    # ★設定只要有一項不合法就整組退回預設，不保留「合法的前半段」——
    #   typo 悄悄吃掉第二階段（電話聯絡）比整組退回預設危險得多。
    clean = []
    valid = True
    for value in stages:
        try:
            minutes = int(value)
        except (TypeError, ValueError):
            valid = False
            break
        if minutes <= 0 or (clean and minutes <= clean[-1]):
            valid = False
            break
        clean.append(minutes)
    return {
        "stages": clean if (valid and clean) else list(DEFAULT_STAGES),
        "mute_minutes": int(cfg.get("靜音分鐘", 10) or 10),
        "contacts": cfg.get("值班聯絡", {}) or {},
    }


def needs_case(station: dict, recommendation: Optional[dict]) -> bool:
    """哪些站要開案：現況已空／已滿，或建議為最高緊急（ADR-111 截斷層／high）。

    門檻刻意比警示嚴格——警示有 info/warning/critical 三級，案件只追最緊急那一層，
    否則管理後台會被一整面的黃色案件淹沒，真正該打電話的那幾站反而被稀釋。
    """
    if station.get("status") in ("empty", "full"):
        return True
    if not recommendation:
        return False
    return (recommendation.get("urgency_tier") == "censored"
            or recommendation.get("priority_level") == "high")


def stations_with_open_task(tasks: Iterable[dict]) -> set:
    """從未結案任務的路線取出涵蓋的站，這些站算「已處理」。"""
    covered = set()
    for task in tasks or []:
        if task.get("task_status") not in OPEN_TASK_STATUS:
            continue
        route = task.get("route") or task.get("route_json") or []
        if isinstance(route, str):
            try:
                route = json.loads(route)
            except (TypeError, ValueError):
                route = []
        for stop in route or []:
            if isinstance(stop, dict) and stop.get("station_id"):
                covered.add(stop["station_id"])
    return covered


def stage_of(case: dict, now: Optional[_dt.datetime] = None,
             config: Optional[dict] = None) -> int:
    """等待時間跨過第幾個門檻。0 = 尚未到第一個提示。"""
    opened = _parse(case.get("opened_at"))
    if opened is None:
        return 0
    stages = _settings(config)["stages"]
    waited = ((now or _now()) - opened).total_seconds() / 60.0
    reached = 0
    for index, minutes in enumerate(stages, start=1):
        if waited >= minutes:
            reached = index
    return reached


def describe(case: dict, now: Optional[_dt.datetime] = None,
             config: Optional[dict] = None) -> dict:
    """把案件補上前端要的推算欄位。時間一律後端算，前端不自己累加。"""
    settings = _settings(config)
    moment = now or _now()
    opened = _parse(case.get("opened_at"))
    waited = max(0.0, (moment - opened).total_seconds() / 60.0) if opened else 0.0
    stage = stage_of(case, moment, config)
    stages = settings["stages"]
    next_at = None
    if opened is not None and stage < len(stages):
        next_at = _iso(opened + _dt.timedelta(minutes=stages[stage]))
    muted_until = _parse(case.get("muted_until"))
    muted = bool(muted_until and muted_until > moment)
    district = case.get("district") or ""
    return {
        **case,
        "stage": stage,
        "stage_label": ("開案", "需再提示", "需電話聯絡")[min(stage, 2)],
        "waited_minutes": round(waited, 1),
        "next_stage_at": next_at,
        "next_stage_in_minutes": (
            round((_parse(next_at) - moment).total_seconds() / 60.0, 1) if next_at else None),
        "muted": muted,
        "muted_until": case.get("muted_until"),
        # 靜音中不打擾；但時鐘照走，靜音到期就回到當時應在的階段。
        "should_banner": stage >= 1 and not muted,
        "should_prompt": stage >= 2 and not muted,
        "contact": settings["contacts"].get(district) or settings["contacts"].get("預設"),
        "stage_thresholds": stages,
    }


def sync_cases(stations: list, recommendations: Optional[list] = None,
               tasks: Optional[list] = None, config: Optional[dict] = None,
               now: Optional[_dt.datetime] = None) -> list:
    """依即時站況與任務開案／關案，回傳所有未結案案件（已補推算欄位）。

    關案只有兩種確定性理由（ADR-309 §2）：
      dispatched —— 有未結案任務涵蓋該站
      recovered  —— 該站本輪不再需要緊急警示
    人按「已讀」不關案，只靜音。
    """
    from db import escalation_repo

    moment = now or _now()
    rec_by_id = {r.get("station_id"): r for r in (recommendations or [])}
    need = {}
    for station in stations or []:
        station_id = station.get("station_id")
        if not station_id:
            continue
        if needs_case(station, rec_by_id.get(station_id)):
            need[station_id] = station

    covered = stations_with_open_task(tasks or [])
    open_cases = {c["station_id"]: c for c in escalation_repo.list_open_cases()}

    # 1. 關案：已派工優先（那是真的有人在處理），其次站況恢復。
    for station_id, case in open_cases.items():
        if station_id in covered:
            escalation_repo.close_case(case["case_id"], CLOSE_DISPATCHED, _iso(moment))
        elif station_id not in need:
            escalation_repo.close_case(case["case_id"], CLOSE_RECOVERED, _iso(moment))

    # 2. 開案：需要緊急調度、沒有未結案案件、且尚未被任務涵蓋。
    for station_id, station in need.items():
        if station_id in open_cases or station_id in covered:
            continue
        rec = rec_by_id.get(station_id)
        escalation_repo.open_case({
            "case_id": f"CASE-{_iso(moment).replace(':', '').replace('-', '')}-{uuid.uuid4().hex[:6]}",
            "station_id": station_id,
            "station_name": station.get("station_name", ""),
            "district": station.get("district", ""),
            "opened_at": _iso(moment),
            "trigger_reason": (rec or {}).get("reason") or _default_reason(station),
            "suggested_action": (f"{rec['action']} {rec['quantity']} 台" if rec else None),
        })

    # 3. 記錄曾達到的最高階段（供稽核與「已提示過」判斷）。
    result = []
    for case in escalation_repo.list_open_cases():
        described = describe(case, moment, config)
        if described["stage"] > int(case.get("highest_stage") or 0):
            escalation_repo.set_highest_stage(case["case_id"], described["stage"])
            described["highest_stage"] = described["stage"]
        result.append(described)
    result.sort(key=lambda c: (-c["stage"], -c["waited_minutes"]))
    return result


def _default_reason(station: dict) -> str:
    status = station.get("status")
    if status == "empty":
        return "已空站（無車可借）"
    if status == "full":
        return "已滿站（無位可還）"
    return "緊急度達最高層級"


def record_action(case_id: str, action: str, actor: str,
                  note: str = "", contact: str = "",
                  config: Optional[dict] = None,
                  now: Optional[_dt.datetime] = None) -> dict:
    """寫稽核軌跡。已讀與已電話聯絡會靜音一段時間，但都不關案（ADR-309 §2）。"""
    from db import escalation_repo

    if action not in VALID_ACTIONS:
        raise ValueError(f"不支援的動作 {action}")
    case = escalation_repo.get_case(case_id)
    if case is None:
        raise LookupError(f"找不到案件 {case_id}")
    if case.get("closed_at"):
        raise ValueError("案件已關閉，不可再記錄動作")
    if action == ACTION_DEFERRED and not note.strip():
        raise ValueError("延後處理必須填寫原因")
    if action == ACTION_CALLED and not contact.strip():
        raise ValueError("電話聯絡必須記錄聯絡對象")

    moment = now or _now()
    escalation_repo.insert_action({
        "action_id": f"ACT-{uuid.uuid4().hex[:10]}",
        "case_id": case_id,
        "action": action,
        "actor": actor or "unknown",
        "stage": stage_of(case, moment, config),
        "note": note.strip(),
        "contact": contact.strip(),
        "created_at": _iso(moment),
    })
    if action in (ACTION_ACK, ACTION_CALLED, ACTION_DEFERRED):
        mute = _settings(config)["mute_minutes"]
        escalation_repo.mute_case(case_id, _iso(moment + _dt.timedelta(minutes=mute)))
    return describe(escalation_repo.get_case(case_id), moment, config)
