"""
ADR-320：自動配單（系統為主的自動化派工）
==========================================
系統每輪掃描目前緊急調度清單，依緊急度由高到低，逐一為每個緊急站自動配對「鄰近適合的
人 + 車」並直接落地成派工單——複用 dispatch_builder.build_from_station 既有的車源決策
階梯（同區取車站就近取 → 同區湊不足跨區取一站補足 → 都不行才由總部載滿車出發），以及
同區優先、需總部時派總部待命人車的人力階梯。

流程（對齊使用者需求）：
  1. 取當前需調度清單（規則引擎排序，全量不截斷）。
  2. 過濾掉「已被進行中任務認領」的站（station_claim_map）與「人正在手動預覽/草稿」的站
     （active_draft_station_ids）——手動組單改為緊急人工介入專用，自動配單不搶這些站。
  3. 依緊急度由高到低逐一配單：build_from_station 組草稿 → confirm 落地。
     每配完一張，該站即被新任務認領，且同輪內就地記錄「已配站」，下一筆不再碰它
     （先配完一張、標記已配、過濾後再跑下一筆）。
  4. 資源被搶／無人無車／被人工手動搶走 → 吞 DispatchConflict，換下一站。

節奏：對齊官方即時資料約 5 分更新（config auto_dispatch.輪詢間隔_秒，預設 300）。
與 auto_detect（自動偵測完成）共用一把鎖序列化，避免兩個背景 thread 同時動任務/車/人。
僅在真實資料源（非 mock）且 config auto_dispatch.enabled=true 時運作。
"""

from __future__ import annotations

import threading
from typing import Optional

# ADR-320：自動配單與 auto_detect（自動偵測完成）共用這把鎖序列化，避免競態。
# auto_detect.scan_once 也會取用同一把（見該模組）。
COORDINATION_LOCK = threading.Lock()

# ADR-320：後台可即時開關自動配單（不必重啟服務）。None＝依 config 預設；
# True/False＝管理員 runtime 覆寫。背景 thread 恆在跑，每輪先看這個開關決定要不要配。
_runtime_enabled: Optional[bool] = None

# ADR-322：上一輪的診斷。原本配不出來時只回「本輪無可配的緊急站」，
# 但那句話涵蓋了六種完全不同的原因（開關關著／級別過濾光了／站被認領／
# 無車／無人／可行性被擋），害人只能瞎猜。這裡逐項記下來給後台看。
_last_diagnostics: dict = {}

# ADR-331：自動配單即時進度（供前端「執行視窗」用流動圖 + 逐筆清單呈現）。
# 一輪的階段：idle → selecting（取清單）→ dispatching（逐筆配）→ done/stopped。
# scan_once 逐筆更新，前端輪詢 GET /dispatch/auto-dispatch/progress。
_progress_lock = threading.Lock()
_progress: dict = {
    "phase": "idle",          # idle/selecting/dispatching/done
    "run_id": 0,              # 每輪遞增，前端用來辨識新一輪（跳出視窗）
    "started_at": None,
    "finished_at": None,
    "trigger": None,          # "manual"（立即配單）/ "auto"（背景輪）
    "queue_total": 0,         # 這輪符合條件、待配的緊急站數
    "processed": 0,           # 已處理（含成功/跳過）的站數
    "placed": [],             # 逐筆成功配出的單 [{trip_id, seed_station, vehicle, operator, stations}]
    "resources": {},          # 即時剩餘資源 {vehicles_available, vehicles_depot, operators_assignable, operators_depot}
    "stopped_because": None,  # 停止原因（無車/無人/無站/達上限）
}


def _progress_set(**kw) -> None:
    with _progress_lock:
        _progress.update(kw)


def _progress_snapshot() -> dict:
    with _progress_lock:
        snap = dict(_progress)
        snap["placed"] = list(_progress["placed"])
        snap["resources"] = dict(_progress["resources"])
    return snap


def get_progress() -> dict:
    """供 API：目前/最近一輪的自動配單進度快照。"""
    return _progress_snapshot()


def _cfg() -> dict:
    from config_loader import get_config
    return get_config().get("auto_dispatch", {}) or {}


