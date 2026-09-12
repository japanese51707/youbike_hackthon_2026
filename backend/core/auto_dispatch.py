"""
ADR-319：自動配單（系統為主的自動化派工）
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

# ADR-319：自動配單與 auto_detect（自動偵測完成）共用這把鎖序列化，避免競態。
# auto_detect.scan_once 也會取用同一把（見該模組）。
COORDINATION_LOCK = threading.Lock()

# ADR-319：後台可即時開關自動配單（不必重啟服務）。None＝依 config 預設；
# True/False＝管理員 runtime 覆寫。背景 thread 恆在跑，每輪先看這個開關決定要不要配。
_runtime_enabled: Optional[bool] = None


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
    """清掉 runtime 覆寫，回到 config 預設（測試/重置用）。"""
    global _runtime_enabled
    _runtime_enabled = None


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


def scan_once() -> list[dict]:
    """跑一輪自動配單。回傳本輪成功落地的派工單紀錄清單（供測試/日誌）。

    先配完一張、標記該站已配、過濾後再跑下一筆（使用者要求的序列化配單）。
    任何單張錯誤（資源被搶/無人車/站被搶）都吞掉，換下一站，不中斷整輪。
    """
    from core import dispatch_builder
    from core.dispatch_confirmation import confirm
    from core.dispatch_drafts import active_draft_station_ids
    from core.dispatch_errors import DispatchConflict, DispatchForbidden
    from core.providers import get_fleet_provider
    from core.task_execution import station_claim_map

    # ADR-319：後台開關關閉時，本輪不配（背景 thread 仍在跑，開關可即時再開）。
    if not is_enabled():
        return []

    cfg = _cfg()
    operator_id = str(cfg.get("operator_id", "OP-002"))
    max_orders = int(cfg.get("每輪最大配單數", 20))
    levels = set(cfg.get("只配緊急級別", ["high"]) or [])

    def _has_available_vehicle() -> bool:
        """車隊是否還有可出勤的車（一般閒置車 + 總部待命車）。兩者皆空＝無車可派。"""
        fp = get_fleet_provider()
        return bool(fp.available_vehicles() or fp.depot_standby_vehicles())

    with COORDINATION_LOCK:
        recs = _current_dispatch_list()
        # 已被進行中任務認領的站 + 人工手動預覽/草稿佔用的站 → 這輪都避開
        skip_ids = set(station_claim_map().keys()) | active_draft_station_ids()
        queue = _eligible_queue(recs, skip_ids, levels)

        placed: list[dict] = []
        # 同輪內就地累積「已配站」：一張單可能一次涵蓋多站（車源階梯會拉入取車站/鄰近補車站），
        # 全部標記，避免同輪把同一站配進第二張單。
        consumed: set[str] = set(skip_ids)
        for rec in queue:
            if len(placed) >= max_orders:
                break
            # ADR-319：沒有閒置車可出勤就「停止本輪」自動配單，等下一輪（5 分鐘後）再偵測。
            # 車隊已無可派車時，繼續掃其他站也配不出來，直接結束本輪最省。
            if not _has_available_vehicle():
                break
            seed_id = str(rec.get("station_id"))
            if seed_id in consumed:
                continue  # 已被前一張單涵蓋
            try:
                # 用「目前扣掉已配站」的清單組單，避免把已配站再排進這張
                pool = [r for r in recs if str(r.get("station_id")) not in consumed]
                draft = dispatch_builder.build_from_station(
                    seed_id, pool, operator_id=None, created_by=operator_id)
                if draft.get("error") or not draft.get("stations"):
                    consumed.add(seed_id)  # 這站這輪組不出單，先擱著，避免卡住佇列
                    continue
                if draft.get("blocking_reasons"):
                    # 有阻擋（無足夠人車/工時/重疊等）→ 這輪配不了，換下一站
                    consumed.add(seed_id)
                    continue
                if not (draft.get("assigned_vehicle") and draft.get("assigned_operator")):
                    consumed.add(seed_id)  # 無可用車或人，換下一站
                    continue
                result = confirm({"draft_id": draft["draft_id"], "version": draft["version"]},
                                 operator_id)
                # 落地成功：把這張單涵蓋的所有站標記為已配（同輪不再碰）
                for s in draft["stations"]:
                    consumed.add(str(s.get("station_id")))
                placed.append({
                    "trip_id": result.get("trip_id"),
                    "seed_station": seed_id,
                    "stations": [str(s.get("station_id")) for s in draft["stations"]],
                    "vehicle": draft.get("assigned_vehicle"),
                    "operator": draft.get("assigned_operator"),
                    "priority_level": rec.get("priority_level"),
                })
            except (DispatchConflict, DispatchForbidden, KeyError):
                # 站/車/人被搶或狀態已變：略過這站，換下一筆
                consumed.add(seed_id)
                continue
            except Exception:  # noqa: BLE001
                consumed.add(seed_id)
                continue
        return placed


# ── 背景輪詢迴圈（daemon thread；main.py lifespan 啟動）──
_stop_event: Optional[threading.Event] = None
_thread: Optional[threading.Thread] = None


def _loop(interval_sec: float, stop_event: threading.Event) -> None:
    while not stop_event.is_set():
        try:
            placed = scan_once()
            if placed:
                print(f"[auto_dispatch] 自動配單完成 {len(placed)} 張："
                      f"{[(p['seed_station'], p['trip_id']) for p in placed]}")
        except Exception as e:  # noqa: BLE001
            print(f"[auto_dispatch] 輪詢發生錯誤（略過本輪）：{e}")
        stop_event.wait(interval_sec)


def start_background(mode: str) -> bool:
    """啟動背景自動配單（daemon thread）。回傳是否有啟動。

    僅在資料源為真實源（非 mock/None）時啟動。thread 恆在跑，每輪由 is_enabled()
    （runtime 開關優先於 config 預設）決定要不要配單——讓後台能即時開關，不必重啟服務。
    """
    global _stop_event, _thread
    cfg = _cfg()
    if mode in (None, "mock"):
        return False  # mock 資料不動，自動配單沒有意義
    if _thread is not None and _thread.is_alive():
        return True   # 已在跑
    interval = float(cfg.get("輪詢間隔_秒", cfg.get("interval_sec", 300)))
    _stop_event = threading.Event()
    _thread = threading.Thread(
        target=_loop, args=(interval, _stop_event), daemon=True, name="auto-dispatch")
    _thread.start()
    return True


def stop_background() -> None:
    """停止背景輪詢（測試/關機用）。"""
    global _stop_event, _thread
    if _stop_event is not None:
        _stop_event.set()
    _thread = None
