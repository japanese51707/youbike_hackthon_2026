"""
調度器（core.dispatcher）— 排序 + 緊急度 + ③覆寫 + 資源限制
=============================================================
職責：把 rule_engine 產出的「需調度清單」轉成「排序後、受資源限制的最終建議」。
不做：觸發判斷（在 rule_engine）、預測（在 predictor）、任務狀態機（在 task_manager）。

排序邏輯（對齊既有決策）：
  1. ③即時覆寫站 = 「最前綴」：被覆寫的站一律排最前面（不改它的 urgency 分數，
     只是排序時強制置頂）。這是刻意的設計——覆寫是人為緊急介入，不污染分數體系。
  2. 其餘依 priority_score（緊急度 0~100）由高到低。

資源限制（config.fleet）：
  最終清單站數 ≤ min(每時段最大調度站數, 調度車數量 × 每趟最大站數)

緊急度來自 B 的 calc_urgency（先用 mock）；priority_level 依分數分級 high/medium/low。

對外暴露：
    build_dispatch_list(stations, config, predictor, urgency_calc, override_station_ids)
        -> list[dict]   # 對齊 api_contract DispatchRecommendation（含 priority_score/level）
    assign_by_district(dispatch_list, ...) -> list[dict]   # ADR-114 行政區任務指派（切趟+派車人）
"""

from __future__ import annotations
import datetime as _dt
from typing import Optional

from config_loader import get_config
from .rule_engine import generate_recommendations
from .interfaces import get_predictor, get_urgency_calculator
from .providers import get_fleet_provider, get_operator_provider
from .shift import current_shift, current_mode, allow_cross_district


def _level(score: float, cfg: dict) -> str:
    """緊急度分數 → 分級。門檻可在 config 覆寫，預設 high≥70 / medium≥40。"""
    band = cfg.get("priority_band", {})
    high = band.get("high_min", 70)
    medium = band.get("medium_min", 40)
    if score >= high:
        return "high"
    if score >= medium:
        return "medium"
    return "low"


def _rec_id(station_id: str) -> str:
    ts = _dt.datetime.now().strftime("%Y%m%d-%H%M")
    return f"REC-{ts}-{station_id}"


def build_dispatch_list(
    stations: list[dict],
    config: Optional[dict] = None,
    predictor=None,
    urgency_calc=None,
    override_station_ids: Optional[set[str]] = None,
    apply_capacity: bool = True,
) -> list[dict]:
    """產出最終排序（+ 可選資源受限）的調度建議清單。

    override_station_ids：③即時覆寫的站，排序時強制置頂（最前綴）。
    apply_capacity：True＝截到「一個時段車隊實際能處理的站數」（派工量能語意，預設）；
      False＝回全部需調度站的完整排序清單（供前端『需調度清單』顯示，不因量能截掉空/滿站）。
    """
    cfg = config or get_config()
    pred = predictor or get_predictor()
    urg = urgency_calc or get_urgency_calculator()
    overrides = override_station_ids or set()
    horizon = cfg["fleet"]["響應時間_分鐘"]

    # 1. 規則引擎產出需調度清單
    recs = generate_recommendations(stations, cfg, pred)

    # 2. 每筆補上緊急度分數 + 分級 + recommendation_id + 覆寫旗標
    station_by_id = {s.get("station_id"): s for s in stations}
    for r in recs:
        st = station_by_id.get(r["station_id"], {})
        try:
            interval = pred.predict(st, horizon)
        except NotImplementedError:
            interval = None
        if interval is not None:
            score = urg.calc_urgency(st, interval, r["action"])
        else:
            score = 50.0   # 無預測時的中性分數（降級）
        r["priority_score"] = score
        r["priority_level"] = _level(score, cfg)
        r["recommendation_id"] = _rec_id(r["station_id"])
        r["override_active"] = r["station_id"] in overrides

    # 3. 排序：覆寫站最前綴（override_active True 先），其餘依分數降序，
    #    同分時以流量信心分級 tie-break（ADR-109 機制 C：high 流量站優先）。
    #    ★confidence_tier 只當「同分次要排序鍵」，不改觸發、不改緊急度分數本身
    #      （守 ADR-104：流量是加分項，非調度觸發依據）。
    _tier_rank = {"high": 0, "mid": 1, "low": 2}
    recs.sort(key=lambda r: (not r["override_active"], -r["priority_score"],
                             _tier_rank.get(r.get("confidence_tier", "mid"), 1)))

    # 4. 資源限制：時段上限（僅在派工量能語意下套用；顯示用清單不截斷）
    if not apply_capacity:
        return recs
    fleet = cfg["fleet"]
    cap = min(int(fleet["每時段最大調度站數"]),
              int(fleet["調度車數量"]) * int(fleet["每趟最大站數"]))
    return recs[:cap]