def is_enabled() -> bool:
    """自動配單目前是否啟用（runtime 覆寫優先於 config 預設）。"""
    if _runtime_enabled is not None:
        return _runtime_enabled
    return bool(_cfg().get("enabled", False))


def set_enabled(enabled: bool) -> bool:
    """後台開關自動配單（runtime 覆寫，即時生效）。回傳設定後的啟用狀態。"""
    global _runtime_enabled
    _runtime_enabled = bool(enabled)
    return _runtime_enabled


def reset_runtime_enabled() -> None:
    """清掉 runtime 覆寫與執行狀態，回到 config 預設（測試/重置用）。"""
    global _runtime_enabled, _next_run_at, _last_run_at, _last_placed_count
    _runtime_enabled = None
    _next_run_at = None
    _last_run_at = None
    _last_placed_count = 0
    with _progress_lock:
        _progress.update(phase="idle", run_id=0, started_at=None, finished_at=None,
                         trigger=None, queue_total=0, processed=0, placed=[],
                         resources={}, stopped_because=None)


def _current_dispatch_list() -> list[dict]:
    """當前需調度清單（與 api/dispatch._current_dispatch_list 同口徑，全量不截斷）。"""
    from core.data.degradation import get_stations_with_degradation
    from core import build_dispatch_list
    from core.override_service import get_override_service

    stations = get_stations_with_degradation()
    overrides = get_override_service().active_station_ids()
    # apply_capacity=False：拿完整排序清單（自動配單自己會逐張配，不靠這裡截量能）
    recs = build_dispatch_list(stations, override_station_ids=overrides, apply_capacity=False)
    by_id = {str(s["station_id"]): s for s in stations}
    for rec in recs:
        st = by_id.get(str(rec["station_id"]), {})
        for key in ("total_docks", "service_available", "status"):
            if key in st:
                rec[key] = st[key]
    return recs


def _eligible_queue(recs: list[dict], skip_ids: set[str], levels: set[str]) -> list[dict]:
    """過濾 + 排序出「這輪要自動配單的緊急站佇列」。

    skip_ids：已被任務認領或人工草稿佔用的站，跳過。
    levels：只配這些緊急級別（空集合＝全配）。
    依 priority_score 由高到低（緊急度優先）。
    """
    out = []
    for r in recs:
        sid = str(r.get("station_id"))
        if sid in skip_ids:
            continue
        if levels and r.get("priority_level") not in levels:
            continue
        out.append(r)
    out.sort(key=lambda r: -float(r.get("priority_score", 0) or 0))
    return out


