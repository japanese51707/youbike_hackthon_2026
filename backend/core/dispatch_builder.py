"""
互動式派工單組建（core.dispatch_builder）— ADR-119
==================================================
後台管理人員互動組單的三個入口 + 草稿預覽 + 確認落地。
系統是決策輔助（算建議、由後台拍板），非自動派工。

三入口（都產出「草稿派工單 draft」，不落地 DB，供預覽）：
  build_from_vehicle(vehicle_id, operator_id, district=None)  # 以車為起點
  build_from_station(station_id, operator_id=None)            # 以站為起點
  build_emergency(station_ids, vehicle_id=None, operator_id=None)  # 緊急出車

確認落地：
  confirm_trip(draft, operator)   # 草稿 → assigned（走 dispatcher._persist_trip）

底層演算全複用 ADR-117 的 dispatcher（_order_route/_pack_trips/_estimate_trip_kpi/_haversine_km），
本模組只加「互動入口 + 草稿/預估 + 確認」。

職責（單一）：組草稿 + 預估 + 確認。不做：觸發判斷(rule_engine)、狀態機(task_manager)、
執行閉環(task_execution)。確認後的任務由 task_execution 接手。
"""

from __future__ import annotations
import datetime as _dt
from typing import Optional

from config_loader import get_config
from copy import deepcopy
from core.dispatch_drafts import remember_draft
from . import dispatcher as _dsp
from .providers import get_fleet_provider, get_operator_provider


def _fill_station_targets(stations: list[dict]) -> None:
    """每站補目標存量（ADR-115/117：主指令用目標值）與站級狀態。"""
    for s in stations:
        if "target_available" not in s:
            avail = float(s.get("current_available", 0))
            qty = float(s.get("quantity", 0))
            s["target_available"] = round(avail + qty if s.get("action") != "取車"
                                          else avail - qty, 0)
        s.setdefault("station_status", "pending")


def _operator_candidates(assignable: list[dict], depot: list[dict],
                         district: Optional[str]) -> dict:
    """司機候選（供前端下拉選），依後端優先序分層：同區 → 鄰近（其他區/未定） → 總站待命。

    每筆帶 operator_id / name / tier / current_district，讓調派員在同分時自行改選。
    """
    def entry(o, tier):
        return {"operator_id": o.get("operator_id"), "name": o.get("name"),
                "tier": tier, "current_district": o.get("current_district")}

    in_district, nearby = [], []
    for o in assignable:
        if district and o.get("current_district") == district:
            in_district.append(entry(o, "該區"))
        else:
            nearby.append(entry(o, "鄰近/待命"))
    return {
        "in_district": in_district,
        "nearby": nearby,
        "depot_standby": [entry(o, "總站待命") for o in depot],
    }


def _resolve_escort(op, escort_id, driver):
    """解析隨車人員（ADR-308）。未指定回 None；與司機同一人時忽略（不可一人兼兩角）。"""
    if not escort_id:
        return None
    if driver and str(escort_id) == str(driver.get("operator_id")):
        return None
    return op.get_operator(escort_id)


def _preset_onboard_value(vehicle: dict, stations: list[dict], cfg: dict) -> int:
    """ADR-317 預設出車載量規則：非總部車=0；總部車=本趟補車需求量（不超過容量）。"""
    demand = sum(int(s.get("quantity", 0) or 0) for s in stations if s.get("action") != "取車")
    capacity = int(vehicle.get("max_capacity") or _dsp._default_capacity(cfg))
    return min(demand, capacity) if vehicle.get("is_depot") else 0