# ────────────────────────────────────────────────────────────
# ADR-114：行政區任務指派（按 district 分組 + 載運量切趟，一趟不跨區不超載）
# ────────────────────────────────────────────────────────────

def _default_capacity(cfg: dict) -> int:
    """車輛主檔未指定 max_capacity 時的 fallback（config.fleet.每車容量，口徑統一 15）。"""
    return int(cfg.get("fleet", {}).get("每車容量", 15))


def _pack_trips(region_recs: list[dict], capacity: int, max_stops: int) -> list[list[dict]]:
    """把同一行政區的建議清單切成多趟：每趟總搬運量 ≤ capacity 且站數 ≤ max_stops。

    region_recs 已依緊急度排序（沿用 build_dispatch_list 的排序），貪婪裝箱：
    依序塞入當前趟，塞不下（超載或超站數）就開新趟。單站 quantity 超過整車容量時，
    該站仍單獨成一趟（up to capacity；剩餘量下輪再處理，這裡不拆量只保證不誤報超載）。
    """
    trips: list[list[dict]] = []
    cur: list[dict] = []
    cur_load = 0
    for r in region_recs:
        q = int(r.get("quantity", 0))
        # 開新趟條件：加入後超載，或已達每趟站數上限
        if cur and (cur_load + q > capacity or len(cur) >= max_stops):
            trips.append(cur)
            cur, cur_load = [], 0
        cur.append(r)
        cur_load += q
    if cur:
        trips.append(cur)
    return trips


def _haversine_km(lat1, lng1, lat2, lng2) -> float:
    """兩點球面距離（公里）。座標缺失回 0。"""
    import math
    try:
        lat1, lng1, lat2, lng2 = float(lat1), float(lng1), float(lat2), float(lng2)
    except (TypeError, ValueError):
        return 0.0
    if 0 in (lat1, lng1, lat2, lng2):
        return 0.0
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return r * 2 * math.asin(math.sqrt(a))


def _order_route(stations: list[dict], start_lat=None, start_lng=None) -> list[dict]:
    """趟內路徑順序（啟發式，ADR-117）：先取車（滿站，action=取車）再放車（空站，action=補車），
    各組內用最近鄰串接（從起點或前一站找最近的下一站）。

    理由：一台車先到滿站把車收上來，再到空站放下去，一趟解決兩邊；組內就近跑減少空駛。
    """
    collect = [s for s in stations if s.get("action") == "取車"]
    supply = [s for s in stations if s.get("action") != "取車"]

    def nearest_chain(group, lat, lng):
        remaining = list(group)
        ordered = []
        cur_lat, cur_lng = lat, lng
        while remaining:
            if cur_lat is None:
                nxt = remaining[0]   # 無起點座標 → 保持原序（已按緊急度）
            else:
                nxt = min(remaining, key=lambda s: _haversine_km(
                    cur_lat, cur_lng, s.get("lat"), s.get("lng")))
            ordered.append(nxt)
            remaining.remove(nxt)
            cur_lat, cur_lng = nxt.get("lat"), nxt.get("lng")
        return ordered, cur_lat, cur_lng

    coll_ordered, lat2, lng2 = nearest_chain(collect, start_lat, start_lng)
    supp_ordered, _, _ = nearest_chain(supply, lat2 if collect else start_lat,
                                       lng2 if collect else start_lng)
    return coll_ordered + supp_ordered


def _estimate_trip_kpi(ordered_stations: list[dict], cfg: dict,
                       start_lat=None, start_lng=None) -> dict:
    """估一趟的交通/作業/總時間與距離（ADR-117 KPI）。"""
    travel = cfg.get("travel", {})
    speed = float(travel.get("平均車速_公里每小時", 20)) or 20
    per_stop = float(travel.get("每站搬運_分鐘", 5))

    dist = 0.0
    cur_lat, cur_lng = start_lat, start_lng
    for s in ordered_stations:
        if cur_lat is not None:
            dist += _haversine_km(cur_lat, cur_lng, s.get("lat"), s.get("lng"))
        cur_lat, cur_lng = s.get("lat"), s.get("lng")
    travel_min = round(dist / speed * 60, 1)
    work_min = round(per_stop * len(ordered_stations), 1)
    return {
        "est_distance_km": round(dist, 2),
        "est_travel_min": travel_min,
        "est_work_min": work_min,
        "est_total_min": round(travel_min + work_min, 1),
    }