def scan_once(trigger: str = "auto") -> list[dict]:
    """跑一輪自動配單。回傳本輪成功落地的派工單紀錄清單（供測試/日誌）。

    先配完一張、標記該站已配、過濾後再跑下一筆（使用者要求的序列化配單）。
    任何單張錯誤（資源被搶/無人車/站被搶）都吞掉，換下一站，不中斷整輪。
    trigger："manual"（立即配單）/ "auto"（背景輪）——只用來標記進度來源。
    ADR-331：逐筆更新 _progress，供前端「執行視窗」流動圖即時呈現。
    """
    from core import dispatch_builder
    from core.dispatch_confirmation import confirm
    from core.dispatch_drafts import active_draft_station_ids
    from core.dispatch_errors import DispatchConflict, DispatchForbidden
    from core.providers import get_fleet_provider, get_operator_provider
    from core.task_execution import station_claim_map

    # ADR-320：後台開關關閉時，本輪不配（背景 thread 仍在跑，開關可即時再開）。
    global _last_diagnostics, _last_run_at, _last_placed_count
    diag: dict = {"enabled": is_enabled(), "reasons": {}}
    if not is_enabled():
        diag["stopped_because"] = "自動配單開關為關閉"
        _last_diagnostics = diag
        return []

    cfg = _cfg()
    operator_id = str(cfg.get("operator_id", "OP-002"))
    max_orders = int(cfg.get("每輪最大配單數", 20))
    levels = set(cfg.get("只配緊急級別", ["high"]) or [])

    def _fleet_op_snapshot() -> dict:
        fp = get_fleet_provider()
        opp = get_operator_provider()
        return {
            "vehicles_available": len(fp.available_vehicles()),
            "vehicles_depot": len(fp.depot_standby_vehicles()),
            "operators_assignable": len(opp.assignable_operators()),
            "operators_depot": len(opp.depot_standby_operators()),
        }

    def _has_available_vehicle() -> bool:
        """車隊是否還有可出勤的車（一般閒置車 + 總部待命車）。兩者皆空＝無車可派。"""
        fp = get_fleet_provider()
        return bool(fp.available_vehicles() or fp.depot_standby_vehicles())

    # ADR-331：開一輪進度（selecting 階段）。run_id 遞增讓前端辨識新一輪並跳出視窗。
    with _progress_lock:
        _progress["run_id"] += 1
        run_id = _progress["run_id"]
    _progress_set(phase="selecting", started_at=_utc_now().isoformat(), finished_at=None,
                  trigger=trigger, queue_total=0, processed=0, placed=[],
                  resources=_fleet_op_snapshot(), stopped_because=None)

    with COORDINATION_LOCK:
        recs = _current_dispatch_list()
        # 已被進行中任務認領的站 + 人工手動預覽/草稿佔用的站 → 這輪都避開
        claimed = set(station_claim_map().keys())
        drafted = active_draft_station_ids()
        skip_ids = claimed | drafted
        queue = _eligible_queue(recs, skip_ids, levels)

        fp = get_fleet_provider()
        opp = get_operator_provider()
        by_level: dict[str, int] = {}
        for r in recs:
            key = str(r.get("priority_level") or "unknown")
            by_level[key] = by_level.get(key, 0) + 1
        diag.update({
            "dispatch_total": len(recs),
            "by_level": by_level,
            "level_filter": sorted(levels) if levels else "全部",
            "skipped_claimed": len(claimed),
            "skipped_draft": len(drafted),
            "eligible": len(queue),
            "vehicles_available": len(fp.available_vehicles()),
            "vehicles_depot_standby": len(fp.depot_standby_vehicles()),
            "operators_assignable": len(opp.assignable_operators()),
            "operators_depot_standby": len(opp.depot_standby_operators()),
        })
        if not queue:
            if not recs:
                diag["stopped_because"] = "目前沒有任何需調度站"
            elif levels:
                diag["stopped_because"] = (
                    f"需調度 {len(recs)} 站，但只配 {sorted(levels)} 級別；"
                    f"各級別數量：{by_level}。放寬 config auto_dispatch.只配緊急級別 即可納入")
            else:
                diag["stopped_because"] = "需調度站全數已被任務認領或人工草稿佔用"

        # ADR-331：進入 dispatching 階段，帶佇列總數與最新資源快照。
        _progress_set(phase="dispatching", queue_total=len(queue),
                      resources=_fleet_op_snapshot())

        placed: list[dict] = []
        stop_reason: Optional[str] = None
        # 同輪內就地累積「已配站」：一張單可能一次涵蓋多站（車源階梯會拉入取車站/鄰近補車站），
        # 全部標記，避免同輪把同一站配進第二張單。
        consumed: set[str] = set(skip_ids)
        processed = 0
        for rec in queue:
            if len(placed) >= max_orders:
                stop_reason = f"已達每輪上限 {max_orders} 張"
                break
            # ADR-320：沒有閒置車可出勤就「停止本輪」自動配單，等下一輪（5 分鐘後）再偵測。
            if not _has_available_vehicle():
                stop_reason = "車隊已無可出勤的車（一般閒置車與總站待命車皆為 0）"
                diag["stopped_because"] = stop_reason
                break
            seed_id = str(rec.get("station_id"))
            if seed_id in consumed:
                continue  # 已被前一張單涵蓋
            processed += 1
            try:
                # 用「目前扣掉已配站」的清單組單，避免把已配站再排進這張
                pool = [r for r in recs if str(r.get("station_id")) not in consumed]
                draft = dispatch_builder.build_from_station(
                    seed_id, pool, operator_id=None, created_by=operator_id)
                if draft.get("error") or not draft.get("stations"):
                    _tally(diag, "組不出站點")
                    consumed.add(seed_id)  # 這站這輪組不出單，先擱著，避免卡住佇列
                    continue
                if draft.get("blocking_reasons"):
                    # 有阻擋（無足夠人車/工時/重疊等）→ 這輪配不了，換下一站
                    _tally(diag, draft["blocking_reasons"][0].get("message", "可行性被擋"))
                    consumed.add(seed_id)
                    continue
                if not (draft.get("assigned_vehicle") and draft.get("assigned_operator")):
                    _tally(diag, "無可用車" if not draft.get("assigned_vehicle") else "無可用人員")
                    consumed.add(seed_id)  # 無可用車或人，換下一站
                    continue
                result = confirm({"draft_id": draft["draft_id"], "version": draft["version"]},
                                 operator_id)
                # 落地成功：把這張單涵蓋的所有站標記為已配（同輪不再碰）
                for s in draft["stations"]:
                    consumed.add(str(s.get("station_id")))
                entry = {
                    "trip_id": result.get("trip_id"),
                    "seed_station": seed_id,
                    "seed_station_name": rec.get("station_name") or seed_id,
                    "district": rec.get("district"),
                    "stations": [str(s.get("station_id")) for s in draft["stations"]],
                    "vehicle": draft.get("assigned_vehicle"),
                    "operator": draft.get("assigned_operator"),
                    "priority_level": rec.get("priority_level"),
                }
                placed.append(entry)
                # ADR-331：逐筆推進進度——附最新這筆 + 剩餘資源遞減 + 已處理數。
                with _progress_lock:
                    _progress["placed"].append(entry)
                    _progress["processed"] = processed
                    _progress["resources"] = _fleet_op_snapshot()
            except (DispatchConflict, DispatchForbidden, KeyError) as exc:
                _tally(diag, f"資源衝突：{exc}")
                consumed.add(seed_id)
                _progress_set(processed=processed)
                continue
            except Exception as exc:  # noqa: BLE001
                _tally(diag, f"{type(exc).__name__}: {exc}")
                consumed.add(seed_id)
                _progress_set(processed=processed)
                continue
        diag["placed"] = len(placed)
        _last_diagnostics = diag
        # ADR-331：收尾——若沒有明確停止原因（把佇列跑完），標「佇列已跑完」。
        if stop_reason is None:
            stop_reason = diag.get("stopped_because") or (
                "本輪需調度站已全部處理完" if queue else diag.get("stopped_because"))
        # 在標 done 之前先寫 last_run（避免輪詢者看到 done 卻讀到舊的 last_run）。
        _last_run_at = _utc_now().isoformat()
        _last_placed_count = len(placed)
        _progress_set(phase="done", finished_at=_utc_now().isoformat(),
                      processed=processed, resources=_fleet_op_snapshot(),
                      stopped_because=stop_reason)
        return placed