def _preset_onboard(vehicle: Optional[dict], stations: list[dict], cfg: dict) -> Optional[dict]:
    """ADR-317：組單時自動預設出車載量，取消人工「回報並重算」。

    規則（(甲) 純預設，不覆蓋已知值）：
      - 車上載量「未知」（onboard_bikes 為 None）時才套預設：
          非總部載運車（is_depot=False）→ 0 台（就近取車補足，不預先載車）；
          總部載運車（is_depot=True）→ 本趟補車需求量（總部載滿出發），不超過容量。
      - 車上「已有回報值」時尊重實際值，不覆蓋（保留「車上有車就用車上的車」能力）。

    回傳一份 vehicle 副本（不動 DB 原車），供 feasibility 直接用；
    vehicle 為 None、或已有回報值時原樣回傳（不覆寫）。
    """
    if not vehicle or vehicle.get("onboard_bikes") is not None:
        return vehicle
    veh = deepcopy(vehicle)
    veh["onboard_bikes"] = _preset_onboard_value(veh, stations, cfg)
    veh["onboard_source"] = "task_completion"          # 系統推算（可追溯來源之一）
    veh["onboard_observed_at"] = _dt.datetime.now().isoformat(timespec="seconds")
    return veh


def _make_draft(stations, vehicle, operator, district, cfg, now,
                start_lat=None, start_lng=None, note="", escort=None) -> dict:
    """組一張草稿派工單（含路徑順序 + 預估）。不落地。

    escort（可選）：隨車人員（第二名）。可行性/路徑只依司機 operator 算，
    隨車不影響載量與工時視野，僅作為第二名資源在確認時一併占用/釋放。
    """
    ordered = _dsp._order_route(deepcopy(stations), start_lat, start_lng)
    _fill_station_targets(ordered)
    # ADR-317：出車載量自動預設（非總部車=0；總部車=本趟補車需求量），取消人工回報並重算。
    vehicle = _preset_onboard(vehicle, ordered, cfg)
    kpi = _dsp._estimate_trip_kpi(ordered, cfg, start_lat, start_lng)
    default_cap = _dsp._default_capacity(cfg)
    estimate = {
        **kpi,
        "total_quantity": sum(int(s.get("quantity", 0)) for s in ordered),
        "stop_count": len(ordered),
        "urgency_sum": round(sum(float(s.get("priority_score", 0)) for s in ordered), 1),
    }
    mode = "emergency" if note.startswith("緊急出車") else _dsp.current_mode(now)
    # ADR-123/304：預覽就跑與確認相同的可行性評估，草稿帶逐站載量計畫與阻擋原因
    from core.dispatch_feasibility import evaluate_feasibility
    feasibility = evaluate_feasibility(
        ordered, vehicle, operator, mode=mode, now=now, config=cfg,
        start_lat=start_lat, start_lng=start_lng,
        est_total_min=kpi.get("est_total_min"),
        check_resources=bool(vehicle and operator))
    for stop, entry in zip(ordered, feasibility["load_plan"]):
        stop["arrival_offset_min"] = entry["arrival_offset_min"]
        stop["horizon_used_min"] = entry["horizon_used_min"]
        stop["onboard_after"] = entry["onboard_after"]
    return {
        "is_draft": True,                       # ★草稿：預覽用，未確認不落地
        "district": district,
        "shift": _dsp.current_shift(now),
        "mode": mode,
        "stations": ordered,
        "assigned_vehicle": vehicle.get("vehicle_id") if vehicle else None,
        "assigned_operator": operator.get("operator_id") if operator else None,
        "assigned_escort": escort.get("operator_id") if escort else None,   # ADR-308 隨車（可選）
        "vehicle_capacity": int(vehicle.get("max_capacity") or default_cap) if vehicle else None,
        # ADR-308 地圖路線起點（車輛位置；無座標時前端退回用第一站）
        "start": {"lat": start_lat, "lng": start_lng} if start_lat is not None else None,
        "estimate": estimate,                   # 預估：距離/時間/載運量/緊急度加總（ADR-119）
        # ADR-304 §1：空陣列＝可確認；非空＝確認會被擋，且原因在預覽就看得到
        "blocking_reasons": feasibility["blocking_reasons"],
        "load_plan": feasibility["load_plan"],  # ADR-123：逐站到達時間／視野／車上載量
        "onboard_start": feasibility["onboard_start"],
        "onboard_end": feasibility["onboard_end"],
        "note": note,
    }