def assign_by_district(
    dispatch_list: list[dict],
    config: Optional[dict] = None,
    fleet_provider=None,
    operator_provider=None,
    persist: bool = False,
    now=None,
) -> list[dict]:
    """ADR-114：把排序好的調度建議清單，按行政區組裝成「不跨區、不超載」的派工單。

    流程：
      1. 依 district 分組（每組已保有原緊急度排序）。
      2. 每組依「可用車輛載運量」切趟（_pack_trips）：一趟站點同屬一區、總量 ≤ 車容量、站數 ≤ 每趟上限。
      3. 依序把每趟指派給一台可用車 + 一名可用調度員（不夠則該趟標記 unassigned 待後續）。
      4. persist=True 時：建立 task（帶 district/assigned_vehicle）、回寫車/人的 current_district。

    回傳 trip（派工單）list，每筆：
      { trip_id, district, stations:[rec...], total_quantity, stop_count,
        assigned_vehicle, assigned_operator, vehicle_capacity, status }

    ★不改 build_dispatch_list（誰要調度/排序）；本函式只做「分給哪台車/誰、怎麼切趟」。
    """
    cfg = config or get_config()
    fp = fleet_provider or get_fleet_provider()
    op = operator_provider or get_operator_provider()
    max_stops = int(cfg.get("fleet", {}).get("每趟最大站數", 3))
    default_cap = _default_capacity(cfg)

    # 1. 分組：早/晚班按行政區（一趟不跨區，ADR-114）；大夜班可跨區則全市一組（ADR-116/117）。
    cross_ok = allow_cross_district(now)
    by_district: dict[str, list[dict]] = {}
    if cross_ok:
        # 大夜跨區大宗復原：全市不分區，讓 _pack_trips 跨區配對缺車↔滿車、裝滿再跑
        by_district["全市跨區"] = list(dispatch_list)
    else:
        for r in dispatch_list:
            d = r.get("district") or "未知區"
            by_district.setdefault(d, []).append(r)

    # 可用資源池（車依載運量由大到小，讓大單先有大車；人力平均分配）
    vehicles = sorted(fp.available_vehicles(),
                      key=lambda v: -int(v.get("max_capacity") or default_cap))
    operators = op.available_operators()
    vi = oi = 0

    trips_out: list[dict] = []
    trip_seq = 0
    # 行政區依「該區最高緊急度」排序，先處理最急的區
    ordered_districts = sorted(
        by_district.items(),
        key=lambda kv: -max((x.get("priority_score", 0) for x in kv[1]), default=0))

    for district, region_recs in ordered_districts:
        # 切趟用「當前可用車的載運量」；沒有可用車時用 fallback 預設（仍能切趟供顯示/待指派）
        cap_for_pack = (int(vehicles[vi].get("max_capacity") or default_cap)
                        if vi < len(vehicles) else default_cap)
        trips = _pack_trips(region_recs, cap_for_pack, max_stops)

        for trip_stations in trips:
            trip_seq += 1
            total_q = sum(int(s.get("quantity", 0)) for s in trip_stations)
            veh = vehicles[vi] if vi < len(vehicles) else None
            oper = operators[oi] if oi < len(operators) else None
            # 車輛當前位置為路徑起點（有的話）
            start_lat = veh.get("current_lat") if veh else None
            start_lng = veh.get("current_lng") if veh else None
            # 趟內路徑順序（先取後放最近鄰，ADR-117）
            ordered = _order_route(trip_stations, start_lat, start_lng)
            kpi = _estimate_trip_kpi(ordered, cfg, start_lat, start_lng)
            # 每站帶「目標存量」為主指令（ADR-115/117：呈現用目標值非增減量）
            for s in ordered:
                s.setdefault("target_available",
                             round(float(s.get("current_available", 0)) + float(s.get("quantity", 0))
                                   if s.get("action") != "取車"
                                   else float(s.get("current_available", 0)) - float(s.get("quantity", 0)), 0))
                s.setdefault("station_status", "pending")   # 站級狀態（Task4 用）
            trip = {
                "trip_id": f"TRIP-{_dt.datetime.now().strftime('%Y%m%d-%H%M%S')}-{trip_seq:03d}",
                "district": district,                       # 一趟不跨區（ADR-114；大夜跨區另走 ADR-117 分支）
                "shift": current_shift(now),                # ADR-116 班別
                "mode": current_mode(now),                  # ADR-117 排程模式
                "stations": ordered,
                "total_quantity": total_q,
                "stop_count": len(ordered),
                "assigned_vehicle": veh.get("vehicle_id") if veh else None,
                "assigned_operator": oper.get("operator_id") if oper else None,
                "vehicle_capacity": int(veh.get("max_capacity") or default_cap) if veh else None,
                "status": "assigned" if (veh and oper) else "unassigned",
                **kpi,
            }
            trips_out.append(trip)
            if veh:
                vi += 1
            if oper:
                oi += 1

            if persist and veh and oper:
                _persist_trip(trip)

    return trips_out


