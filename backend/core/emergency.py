"""
緊急救火與死結警報（core.emergency）— ADR-118
==============================================
題目宗旨：縮短「供需失衡→機關獲知→介入」的時間差。常態排程（ADR-117）處理可預測失衡；
突發死結（大站爆滿/空車、在途車來不及）走本模組的緊急救火：偵測 → 警報 → 派 standby 預備車。

不歸大數據預測管，歸「緊急警報」管（ADR-118）。

職責（單一）：偵測死結 + 產生救火警報 + 派待命預備車（可跨區）。
不做：常態排程（dispatcher）、預測（predictor）、警示推播機制本身（借用 alert_service）。

觸發條件（config emergency，可調）：
  某行政區同時 ≥ 死結站數門檻 個「精華大站（柱數 ≥ 大站柱數門檻）」處於死結
  （100% 滿或 0% 空），且現有在途車抵達均 > 在途門檻分鐘 → 觸發救火。
  （死結持續分鐘：需持續才算，此處以「當下快照 + 傳入的持續狀態」判定，
    連續 N 分鐘的追蹤由呼叫端/排程週期維護，避免瞬時波動誤觸。）

對外暴露：
    detect_deadlocks(stations) -> list[dict]           # 找出死結大站（分區彙整）
    check_and_dispatch_reserve(stations, in_transit_eta_min, now, persist) -> dict
        # 偵測 → 產生 critical 救火警報 → 派 standby（可跨區）
"""

from __future__ import annotations
import datetime as _dt
from typing import Optional

from config_loader import get_config


def _is_deadlock(st: dict) -> Optional[str]:
    """站點是否死結。回 'full'（滿站無位還）/ 'empty'（空站無車借）/ None。"""
    total = float(st.get("total_docks", 0) or 0)
    if total <= 0:
        return None
    bikes = float(st.get("available_bikes", 0) or 0)
    docks = float(st.get("available_docks", total - bikes) or 0)
    if bikes <= 0:
        return "empty"
    if docks <= 0:
        return "full"
    return None


def detect_deadlocks(stations: list[dict], config: Optional[dict] = None) -> list[dict]:
    """找出「精華大站」中處於死結的站，依行政區彙整。

    回傳 list[{district, count, stations:[...]}]，只含達站數門檻的行政區（依 count 降序）。
    """
    cfg = (config or get_config()).get("emergency", {})
    big_threshold = float(cfg.get("大站柱數門檻", 40))
    n_threshold = int(cfg.get("死結站數門檻", 3))

    by_district: dict[str, list[dict]] = {}
    for st in stations:
        if float(st.get("total_docks", 0) or 0) < big_threshold:
            continue   # 只看精華大站
        dl = _is_deadlock(st)
        if dl is None:
            continue
        d = st.get("district") or "未知區"
        by_district.setdefault(d, []).append({
            "station_id": st.get("station_id"),
            "station_name": st.get("station_name"),
            "deadlock_type": dl,
            "total_docks": st.get("total_docks"),
        })

    out = [{"district": d, "count": len(v), "stations": v}
           for d, v in by_district.items() if len(v) >= n_threshold]
    out.sort(key=lambda x: -x["count"])
    return out


def reserve_bikes_for_station(
    station: dict, peak_turnover: float, config: Optional[dict] = None,
) -> dict:
    """ADR-118 駐點預備車量：該站尖峰要備的總量 = 尖峰週轉量，扣掉柱點上現有車 = 實際要放的預備車。

    - peak_turnover：該站尖峰（早+晚）歷史週轉量（來自 dispatch_ops_analysis）。
    - 實際預備車 = max(0, 尖峰週轉量 − 站上現有車)，避免備過頭（owner：含站上現有車）。
    - 再夾「不超過該站空位」（現場放得下）：預備車 ≤ 總柱 − 現有車。
    回傳：{ station_id, peak_turnover, on_site_bikes, reserve_bikes, capped_by_space }
    """
    total = float(station.get("total_docks", 0) or 0)
    on_site = float(station.get("available_bikes", 0) or 0)
    raw = max(0.0, peak_turnover - on_site)         # 扣站上車，不過量
    free_space = max(0.0, total - on_site)          # 現場放得下的空間
    reserve = min(raw, free_space)
    return {
        "station_id": station.get("station_id"),
        "station_name": station.get("station_name"),
        "peak_turnover": round(peak_turnover, 1),
        "on_site_bikes": int(on_site),
        "reserve_bikes": int(round(reserve)),
        "capped_by_space": raw > free_space,        # 是否被現場空間夾住
    }