# ── 入口 (a)：以車為起點 ──
@remember_draft
def build_from_vehicle(
    vehicle_id: str, operator_id: str, dispatch_list: list[dict],
    district: Optional[str] = None, config=None, fleet_provider=None, now=None,
    escort_id: Optional[str] = None,
) -> dict:
    """ADR-119 入口 a：選車 → 用車位置算最適出車站點順序。

    district=None：預設用車當前所在行政區的需調度站。
    district 指定（後台改目標區）：改用該區的站 → 自動重算（換區重跑）。
    dispatch_list：當前需調度站清單（含 district/lat/lng/priority_score/action/quantity）。
    """
    cfg = config or get_config()
    fp = fleet_provider or get_fleet_provider()
    veh = fp.get_vehicle(vehicle_id)
    if veh is None:
        return {"error": f"找不到車輛 {vehicle_id}", "is_draft": True, "stations": []}

    target_district = district or veh.get("current_district")
    pool = [r for r in dispatch_list
            if not target_district or r.get("district") == target_district]
    # 依載運量切一趟（取該車能裝的第一趟）
    cap = int(veh.get("max_capacity") or _dsp._default_capacity(cfg))
    max_stops = int(cfg.get("fleet", {}).get("每趟最大站數", 3))
    # 依緊急度排序後切趟，取第一趟
    pool = sorted(pool, key=lambda r: -float(r.get("priority_score", 0)))
    trips = _dsp._pack_trips(pool, cap, max_stops)
    stations = trips[0] if trips else []
    op = get_operator_provider()
    # 入口 a 通常由後台先選好人車；未指定時仍按優先序自動帶一名（同區優先）。
    assignable = op.assignable_operators(district=target_district)
    depot_ops = op.depot_standby_operators()
    if operator_id:
        oper = op.get_operator(operator_id)
    else:
        oper = assignable[0] if assignable else (depot_ops[0] if depot_ops else None)
    escort = _resolve_escort(op, escort_id, oper)
    draft = _make_draft(stations, veh, oper, target_district, cfg, now,
                        start_lat=veh.get("current_lat"), start_lng=veh.get("current_lng"),
                        note=f"以車為起點（{'指定區' if district else '車所在區'}：{target_district}）",
                        escort=escort)
    draft["operator_candidates"] = _operator_candidates(assignable, depot_ops, target_district)
    return draft