def assign_peak_shuttle(
    dispatch_list: list[dict],
    config: Optional[dict] = None,
    fleet_provider=None,
    operator_provider=None,
    now=None,
) -> list[dict]:
    """ADR-117 尖峰折返組排程：同區「狂流出站（缺車）↔ 狂流入站（滿車）」配成折返組，
    一台車綁定一組，在其間來回循環（收滿→放空→再收），追求尖峰高頻週轉。

    折返組組法（啟發式）：
      每個行政區內，把取車站（滿站，供給來源）與補車站（空站，需求）配成一組——
      以「一個取車站 + 依緊急度與鄰近取數個補車站」湊成一組（組總搬運量參考車容量）。
      早/晚尖峰各區的組數 ≈ 該區需車數（見 dispatch_ops_analysis）。

    回傳 trip（mode=peak_shuttle），每筆帶 shuttle_cluster（該組站清單）。
    ★不自動派工，供後台佈署尖峰折返車（人在迴圈）。
    """
    cfg = config or get_config()
    fp = fleet_provider or get_fleet_provider()
    op = operator_provider or get_operator_provider()
    default_cap = _default_capacity(cfg)
    max_stops = int(cfg.get("fleet", {}).get("每趟最大站數", 3))

    # 按行政區分組（折返不跨區）
    by_district: dict[str, list[dict]] = {}
    for r in dispatch_list:
        by_district.setdefault(r.get("district") or "未知區", []).append(r)

    vehicles = sorted(fp.available_vehicles(),
                      key=lambda v: -int(v.get("max_capacity") or default_cap))
    operators = op.available_operators()
    vi = oi = 0

    clusters_out: list[dict] = []
    seq = 0
    for district, recs in by_district.items():
        collect = sorted([r for r in recs if r.get("action") == "取車"],
                         key=lambda r: -float(r.get("priority_score", 0)))
        supply = sorted([r for r in recs if r.get("action") != "取車"],
                        key=lambda r: -float(r.get("priority_score", 0)))
        if not collect and not supply:
            continue

        # 組折返組：以取車站為核心，配就近/高緊急的補車站；無取車站時純補車組（車需外部帶車進來）
        cap = (int(vehicles[vi].get("max_capacity") or default_cap)
               if vi < len(vehicles) else default_cap)
        # 每組 = 1 取車站 + 依鄰近串接數個補車站（站數 ≤ max_stops、量 ≤ 車容量）
        cores = collect or [None]   # 無滿站時 core=None（純缺車組）
        supply_pool = list(supply)
        for core in cores:
            seq += 1
            group = []
            load = 0
            if core is not None:
                group.append(core)
            # 就近取補車站塞滿這組
            cur_lat = core.get("lat") if core else (supply_pool[0].get("lat") if supply_pool else None)
            cur_lng = core.get("lng") if core else (supply_pool[0].get("lng") if supply_pool else None)
            while supply_pool and len(group) < max_stops:
                nxt = min(supply_pool, key=lambda s: _haversine_km(
                    cur_lat, cur_lng, s.get("lat"), s.get("lng")))
                if load + int(nxt.get("quantity", 0)) > cap and group:
                    break
                group.append(nxt)
                load += int(nxt.get("quantity", 0))
                supply_pool.remove(nxt)
                cur_lat, cur_lng = nxt.get("lat"), nxt.get("lng")
            if not group:
                continue

            veh = vehicles[vi] if vi < len(vehicles) else None
            oper = operators[oi] if oi < len(operators) else None
            for s in group:
                s.setdefault("target_available",
                             round(float(s.get("current_available", 0)) + float(s.get("quantity", 0))
                                   if s.get("action") != "取車"
                                   else float(s.get("current_available", 0)) - float(s.get("quantity", 0)), 0))
                s.setdefault("station_status", "pending")
            clusters_out.append({
                "trip_id": f"SHUTTLE-{_dt.datetime.now().strftime('%Y%m%d-%H%M%S')}-{seq:03d}",
                "district": district,
                "shift": current_shift(now),
                "mode": "peak_shuttle",
                "shuttle_cluster": [s.get("station_id") for s in group],   # 折返組站清單
                "stations": group,
                "assigned_vehicle": veh.get("vehicle_id") if veh else None,
                "assigned_operator": oper.get("operator_id") if oper else None,
                "vehicle_capacity": int(veh.get("max_capacity") or default_cap) if veh else None,
                "status": "assigned" if (veh and oper) else "unassigned",
                "note": "尖峰折返：車綁此組站來回循環（收滿放空），非一趟性任務",
            })
            if veh:
                vi += 1
            if oper:
                oi += 1
        # 剩餘沒配到取車站的補車站，仍成組（供給靠外部調入或大站週轉）
        while supply_pool:
            seq += 1
            group = supply_pool[:max_stops]
            supply_pool = supply_pool[max_stops:]
            veh = vehicles[vi] if vi < len(vehicles) else None
            oper = operators[oi] if oi < len(operators) else None
            for s in group:
                s.setdefault("target_available",
                             round(float(s.get("current_available", 0)) + float(s.get("quantity", 0)), 0))
                s.setdefault("station_status", "pending")
            clusters_out.append({
                "trip_id": f"SHUTTLE-{_dt.datetime.now().strftime('%Y%m%d-%H%M%S')}-{seq:03d}",
                "district": district, "shift": current_shift(now), "mode": "peak_shuttle",
                "shuttle_cluster": [s.get("station_id") for s in group],
                "stations": group,
                "assigned_vehicle": veh.get("vehicle_id") if veh else None,
                "assigned_operator": oper.get("operator_id") if oper else None,
                "vehicle_capacity": int(veh.get("max_capacity") or default_cap) if veh else None,
                "status": "assigned" if (veh and oper) else "unassigned",
                "note": "尖峰折返（純補車組）：需外部調入車源",
            })
            if veh:
                vi += 1
            if oper:
                oi += 1

    return clusters_out


