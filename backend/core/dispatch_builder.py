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
from . import dispatcher as _dsp
from .providers import get_fleet_provider, get_operator_provider


def _draft_id() -> str:
    return f"DRAFT-{_dt.datetime.now().strftime('%Y%m%d-%H%M%S-%f')[:-3]}"


def _fill_station_targets(stations: list[dict]) -> None:
    """每站補目標存量（ADR-115/117：主指令用目標值）與站級狀態。"""
    for s in stations:
        if "target_available" not in s:
            avail = float(s.get("current_available", 0))
            qty = float(s.get("quantity", 0))
            s["target_available"] = round(avail + qty if s.get("action") != "取車"
                                          else avail - qty, 0)
        s.setdefault("station_status", "pending")


def _make_draft(stations, vehicle, operator, district, cfg, now,
                start_lat=None, start_lng=None, note="") -> dict:
    """組一張草稿派工單（含路徑順序 + 預估）。不落地。"""
    ordered = _dsp._order_route(stations, start_lat, start_lng)
    _fill_station_targets(ordered)
    kpi = _dsp._estimate_trip_kpi(ordered, cfg, start_lat, start_lng)
    default_cap = _dsp._default_capacity(cfg)
    estimate = {
        **kpi,
        "total_quantity": sum(int(s.get("quantity", 0)) for s in ordered),
        "stop_count": len(ordered),
        "urgency_sum": round(sum(float(s.get("priority_score", 0)) for s in ordered), 1),
    }
    return {
        "draft_id": _draft_id(),
        "is_draft": True,                       # ★草稿：預覽用，未確認不落地
        "district": district,
        "shift": _dsp.current_shift(now),
        "mode": _dsp.current_mode(now),
        "stations": ordered,
        "assigned_vehicle": vehicle.get("vehicle_id") if vehicle else None,
        "assigned_operator": operator.get("operator_id") if operator else None,
        "vehicle_capacity": int(vehicle.get("max_capacity") or default_cap) if vehicle else None,
        "estimate": estimate,                   # 預估：距離/時間/載運量/緊急度加總（ADR-119）
        "note": note,
    }


# ── 入口 (a)：以車為起點 ──
def build_from_vehicle(
    vehicle_id: str, operator_id: str, dispatch_list: list[dict],
    district: Optional[str] = None, config=None, fleet_provider=None, now=None,
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
    oper = op.get_operator(operator_id)
    return _make_draft(stations, veh, oper, target_district, cfg, now,
                       start_lat=veh.get("current_lat"), start_lng=veh.get("current_lng"),
                       note=f"以車為起點（{'指定區' if district else '車所在區'}：{target_district}）")


# ── 入口 (b)：以站為起點 ──
def build_from_station(
    station_id: str, dispatch_list: list[dict], operator_id: Optional[str] = None,
    vehicle_id: Optional[str] = None, config=None, fleet_provider=None,
    operator_provider=None, now=None,
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
        return {"error": f"站點 {station_id} 不在需調度清單", "is_draft": True, "stations": []}
    district = seed.get("district")

    # 同區需調度站（含被點的站），依緊急度排序 → 切一趟
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

    veh = fp.get_vehicle(vehicle_id) if vehicle_id else (candidates[0] if candidates else None)
    cap = int(veh.get("max_capacity") or default_cap) if veh else default_cap
    trips = _dsp._pack_trips(pool, cap, max_stops)
    stations = trips[0] if trips else []

    # 人員：指定 → 用指定；否則該區閒置優先，無則總站待命
    if operator_id:
        oper = op.get_operator(operator_id)
    else:
        avail_ops = op.available_operators() + op.depot_standby_operators()
        oper = avail_ops[0] if avail_ops else None

    draft = _make_draft(stations, veh, oper, district, cfg, now,
                        start_lat=veh.get("current_lat") if veh else None,
                        start_lng=veh.get("current_lng") if veh else None,
                        note=f"以站為起點（{station_id} / {district}）")
    # 附車輛候選（分類供後台選；無指定車時特別有用）
    draft["vehicle_candidates"] = {
        "in_district": [v["vehicle_id"] for v in in_district],
        "nearby": [v["vehicle_id"] for v in nearby],
        "depot_standby": [v["vehicle_id"] for v in depot],
    }
    if not in_district and not nearby:
        draft["note"] += "｜該區與鄰近無閒置車，建議用總站待命車"
    return draft


# ── 入口 (c)：緊急出車 ──
def build_emergency(
    station_ids: list[str], dispatch_list: list[dict],
    vehicle_id: Optional[str] = None, operator_id: Optional[str] = None,
    config=None, fleet_provider=None, operator_provider=None, now=None,
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
    if not stations:
        return {"error": "指定站點不在需調度清單", "is_draft": True, "stations": []}

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

    oper = op.get_operator(operator_id) if operator_id else None
    if oper is None:
        pool = op.available_operators() + op.depot_standby_operators()
        oper = pool[0] if pool else None

    # 緊急可跨區 → district 標「緊急跨區」（若站跨多區）
    dset = {s.get("district") for s in stations}
    district = stations[0].get("district") if len(dset) == 1 else "緊急跨區"

    draft = _make_draft(stations, veh, oper, district, cfg, now,
                        start_lat=veh.get("current_lat") if veh else ref_lat,
                        start_lng=veh.get("current_lng") if veh else ref_lng,
                        note="緊急出車（就近閒置車優先，預備車殿後；可跨區）")
    draft["mode"] = "emergency"
    draft["resource_suggestion"] = resource_suggestion   # 供後台覆寫選擇
    return draft


# ── 確認落地 ──
def confirm_trip(draft: dict, operator: str = "system") -> dict:
    """ADR-119 確認：草稿 → 真正派工單（assigned，落地 DB）。人在迴圈唯一閘門。

    走 dispatcher._persist_trip（建 task + 回寫車/人 current_district + 認領標註）。
    確認記 audit 留痕。
    """
    if not draft or not draft.get("stations"):
        raise ValueError("空草稿不可確認")
    if not draft.get("assigned_vehicle") or not draft.get("assigned_operator"):
        raise ValueError("草稿缺車輛或人員，不可確認（請先指派）")

    # 組成 dispatcher trip 結構（給 _persist_trip）
    trip = {
        "trip_id": draft["draft_id"].replace("DRAFT", "TRIP"),
        "district": draft.get("district"),
        "shift": draft.get("shift"),
        "mode": draft.get("mode"),
        "stations": draft["stations"],
        "assigned_vehicle": draft["assigned_vehicle"],
        "assigned_operator": draft["assigned_operator"],
        "vehicle_capacity": draft.get("vehicle_capacity"),
    }
    _dsp._persist_trip(trip)

    from core.audit import get_audit_service
    get_audit_service().record(
        type="task_report", operator=operator,
        action=f"確認派工單 {trip['trip_id']}（{trip.get('mode')}，{len(trip['stations'])} 站）",
        reason=draft.get("note"))
    return {"trip_id": trip["trip_id"], "confirmed": True, "status": "assigned"}