def plan_stationed_reserves(
    stations: list[dict], turnover_by_station: dict, top_n: int = 15,
    config: Optional[dict] = None,
) -> list[dict]:
    """ADR-118 規劃駐點預備車：對尖峰週轉量最高的 top_n 站算各站要放的預備車。

    turnover_by_station：{station_id: 尖峰週轉量}（來自 dispatch_ops_analysis 離線統計）。
    回傳依預備車量降序的清單，供後台佈署駐點人員 + 預備車。
    """
    st_by_id = {s.get("station_id"): s for s in stations}
    # 依週轉量取 top_n 候選站
    ranked = sorted(turnover_by_station.items(), key=lambda kv: -kv[1])[:top_n]
    out = []
    for sid, turnover in ranked:
        st = st_by_id.get(sid)
        if st is None:
            continue
        out.append(reserve_bikes_for_station(st, turnover, config))
    out.sort(key=lambda x: -x["reserve_bikes"])
    return out


def check_and_dispatch_reserve(
    stations: list[dict],
    in_transit_eta_min: Optional[float] = None,
    config: Optional[dict] = None,
    now=None,
    persist: bool = False,
) -> dict:
    """ADR-118 緊急救火主流程：偵測死結 → 若在途車來不及 → 產生 critical 警報 + 派 standby。

    in_transit_eta_min：現有在途調度車抵達該區的預估時間（分鐘）。None 視為無在途車（等同來不及）。
    persist=True 時真的把 standby 車轉 active（demo/測試可設 False 只回報建議）。

    回傳：{ triggered, deadlock_districts, dispatched:[{district, vehicle_id}...], alerts:[...] }
    """
    cfg = config or get_config()
    em = cfg.get("emergency", {})
    eta_threshold = float(em.get("在途門檻分鐘", 30))

    deadlocks = detect_deadlocks(stations, cfg)
    # 在途車若能在門檻內趕到，就不必動用 standby（常態車處理即可）
    in_time = in_transit_eta_min is not None and in_transit_eta_min <= eta_threshold
    if not deadlocks or in_time:
        return {"triggered": False, "deadlock_districts": deadlocks,
                "dispatched": [], "alerts": []}

    from core.alert_service import get_alert_service
    from db import vehicles_repo
    alert_svc = get_alert_service()

    dispatched = []
    alerts = []
    standby = vehicles_repo.list_standby()   # 待命預備車池（救火可跨區，不限該區）
    si = 0
    for dl in deadlocks:
        district = dl["district"]
        # 產生 critical 救火警報（統一走 alert_service，前端跳紅字、webhook 推機關）
        first = dl["stations"][0]
        a = alert_svc._create_alert(
            {"station_id": first["station_id"], "station_name": first["station_name"],
             "district": district, "status": first["deadlock_type"]},
            level="critical",
            rec={"action": "緊急救火補/取車", "quantity": 0,
                 "priority_level": "high",
                 "reason": (f"【死結救火】{district} 有 {dl['count']} 個大站死結"
                            f"（{'/'.join(s['station_name'] for s in dl['stations'][:3])}），"
                            f"在途車來不及（>{eta_threshold:.0f}分），派待命預備車")})
        alerts.append(a)

        # 派一台 standby 預備車去救火（可跨區，ADR-116/118）
        if si < len(standby):
            veh = standby[si]
            si += 1
            if persist:
                task_id = f"RESCUE-{_dt.datetime.now().strftime('%Y%m%d-%H%M%S')}-{district}"
                vehicles_repo.activate_reserve(veh["vehicle_id"], district, task_id)
            dispatched.append({"district": district, "vehicle_id": veh["vehicle_id"]})

    return {
        "triggered": True,
        "deadlock_districts": deadlocks,
        "dispatched": dispatched,
        "alerts": alerts,
        "reserve_exhausted": si >= len(standby) and len(deadlocks) > len(dispatched),
    }