def _persist_trip(trip: dict) -> None:
    from db.connection import transaction
    with transaction():
        _persist_trip_atomic(trip)


def _persist_trip_atomic(trip: dict) -> None:
    """落地一張派工單：建 task（帶 district/assigned_vehicle）+ 回寫車/人的 current_district。"""
    from db import vehicles_repo, operators_repo, tasks_repo
    from core.dispatch_guards import validate_resources, validate_stations
    from core.dispatch_errors import DispatchConflict
    task_id = trip["trip_id"]
    if tasks_repo.exists(task_id):
        raise DispatchConflict("任務 ID 已存在，請使用草稿確認收據重送")
    vehicle, operator, escort = validate_resources(trip)
    validate_stations(trip["stations"], vehicle["max_capacity"])
    # ADR-123/304：確認時以當下資源重跑與預覽相同的可行性評估（載量守恆／逐站視野／班別工時／重疊）
    from core.dispatch_feasibility import evaluate_feasibility, first_blocking_message
    feasibility = evaluate_feasibility(
        trip["stations"], vehicle, operator, mode=trip.get("mode"),
        start_lat=vehicle.get("current_lat"), start_lng=vehicle.get("current_lng"),
        est_total_min=trip.get("est_total_min") or (trip.get("estimate") or {}).get("est_total_min"),
        exclude_task=task_id)
    blocked = first_blocking_message(feasibility)
    if blocked:
        raise DispatchConflict(blocked)
    plan_by_station = {str(e["station_id"]): e for e in feasibility["load_plan"]}
    # route 存「站物件」（含 target_available/station_status/認領人），供 task_execution 逐站操作（ADR-117）
    route = []
    for s in trip["stations"]:
        route.append({
            "station_id": s.get("station_id"),
            "station_name": s.get("station_name"),
            "district": s.get("district"),
            "action": s.get("action"),
            "target_available": s.get("target_available"),
            # ADR-123：與可行性計畫同一口徑的搬運量（結案推算載量要用同一個數）
            "est_quantity": plan_by_station.get(str(s.get("station_id")), {}).get(
                "quantity", s.get("quantity")),
            "station_status": "pending",
            "total_docks": s.get("total_docks"),
            # ADR-310 自動偵測基準：組單當下該站可借車數（判斷變化方向/量的 baseline）
            "current_available": s.get("current_available"),
            "claimed_by": trip["assigned_operator"],   # 認領標註（ADR-117）
            "lat": s.get("lat"), "lng": s.get("lng"),
            # ADR-123：逐站到達偏移／所用預測視野／到站後車上載量（確認時算定，供執行端對照）
            "arrival_offset_min": plan_by_station.get(str(s.get("station_id")), {}).get(
                "arrival_offset_min"),
            "horizon_used_min": plan_by_station.get(str(s.get("station_id")), {}).get(
                "horizon_used_min"),
            "onboard_after": plan_by_station.get(str(s.get("station_id")), {}).get("onboard_after"),
        })
    task = {
        "task_id": task_id,
        "task_type": "emergency" if trip.get("mode") == "emergency" else "normal",
        "vehicle_return_status": vehicle["status"],
        "resources_released": 0,
        "task_status": "assigned",
        "assigned_operator": trip["assigned_operator"],
        "assigned_escort": trip.get("assigned_escort"),   # ADR-308 隨車（可選）
        "district": trip["district"],
        "assigned_vehicle": trip["assigned_vehicle"],
        "route": route,
        "assigned_at": _dt.datetime.now().isoformat(timespec="seconds"),
        "estimated_total_minutes": feasibility.get("est_total_min"),
        "onboard_start": feasibility.get("onboard_start"),
        "onboard_planned_end": feasibility.get("onboard_end"),
    }
    tasks_repo.insert(task)
    # 回寫車/人的 current_district（動態，ADR-114）
    vehicles_repo.assign_district(trip["assigned_vehicle"], trip["district"], task_id)
    operators_repo.assign_district(trip["assigned_operator"], trip["district"], task_id)
    # ADR-308 隨車人員：一併轉 busy + 綁同一任務/行政區（釋放時對稱下工）
    if trip.get("assigned_escort"):
        operators_repo.assign_district(trip["assigned_escort"], trip["district"], task_id)


