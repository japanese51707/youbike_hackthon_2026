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
) -> list[dict]:
    """產出最終排序 + 資源受限的調度建議清單。

    override_station_ids：③即時覆寫的站，排序時強制置頂（最前綴）。
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

    # 4. 資源限制：時段上限
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


def assign_by_district(
    dispatch_list: list[dict],
    config: Optional[dict] = None,
    fleet_provider=None,
    operator_provider=None,
    persist: bool = False,
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

    # 1. 按行政區分組（保留原排序）
    by_district: dict[str, list[dict]] = {}
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
            trip = {
                "trip_id": f"TRIP-{_dt.datetime.now().strftime('%Y%m%d-%H%M')}-{trip_seq:03d}",
                "district": district,                       # 一趟不跨區（ADR-114）
                "stations": trip_stations,
                "total_quantity": total_q,
                "stop_count": len(trip_stations),
                "assigned_vehicle": veh.get("vehicle_id") if veh else None,
                "assigned_operator": oper.get("operator_id") if oper else None,
                "vehicle_capacity": int(veh.get("max_capacity") or default_cap) if veh else None,
                "status": "assigned" if (veh and oper) else "unassigned",
            }
            trips_out.append(trip)
            if veh:
                vi += 1
            if oper:
                oi += 1

            if persist and veh and oper:
                _persist_trip(trip)

    return trips_out


def _persist_trip(trip: dict) -> None:
    """落地一張派工單：建 task（帶 district/assigned_vehicle）+ 回寫車/人的 current_district。"""
    from db import vehicles_repo, operators_repo, tasks_repo
    task_id = trip["trip_id"]
    task = {
        "task_id": task_id,
        "task_type": "normal",
        "task_status": "assigned",
        "assigned_operator": trip["assigned_operator"],
        "district": trip["district"],
        "assigned_vehicle": trip["assigned_vehicle"],
        "route": [s.get("station_id") for s in trip["stations"]],
        "assigned_at": _dt.datetime.now().isoformat(timespec="seconds"),
    }
    if not tasks_repo.exists(task_id):
        tasks_repo.insert(task)
    # 回寫車/人的 current_district（動態，ADR-114）
    vehicles_repo.assign_district(trip["assigned_vehicle"], trip["district"], task_id)
    operators_repo.assign_district(trip["assigned_operator"], trip["district"], task_id)
