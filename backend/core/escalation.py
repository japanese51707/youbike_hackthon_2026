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

CLOSE_DISPATCHED = "dispatched"   # ADR-335 起不再使用；保留供歷史資料讀取
CLOSE_RECOVERED = "recovered"

# ADR-335 觀測狀態：案件此刻是被什麼樣的資料支撐著
OBS_CONFIRMED = "confirmed"     # 新鮮可信觀測，確認仍緊急
OBS_UNVERIFIED = "unverified"   # 過期／離線／缺站／規則結果不可用 → 保留時計，不得當恢復


def observation_trustworthy(station: Optional[dict], config: Optional[dict] = None) -> bool:
    """這筆站況能不能拿來「確認緊急已解除」。

    ★這條路徑會關掉案件，所以標準要嚴：正式資料必須明確標示 data_freshness == 'live'，
      欄位缺漏一律視為不可信。缺漏可能來自任何一個上游忘了帶欄位，把它當可信
      就會安靜地關掉不該關的案——而關錯的代價是沒人去處理那一站。
      只有 mock 資料源（測試 fixture 沒有這些欄位）才放行缺漏。
    """
    if not station:
        return False
    if station.get("service_available") is False or station.get("status") == "offline":
        return False
    freshness = station.get("data_freshness")
    if freshness == "live":
        return True
    if freshness is None:
        if config is None:
            from config_loader import get_config
            config = get_config()
        mode = ((config or {}).get("data_source", {}) or {}).get("mode", "mock")
        return mode == "mock"
    return False

ACTION_ACK = "acknowledged"
ACTION_CALLED = "called"
ACTION_DEFERRED = "deferred"
ACTION_DISPATCH = "dispatch"
VALID_ACTIONS = (ACTION_ACK, ACTION_CALLED, ACTION_DEFERRED, ACTION_DISPATCH)

# 任務還在路上、還算「已處理」的狀態；completed/cancelled 不算。
OPEN_TASK_STATUS = ("pending", "assigned", "in_progress", "retryable", "manual_required")

# 階段預設值；設定不合法時整組退回這個
DEFAULT_STAGES = (30, 45)


TAIPEI = _dt.timezone(_dt.timedelta(hours=8))


def _now() -> _dt.datetime:
    return _dt.datetime.now(TAIPEI)


def _to_taipei(moment: _dt.datetime) -> _dt.datetime:
    """案件時計一律台北。naive 當台北牆上時間，不跟容器 UTC 對打。"""
    if moment.tzinfo is None:
        return moment.replace(tzinfo=TAIPEI)
    return moment.astimezone(TAIPEI)


def _iso(moment: _dt.datetime) -> str:
    return _to_taipei(moment).isoformat(timespec="seconds")


def _parse(value) -> Optional[_dt.datetime]:
    if not value:
        return None
    try:
        return _to_taipei(_dt.datetime.fromisoformat(str(value)))
    except (TypeError, ValueError):
        return None


def _align(left: _dt.datetime, right: _dt.datetime) -> tuple[_dt.datetime, _dt.datetime]:
    return _to_taipei(left), _to_taipei(right)


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
    opened, moment = _align(opened, now or _now())
    waited = (moment - opened).total_seconds() / 60.0
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
    if opened is not None:
        opened, moment = _align(opened, moment)
        waited = max(0.0, (moment - opened).total_seconds() / 60.0)
    else:
        waited = 0.0
    stage = stage_of(case, moment, config)
    stages = settings["stages"]
    next_at = None
    if opened is not None and stage < len(stages):
        next_at = _iso(opened + _dt.timedelta(minutes=stages[stage]))
    muted_until = _parse(case.get("muted_until"))
    if muted_until is not None:
        muted_until, muted_now = _align(muted_until, moment)
        muted = muted_until > muted_now
    else:
        muted = False
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
    """依即時站況開案／關案，回傳所有未結案案件（已補推算欄位）。

    ADR-335 改寫了關案規則。舊規則（ADR-309）是「有未結案任務涵蓋該站就關案」，
    但派工只代表**有人承辦**，不代表**問題解除**——司機還沒到、到了發現車不夠、
    或補完又被借光，站點其實一直是空的。舊規則等於一派工就停止催辦，
    這正是「派完就沒人再管」的根因。

    現在只有一種關案理由：**新鮮且可信的觀測，配合有效規則結果，確認不再緊急**。
      - 派工、轉派、已讀、任務回報完成、跨日、換班：一律不關案，時計不重設。
      - 缺站、空回應、過期、離線、規則結果不可用：保留案件並標 unverified，
        絕不當成恢復。資料不知道不等於問題解決了。
      - 亂序：比 last_confirmed_at 舊的觀測不得反轉狀態。
    """
    from db import escalation_repo

    moment = now or _now()
    rec_by_id = {r.get("station_id"): r for r in (recommendations or [])}
    station_by_id = {s.get("station_id"): s for s in (stations or []) if s.get("station_id")}

    need = {}
    for station_id, station in station_by_id.items():
        if needs_case(station, rec_by_id.get(station_id)):
            need[station_id] = station

    open_cases = {c["station_id"]: c for c in escalation_repo.list_open_cases()}

    # ── 1. 逐案判斷：只有「確認解除」才關 ────────────────────────────
    for station_id, case in open_cases.items():
        station = station_by_id.get(station_id)
        observed_at = _observed_at(station)

        # 亂序防護：這筆觀測比上次確認還舊 → 不採信，狀態維持原樣
        last_confirmed = _parse(case.get("last_confirmed_at"))
        if observed_at and last_confirmed and observed_at < last_confirmed:
            continue

        if station is None:
            # 這輪根本沒看到這個站（缺站／查詢失敗）→ 不能當恢復
            escalation_repo.mark_unverified(case["case_id"], OBS_UNVERIFIED)
            continue
        if not observation_trustworthy(station, config):
            escalation_repo.mark_unverified(case["case_id"], OBS_UNVERIFIED)
            continue

        stamp = _iso(observed_at or moment)
        if station_id in need:
            # 新鮮觀測確認「仍然緊急」→ 續案並記錄確認時間
            escalation_repo.mark_confirmed(case["case_id"], stamp, OBS_CONFIRMED,
                                           station.get("source"))
        else:
            # 新鮮觀測確認「不再緊急」→ 這是唯一的關案路徑
            escalation_repo.mark_confirmed(case["case_id"], stamp, OBS_CONFIRMED,
                                           station.get("source"))
            escalation_repo.close_case(case["case_id"], CLOSE_RECOVERED, _iso(moment))

    # ── 2. 開案：需要緊急調度且沒有未結案案件 ───────────────────────
    #    ★不再因為「已被任務涵蓋」而跳過開案——派工中的站一樣要計時，
    #      否則司機還沒到之前那段延誤沒有人在算。
    for station_id, station in need.items():
        if station_id in open_cases:
            continue
        rec = rec_by_id.get(station_id)
        observed_at = _observed_at(station)
        escalation_repo.open_case({
            "case_id": f"CASE-{_iso(moment).replace(':', '').replace('-', '')}-{uuid.uuid4().hex[:6]}",
            "station_id": station_id,
            "station_name": station.get("station_name", ""),
            "district": station.get("district", ""),
            "opened_at": _iso(observed_at or moment),
            "trigger_reason": (rec or {}).get("reason") or _default_reason(station),
            "suggested_action": (f"{rec['action']} {rec['quantity']} 台" if rec else None),
        })
        fresh = escalation_repo.get_open_case_by_station(station_id)
        if fresh:
            escalation_repo.mark_confirmed(
                fresh["case_id"], _iso(observed_at or moment),
                OBS_CONFIRMED if observation_trustworthy(station, config) else OBS_UNVERIFIED,
                station.get("source"))

    return list_open_described(now=moment, config=config, tasks=tasks)