def suggest_next_trip(
    vehicle_id: str,
    dispatch_list: list[dict],
    config: Optional[dict] = None,
    fleet_provider=None,
    now=None,
    top_k: int = 10,
) -> dict:
    """ADR-117 離峰滾動排程：車完成一趟後，依「該車當前位置」給下一趟建議（不自動派工）。

    系統做的是「輔助計算」：對每個待調度站算「綜合評分 = 緊急度高、距離近、單位成本低者優先」，
    排序後回傳候選清單，由後台管理人員拍板（steering §6 人在迴圈）。

    綜合評分（可解釋的啟發式）：score = priority_score − 距離懲罰。
      距離懲罰 = 距離(km) × 每公里成本權重（config `dispatch_next.每公里扣分`，預設 2 分/km）。
    早/晚班只在該車當前行政區內找候選（不跨區，ADR-116）；大夜班可跨區。

    回傳：{ vehicle_id, from_district, cross_district_allowed, candidates:[{station+score+距離}...] }
    """
    cfg = config or get_config()
    fp = fleet_provider or get_fleet_provider()
    veh = fp.get_vehicle(vehicle_id)
    if veh is None:
        return {"vehicle_id": vehicle_id, "error": "找不到該車", "candidates": []}

    cur_lat = veh.get("current_lat")
    cur_lng = veh.get("current_lng")
    from_district = veh.get("current_district")
    cross_ok = allow_cross_district(now)

    km_penalty = float(cfg.get("dispatch_next", {}).get("每公里扣分", 2.0))
    cands = []
    for r in dispatch_list:
        # 非大夜（不可跨區）時，只考慮同區候選
        if not cross_ok and from_district and r.get("district") != from_district:
            continue
        dist = _haversine_km(cur_lat, cur_lng, r.get("lat"), r.get("lng"))
        score = float(r.get("priority_score", 0)) - dist * km_penalty
        cands.append({
            "station_id": r.get("station_id"),
            "station_name": r.get("station_name"),
            "district": r.get("district"),
            "action": r.get("action"),
            "target_available": r.get("target_available"),
            "priority_score": r.get("priority_score"),
            "distance_km": round(dist, 2),
            "suggest_score": round(score, 1),
        })
    cands.sort(key=lambda c: -c["suggest_score"])
    return {
        "vehicle_id": vehicle_id,
        "from_district": from_district,
        "cross_district_allowed": cross_ok,
        "candidates": cands[:top_k],   # 建議清單，由後台拍板（非自動派工）
    }