def _tally(diag: dict, reason: str) -> None:
    """累計「這一輪為什麼配不出去」的原因次數（訊息過長時截斷）。"""
    key = (reason or "未知")[:80]
    diag["reasons"][key] = diag["reasons"].get(key, 0) + 1


# ── 背景輪詢迴圈（daemon thread；main.py lifespan 啟動）──
_stop_event: Optional[threading.Event] = None
_thread: Optional[threading.Thread] = None
_wakeup: Optional[threading.Event] = None   # 手動立即觸發：叫醒迴圈提早跑一輪

# 執行狀態（供儀表板顯示倒數與上次結果）。時間用 UTC ISO 字串。
import datetime as _dt

_next_run_at: Optional[str] = None      # 下一輪預定執行時間（ISO，UTC）
_last_run_at: Optional[str] = None      # 上一輪實際執行時間
_last_placed_count: int = 0             # 上一輪落地張數


def _utc_now() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc)


def _set_next_run(interval_sec: float) -> None:
    global _next_run_at
    _next_run_at = (_utc_now() + _dt.timedelta(seconds=interval_sec)).isoformat()


def run_status() -> dict:
    """供 API/儀表板：目前開關、背景是否在跑、下一輪時間、上次結果與間隔。"""
    return {
        "enabled": is_enabled(),
        "running": _thread is not None and _thread.is_alive(),
        "interval_sec": int(_cfg().get("輪詢間隔_秒", 300)),
        "next_run_at": _next_run_at,
        "last_run_at": _last_run_at,
        "last_placed_count": _last_placed_count,
        "diagnostics": dict(_last_diagnostics),
        "progress": get_progress(),
    }