def list_open_described(now: Optional[_dt.datetime] = None, config: Optional[dict] = None,
                        tasks: Optional[list] = None) -> list:
    """只讀未結案案件並補階段／等待／承辦。不開不關（ADR-335 顯示路徑）。"""
    from db import escalation_repo

    moment = now or _now()
    assignments = assignments_by_station(tasks or [])
    result = []
    for case in escalation_repo.list_open_cases():
        try:
            described = describe(case, moment, config)
            described.update(responsibility_of(case["station_id"], assignments))
            if described["stage"] > int(case.get("highest_stage") or 0):
                escalation_repo.set_highest_stage(case["case_id"], described["stage"])
                described["highest_stage"] = described["stage"]
            result.append(described)
        except Exception as exc:  # noqa: BLE001
            print(f"[escalation] 描述案件失敗 case_id={case.get('case_id')}：{exc}")
    result.sort(key=lambda c: (-c["stage"], -c["waited_minutes"]))
    return result


def _observed_at(station: Optional[dict]) -> Optional[_dt.datetime]:
    """這筆站況的觀測時間（用於亂序防護與案件起算）。"""
    if not station:
        return None
    for key in ("observed_at", "source_timestamp", "timestamp", "received_at"):
        stamp = _parse(station.get(key))
        if stamp:
            return stamp
    return None


def assignments_by_station(tasks: Iterable[dict]) -> dict:
    """哪些站正被哪張未結案任務的哪個人承辦。

    只認「還沒處理完」的停靠站：completed／removed 的 stop 不算承辦，
    已釋放資源、已取消／完成的任務也不算——否則案件會掛在一個早就收工的人身上。
    """
    out: dict = {}
    for task in tasks or []:
        if task.get("task_status") not in OPEN_TASK_STATUS:
            continue
        if task.get("resources_released"):
            continue
        route = task.get("route") or task.get("route_json") or []
        if isinstance(route, str):
            try:
                route = json.loads(route)
            except (TypeError, ValueError):
                route = []
        for stop in route or []:
            if not isinstance(stop, dict) or not stop.get("station_id"):
                continue
            if (stop.get("station_status") or "pending") != "pending":
                continue
            out.setdefault(str(stop["station_id"]), []).append({
                "task_id": task.get("task_id"),
                "task_status": task.get("task_status"),
                "operator_id": task.get("assigned_operator"),
                "escort_id": task.get("assigned_escort"),
                "vehicle_id": task.get("assigned_vehicle"),
                "assigned_at": task.get("assigned_at"),
            })
    return out


def responsibility_of(station_id: str, assignments: dict) -> dict:
    """這一站現在由誰負責，以及該把提醒送給誰。

    多張未結案任務同時涵蓋同一站是資料異常，回 conflict 讓後台去查，
    不任選一個人扛——挑錯人比沒挑更糟。
    """
    rows = assignments.get(str(station_id)) or []
    if not rows:
        return {"assignments": [], "responsibility_status": "unassigned",
                "responsible_operator": None}
    if len(rows) > 1:
        return {"assignments": rows, "responsibility_status": "conflict",
                "responsible_operator": None}
    row = rows[0]
    status = "in_progress" if row.get("task_status") == "in_progress" else "assigned"
    return {"assignments": rows, "responsibility_status": status,
            "responsible_operator": row.get("operator_id")}


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