# ── 入口 (b)：以站為起點 ──
@remember_draft
def build_from_station(
    station_id: str, dispatch_list: list[dict], operator_id: Optional[str] = None,
    vehicle_id: Optional[str] = None, config=None, fleet_provider=None,
    operator_provider=None, now=None, escort_id: Optional[str] = None,
) -> dict:
    """ADR-119 入口 b：選站 → 依該站所屬行政區最適化，找車 + 人，算站點順序。

    找車候選順序（未指定 vehicle_id 時，回 candidates 供後台選）：
      該區閒置車 → 鄰近區閒置車 → 總站待命車。
    人員池 = 該區閒置 + 總站待命人力。
    """
    cfg = config or get_config()
    fp = fleet_provider or get_fleet_provider()
    op = operator_provider or get_operator_provider()

    seed = next((r for r in dispatch_list if str(r.get("station_id")) == str(station_id)), None)
    if seed is None:
        # ADR-315：前端需調度清單走快取（60 秒），與組單即時清單可能有落差 → 名單上的站
        # 在即時清單裡查無。此時用即時站況為該站臨時生成建議（同 emergency 的保底機制），
        # 讓「點名單任一站都能組單」，而不是直接報「不在清單」。
        extra = _emergency_recs_for({str(station_id)}, cfg)
        seed = next((r for r in extra if str(r.get("station_id")) == str(station_id)), None)
        if seed is None:
            return {"error": f"站點 {station_id} 查無即時站況或目前無需調度", "is_draft": True, "stations": []}
        dispatch_list = list(dispatch_list) + extra
    district = seed.get("district")

    # ADR-316：所有時段皆可跨區，但「同區優先、跨區次之」。
    # 主挑站池 = 同區站（被點站置頂、其餘依緊急度）；跨區站只在同區湊不足時當備援拉入。
    pool = sorted([r for r in dispatch_list if r.get("district") == district],
                  key=lambda r: (str(r.get("station_id")) != str(station_id),
                                 -float(r.get("priority_score", 0))))
    default_cap = _dsp._default_capacity(cfg)
    max_stops = int(cfg.get("fleet", {}).get("每趟最大站數", 3))

    # 找車候選：該區閒置 → 鄰近區閒置 → 總站待命（ADR-119）
    avail = fp.available_vehicles()
    in_district = [v for v in avail if v.get("current_district") == district]
    nearby = [v for v in avail if v.get("current_district") != district]
    depot = fp.depot_standby_vehicles()
    candidates = in_district + nearby + depot

    # 先用「該區優先」的候選車估容量挑站（真正選哪台車在挑完站、判斷是否需總部後定）。
    tentative_veh = fp.get_vehicle(vehicle_id) if vehicle_id else (candidates[0] if candidates else None)
    cap = int(tentative_veh.get("max_capacity") or default_cap) if tentative_veh else default_cap
    onboard = tentative_veh.get("onboard_bikes") if tentative_veh else None
    onboard = int(onboard) if onboard is not None else 0
    # 車源決策階梯（ADR-315/316）：①車上載量 ②同區取車站就近取（在 pool 內）
    # ③同區湊不足 → 跨區取車站補足車源（同區優先、跨區次之，所有時段適用）。
    cross_collectors = sorted(
        [r for r in dispatch_list
         if r.get("action") == "取車" and r.get("district") != district],
        key=lambda r: -float(r.get("quantity", 0) or 0))
    stations = _dsp._pack_supply_aware_trip(
        pool, cap, max_stops, seed_id=station_id, onboard=onboard,
        start_lat=tentative_veh.get("current_lat") if tentative_veh else None,
        start_lng=tentative_veh.get("current_lng") if tentative_veh else None,
        extra_collectors=cross_collectors)

    # ADR-315：判斷這趟是否「純靠總部載車」——補車需求超過（車上載量 + 趟內取車站可取量）。
    _demand0 = sum(int(s.get("quantity", 0) or 0) for s in stations if s.get("action") != "取車")
    _supply0 = onboard + sum(int(s.get("quantity", 0) or 0) for s in stations if s.get("action") == "取車")
    needs_depot = _demand0 > _supply0
    if vehicle_id:
        veh = fp.get_vehicle(vehicle_id)
    elif needs_depot and depot:
        # 需總部載車：優先派總站待命車（已備車、可跨區支援），而非當地閒置車。
        veh = depot[0]
    else:
        veh = candidates[0] if candidates else None

    # 人員：指定 → 用指定；否則後端排優先序。
    # ADR-315：需總部載車時（needs_depot），執行人員也優先派「總部待命人員」（隨總站待命車出發），
    # 而非當地區域人員；否則維持同區優先。司機不常態待命，被派到任務當下才上工。
    assignable = op.assignable_operators(district=district)
    depot_ops = op.depot_standby_operators()
    if operator_id:
        oper = op.get_operator(operator_id)
    elif needs_depot and depot_ops:
        oper = depot_ops[0]
    else:
        oper = assignable[0] if assignable else (depot_ops[0] if depot_ops else None)
    escort = _resolve_escort(op, escort_id, oper)

    # 大夜跨區時本趟可能含多區站點，district 標示改為涵蓋範圍（否則落地/顯示會誤標單一區）。
    trip_districts = {s.get("district") for s in stations if s.get("district")}
    draft_district = district if len(trip_districts) <= 1 else "跨區"
    note_area = district if len(trip_districts) <= 1 else f"{district}＋跨區支援"
    draft = _make_draft(stations, veh, oper, draft_district, cfg, now,
                        start_lat=veh.get("current_lat") if veh else None,
                        start_lng=veh.get("current_lng") if veh else None,
                        note=f"以站為起點（{station_id} / {note_area}）",
                        escort=escort)
    # 附車輛候選（分類供後台選；無指定車時特別有用）
    draft["vehicle_candidates"] = {
        "in_district": [v["vehicle_id"] for v in in_district],
        "nearby": [v["vehicle_id"] for v in nearby],
        "depot_standby": [v["vehicle_id"] for v in depot],
    }
    # 附司機候選（後端優先序：同區在前）。同分（同層級）時後台可自行改選。
    draft["operator_candidates"] = _operator_candidates(assignable, depot_ops, district)
    if not in_district and not nearby:
        draft["note"] += "｜該區與鄰近無閒置車，建議用總站待命車"

    # ADR-315 車源階梯最後一關：若補車需求仍超過（車上載量 + 趟內取車站可取量），
    # 代表同區＋跨區都湊不到足夠車源 → 需從總部載滿車出發調度（供未來全自動流程升級為警示）。
    _demand = sum(int(s.get("quantity", 0) or 0) for s in stations if s.get("action") != "取車")
    _supply = onboard + sum(int(s.get("quantity", 0) or 0) for s in stations if s.get("action") == "取車")
    if _demand > _supply:
        gap = _demand - _supply
        draft["supply_shortfall"] = gap
        draft["needs_depot_refill"] = True
        draft["note"] += f"｜⚠ 附近無足夠車源可取（缺 {gap} 台），需由總部載滿車出發調度"
    return draft