_manual_thread: Optional[threading.Thread] = None


def _run_scan(trigger: str) -> None:
    """實際跑一輪（背景 thread 用，避免請求端逾時）。last_run 由 scan_once 內部更新。"""
    try:
        placed = scan_once(trigger=trigger)
        if placed:
            print(f"[auto_dispatch] 自動配單完成 {len(placed)} 張（{trigger}）："
                  f"{[(p['seed_station'], p['trip_id']) for p in placed]}")
    except Exception as e:  # noqa: BLE001
        print(f"[auto_dispatch] 配單發生錯誤（略過本輪）：{e}")


def run_now() -> dict:
    """後台手動觸發：ADR-331 改為「非同步啟動一輪」立刻回，不等它跑完（避免前端逾時）。

    回傳目前進度快照（run_id/phase）；前端據此開執行視窗並輪詢 get_progress。
    若已有一輪在跑（背景輪或前一次手動），不重複啟動，直接回目前進度。
    """
    global _manual_thread
    if not is_enabled():
        # 開關關著：直接回一個「done」進度，讓前端視窗顯示原因後關閉。
        _progress_set(phase="done", trigger="manual", finished_at=_utc_now().isoformat(),
                      stopped_because="自動配單開關為關閉", queue_total=0, processed=0, placed=[])
        return {"started": False, "progress": get_progress()}
    already = _manual_thread is not None and _manual_thread.is_alive()
    running_round = get_progress().get("phase") in ("selecting", "dispatching")
    if not already and not running_round:
        # 啟動前先同步把進度標成 selecting，避免輪詢者在 thread 真正開跑前讀到上一輪的 done。
        _progress_set(phase="selecting", trigger="manual", finished_at=None)
        _manual_thread = threading.Thread(target=_run_scan, args=("manual",),
                                          daemon=True, name="auto-dispatch-manual")
        _manual_thread.start()
    # 叫醒背景迴圈重設下一輪計時（避免剛手動跑完，背景又緊接著跑一次）
    if _wakeup is not None:
        _wakeup.set()
    else:
        _set_next_run(float(_cfg().get("輪詢間隔_秒", 300)))
    return {"started": True, "progress": get_progress()}


def _loop(interval_sec: float, stop_event: threading.Event, wakeup: threading.Event) -> None:
    while not stop_event.is_set():
        _run_scan("auto")
        _set_next_run(interval_sec)
        # 等到下一輪，或被 run_now 叫醒提早結束等待（重設倒數後進下一輪）。
        wakeup.clear()
        wakeup.wait(interval_sec)   # 被 set 立即返回；否則等滿 interval_sec


def start_background(mode: str) -> bool:
    """啟動背景自動配單（daemon thread）。回傳是否有啟動。

    僅在資料源為真實源（非 mock/None）時啟動。thread 恆在跑，每輪由 is_enabled()
    （runtime 開關優先於 config 預設）決定要不要配單——讓後台能即時開關，不必重啟服務。
    """
    global _stop_event, _thread, _wakeup
    cfg = _cfg()
    if mode in (None, "mock"):
        return False  # mock 資料不動，自動配單沒有意義
    if _thread is not None and _thread.is_alive():
        return True   # 已在跑
    interval = float(cfg.get("輪詢間隔_秒", cfg.get("interval_sec", 300)))
    _stop_event = threading.Event()
    _wakeup = threading.Event()
    _set_next_run(interval)
    _thread = threading.Thread(
        target=_loop, args=(interval, _stop_event, _wakeup), daemon=True, name="auto-dispatch")
    _thread.start()
    return True


def stop_background() -> None:
    """停止背景輪詢（測試/關機用）。"""
    global _stop_event, _thread, _next_run_at
    if _stop_event is not None:
        _stop_event.set()
    if _wakeup is not None:
        _wakeup.set()
    _thread = None
    _next_run_at = None