def _emergency_recs_for(station_ids: set[str], cfg) -> list[dict]:
    """為「不在自動推薦清單」的緊急指定站，用即時站況臨時生成建議條目。

    緊急出車由後台針對特定站強制發動：
      1. 先撈即時站況；規則引擎若認為需調度 → 用引擎的建議（含真實緊急度/原因）。
      2. 規則引擎不觸發（站況正常/剛恢復）→ 用即時站況做「保底條目」，
         依現況缺車補、滿車取，讓後台仍能對它強制出車（原因標明為後台強制）。
    找不到即時站況（查無此站）的 ID 直接略過。
    """
    from core.data import get_stations_with_degradation
    from core import build_dispatch_list

    live = {str(s["station_id"]): s for s in get_stations_with_degradation()
            if str(s["station_id"]) in station_ids}
    if not live:
        return []

    # 先讓規則引擎評估（拿到 priority_score/recommendation_id 等完整欄位）
    engine_recs = {str(r["station_id"]): r
                   for r in build_dispatch_list(list(live.values()), config=cfg)}

    out = []
    for sid, st in live.items():
        rec = engine_recs.get(sid)
        if rec is not None:
            out.append(rec)
            continue
        # 保底條目：規則引擎未觸發，但後台要強制出車。依現況判斷補/取。
        total = float(st.get("total_docks", 0) or 0)
        avail = float(st.get("available_bikes", 0) or 0)
        target = round(total * float(cfg.get("target", {}).get("預設借用率百分比", 50)) / 100)
        action = "補車" if avail < target else "取車"
        qty = int(min(max(1, abs(round(target - avail))), cfg.get("fleet", {}).get("每車容量", 15)))
        out.append({
            **st,
            "action": action,
            "quantity": qty,
            "target_available": float(target),
            "priority_score": 50.0,
            "priority_level": "medium",
            "urgency_tier": "normal",
            "reason": f"後台緊急指定出車（現況 {avail:.0f}/{total:.0f} 台，非自動觸發）",
            "basis": "後台強制",
            "current_available": int(avail),
            "recommendation_id": f"EMG-{sid}",
        })
    return out


# ── 入口 (c)：緊急出車 ──
@remember_draft
def build_emergency(
    station_ids: list[str], dispatch_list: list[dict],
    vehicle_id: Optional[str] = None, operator_id: Optional[str] = None,
    config=None, fleet_provider=None, operator_provider=None, now=None,
    escort_id: Optional[str] = None,
) -> dict:
    """ADR-119 入口 c：後台自選站（+可選車/人），緊急出車。

    資源優先序（未指定 vehicle_id 時，系統建議，後台可覆寫）：
      1. 就近閒置的一般調度車（成本低，不動用戰備）
      2. 才動用預備車 standby（保留給真的無車可調的死結）
    順序自動算（先取後放）；可跨區（救火優先於分區約束）。
    """
    cfg = config or get_config()
    fp = fleet_provider or get_fleet_provider()
    op = operator_provider or get_operator_provider()

    id_set = {str(s) for s in station_ids}
    stations = [r for r in dispatch_list if str(r.get("station_id")) in id_set]
    # 緊急出車的語意＝後台針對「特定出問題的站」強制出車，不該被「是否在自動推薦清單」限制。
    # 指定站不在清單時（緊急度不在前段、或站況剛恢復），用即時站況為它臨時評估一筆建議。
    found_ids = {str(s.get("station_id")) for s in stations}
    missing_ids = id_set - found_ids
    if missing_ids:
        extra = _emergency_recs_for(missing_ids, cfg)
        stations = stations + extra
    if not stations:
        return {"error": "指定站點查無即時站況或目前無需調度（可借可還皆正常）",
                "is_draft": True, "stations": []}

    # 起點座標：第一個站附近（用於就近找車）
    ref_lat = stations[0].get("lat")
    ref_lng = stations[0].get("lng")

    # 資源優先序：就近閒置一般車 → 預備車 standby（ADR-118/119）
    from db import vehicles_repo
    idle = fp.available_vehicles()
    idle_sorted = sorted(idle, key=lambda v: _dsp._haversine_km(
        ref_lat, ref_lng, v.get("current_lat"), v.get("current_lng")))
    standby = vehicles_repo.list_standby()
    resource_suggestion = {
        "nearest_idle": [v["vehicle_id"] for v in idle_sorted[:3]],
        "reserve_standby": [v["vehicle_id"] for v in standby[:3]],
    }

    if vehicle_id:
        veh = fp.get_vehicle(vehicle_id)
    else:
        veh = idle_sorted[0] if idle_sorted else (standby[0] if standby else None)

    # 緊急可跨區 → district 標「緊急跨區」（若站跨多區）
    dset = {s.get("district") for s in stations}
    district = stations[0].get("district") if len(dset) == 1 else "緊急跨區"

    # 人員：緊急也走優先序（就近/待命皆可），未指定帶第一名，候選供覆寫。
    seed_district = stations[0].get("district")
    assignable = op.assignable_operators(district=seed_district)
    depot_ops = op.depot_standby_operators()
    if operator_id:
        oper = op.get_operator(operator_id)
    else:
        oper = assignable[0] if assignable else (depot_ops[0] if depot_ops else None)
    escort = _resolve_escort(op, escort_id, oper)

    # 起點：優先用車的當前座標；車無座標（seed 車或未回報定位）時退回種子站附近，
    # 確保地圖仍畫得出路線（ADR-308）。
    draft = _make_draft(stations, veh, oper, district, cfg, now,
                        start_lat=(veh.get("current_lat") if veh else None) or ref_lat,
                        start_lng=(veh.get("current_lng") if veh else None) or ref_lng,
                        note="緊急出車（就近閒置車優先，預備車殿後；可跨區）",
                        escort=escort)
    draft["mode"] = "emergency"
    draft["resource_suggestion"] = resource_suggestion   # 供後台覆寫選擇
    draft["operator_candidates"] = _operator_candidates(assignable, depot_ops, seed_district)
    return draft


# ── 確認落地 ──
def confirm_trip(draft: dict, operator: str = "system") -> dict:
    """ADR-302：相容完整草稿；也接受 {draft_id, version} 確認。"""
    from core.dispatch_confirmation import confirm
    return confirm(draft, operator)
