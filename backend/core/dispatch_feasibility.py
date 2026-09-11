"""
路線可執行性評估（core.dispatch_feasibility）— ADR-123 / ADR-304
=================================================================
在「排好順序的一趟派工」上，檢查它在物理與制度上是否真的跑得完：

  1. 車輛初始載量（ADR-123 §1）：來源必須可追溯；未知或觀測過期 → 阻擋確認，不假設為零。
  2. 逐站載量守恆（§2）：依實際路線順序累加——取車 +q、補車 −q——全程須落在 [0, 容量]。
  3. 逐站到達時間與對應視野（§3）：累計行車 + 各站作業時間，每站取最接近其到達偏移的
     預測視野（30/60/90/120），不整趟共用同一視野；超出最長視野明確標記，不外推。
  4. 班別、剩餘工時與任務重疊（§4）：跨區是否為該班別允許、剩餘連續工時是否夠跑完本趟、
     本趟時間區間是否與該人／該車既有未結束任務重疊。

職責（單一）：只回「可不可行 + 為什麼不可行 + 逐站載量／到達計畫」。
不做：組單（dispatch_builder）、落地（dispatcher._persist_trip）、狀態機（task_manager）。
預覽與確認呼叫同一個 evaluate_feasibility，兩邊規則一致（ADR-304 §1）。

對外暴露：
    evaluate_feasibility(...) -> dict   # {load_plan, blocking_reasons, onboard_start, onboard_end}
    first_blocking_message(result) -> str | None
"""

from __future__ import annotations

import datetime as _dt
from typing import Optional

from config_loader import get_config

# ADR-107 多視野；逐站到達時間對應到其中最接近的一個
HORIZON_CHOICES = (30, 60, 90, 120)


def _reason(code: str, message: str, **extra) -> dict:
    return {"code": code, "message": message, **extra}


def _parse_ts(value) -> Optional[_dt.datetime]:
    if not value:
        return None
    try:
        return _dt.datetime.fromisoformat(str(value))
    except ValueError:
        return None


def _naive(moment: Optional[_dt.datetime]) -> Optional[_dt.datetime]:
    """統一去掉時區，讓 DB 的 naive 時間與帶時區的觀測時間可以相減。"""
    if moment is None:
        return None
    return moment.replace(tzinfo=None) if moment.tzinfo is not None else moment


def stop_quantity(stop: dict) -> int:
    """該站搬運量。ADR-123 §2：優先用主指令 target_available 與當下觀測存量推算。"""
    target = stop.get("target_available")
    current = stop.get("current_available")
    if target is not None and current is not None:
        try:
            return int(round(abs(float(target) - float(current))))
        except (TypeError, ValueError):
            pass
    for key in ("quantity", "est_quantity"):
        value = stop.get(key)
        if value is not None:
            try:
                return int(round(abs(float(value))))
            except (TypeError, ValueError):
                continue
    return 0


def onboard_start_of(vehicle: Optional[dict], cfg: dict, now: Optional[_dt.datetime] = None):
    """車輛出車時的車上台數。回 (值或 None, 阻擋原因 list)。

    ADR-123 §1：未知不得當成 0；觀測過期同樣不可用。
    """
    reasons: list[dict] = []
    if not vehicle:
        return None, [_reason("missing_vehicle", "尚未指定調度車，無法檢查載量")]
    raw = vehicle.get("onboard_bikes")
    if raw is None:
        return None, [_reason(
            "vehicle_onboard_unknown",
            f"車輛 {vehicle.get('vehicle_id')} 尚未回報車上台數，無法確認載量是否足夠；"
            f"請先回報後再確認派工")]
    try:
        onboard = int(raw)
    except (TypeError, ValueError):
        return None, [_reason("vehicle_onboard_unknown",
                              f"車輛 {vehicle.get('vehicle_id')} 的車上台數不是整數，視為未知")]
    if onboard < 0:
        return None, [_reason("vehicle_onboard_unknown",
                              f"車輛 {vehicle.get('vehicle_id')} 的車上台數為負值，視為未知")]

    max_age = int(cfg.get("fleet", {}).get("車上載量有效期_分鐘", 240))
    observed = _naive(_parse_ts(vehicle.get("onboard_observed_at")))
    if observed is None:
        reasons.append(_reason(
            "vehicle_onboard_stale",
            f"車輛 {vehicle.get('vehicle_id')} 的車上台數沒有觀測時間，無法確認是否仍有效"))
    else:
        age_min = (_naive(now or _dt.datetime.now()) - observed).total_seconds() / 60.0
        if age_min > max_age:
            reasons.append(_reason(
                "vehicle_onboard_stale",
                f"車輛 {vehicle.get('vehicle_id')} 的車上台數回報於 {age_min:.0f} 分鐘前，"
                f"超過有效期 {max_age} 分鐘，請重新回報",
                age_minutes=round(age_min, 1)))
    return onboard, reasons


def build_load_plan(
    stations: list[dict],
    vehicle: Optional[dict],
    cfg: dict,
    start_lat=None,
    start_lng=None,
    now: Optional[_dt.datetime] = None,
) -> tuple[list[dict], list[dict], Optional[int]]:
    """依既定順序算逐站到達時間、對應視野與車上載量。回 (plan, reasons, onboard_end)。"""
    from .dispatcher import _default_capacity, _haversine_km

    reasons: list[dict] = []
    travel = cfg.get("travel", {})
    speed = float(travel.get("平均車速_公里每小時", 20)) or 20.0
    per_stop = float(travel.get("每站搬運_分鐘", 5))
    capacity = int((vehicle or {}).get("max_capacity") or _default_capacity(cfg))

    onboard, load_reasons = onboard_start_of(vehicle, cfg, now)
    reasons.extend(load_reasons)
    known_load = onboard is not None
    running = onboard if known_load else 0

    plan: list[dict] = []
    cur_lat, cur_lng = start_lat, start_lng
    cumulative_km = 0.0
    for seq, stop in enumerate(stations, start=1):
        if cur_lat is not None:
            cumulative_km += _haversine_km(cur_lat, cur_lng, stop.get("lat"), stop.get("lng"))
        cur_lat, cur_lng = stop.get("lat"), stop.get("lng")

        # 到達偏移 = 到本站的行車時間 + 先前各站的作業時間
        arrival = cumulative_km / speed * 60.0 + per_stop * (seq - 1)
        horizon = min(HORIZON_CHOICES, key=lambda h: (abs(h - arrival), h))
        beyond = arrival > max(HORIZON_CHOICES)

        qty = stop_quantity(stop)
        action = stop.get("action")
        before = running
        if action == "取車":
            running = before + qty
        elif action == "補車":
            running = before - qty
        else:
            reasons.append(_reason(
                "invalid_action",
                f"站點 {stop.get('station_id')} 的動作 '{action}' 不是補車或取車"))

        entry = {
            "seq": seq,
            "station_id": stop.get("station_id"),
            "station_name": stop.get("station_name"),
            "action": action,
            "quantity": qty,
            "target_available": stop.get("target_available"),
            "arrival_offset_min": round(arrival, 1),
            "horizon_used_min": None if beyond else horizon,
            "beyond_forecast_horizon": bool(beyond),
            "onboard_before": before if known_load else None,
            "onboard_after": running if known_load else None,
        }
        plan.append(entry)

        if beyond:
            reasons.append(_reason(
                "stop_beyond_forecast_horizon",
                f"第 {seq} 站 {stop.get('station_id')} 預估 {arrival:.0f} 分鐘後才到達，"
                f"超出最長預測視野 {max(HORIZON_CHOICES)} 分鐘，不以外推預測派工",
                station_id=stop.get("station_id"), arrival_offset_min=round(arrival, 1)))
        if known_load and running > capacity:
            reasons.append(_reason(
                "load_exceeds_capacity",
                f"第 {seq} 站 {stop.get('station_id')} 取車後車上 {running} 台，"
                f"超過車輛容量 {capacity} 台",
                station_id=stop.get("station_id"), onboard_after=running, capacity=capacity))
        if known_load and running < 0:
            reasons.append(_reason(
                "load_below_zero",
                f"第 {seq} 站 {stop.get('station_id')} 需補 {qty} 台，"
                f"但到站時車上只有 {before} 台",
                station_id=stop.get("station_id"), onboard_before=before, quantity=qty))

    return plan, reasons, (running if known_load else None)


def _shift_reasons(stations: list[dict], mode: Optional[str],
                   now: Optional[_dt.datetime]) -> list[dict]:
    """ADR-116/119：早晚班不跨區；緊急模式可跨區（救火優先於分區約束）。"""
    from .shift import allow_cross_district, current_shift
    if mode == "emergency":
        return []
    districts = {s.get("district") for s in stations if s.get("district")}
    if len(districts) <= 1 or allow_cross_district(now):
        return []
    return [_reason(
        "cross_district_not_allowed",
        f"{current_shift(now) or '目前'}班不允許跨區，本趟涵蓋 {len(districts)} 個行政區："
        f"{'、'.join(sorted(districts))}", districts=sorted(districts))]


def _labor_reasons(operator: Optional[dict], est_total_min: float) -> list[dict]:
    """ADR-116 工時：剩餘連續工時是否足以跑完本趟（check_labor 正式接線）。"""
    from .shift import check_labor
    if not operator:
        return [_reason("missing_operator", "尚未指定執行人員，無法檢查工時")]
    worked = operator.get("today_work_minutes") or 0
    try:
        worked = float(worked)
    except (TypeError, ValueError):
        worked = 0.0
    status = check_labor(worked)
    if not status["can_dispatch"]:
        return [_reason("labor_hours_exceeded", status["message"], worked_minutes=worked)]
    cap = float(get_config().get("labor", {}).get("連續工時上限_分鐘", 240))
    if worked + est_total_min > cap:
        return [_reason(
            "labor_hours_exceeded",
            f"本趟預估 {est_total_min:.0f} 分鐘，加上已連續工作 {worked:.0f} 分鐘會超過"
            f"上限 {cap:.0f} 分鐘，請先安排休息或縮短本趟",
            worked_minutes=worked, est_total_min=round(est_total_min, 1))]
    return []


def _overlap_reasons(vehicle, operator, est_total_min: float,
                     now: Optional[_dt.datetime], exclude=None) -> list[dict]:
    """ADR-123 §4：本趟時間區間是否與該人／該車既有未結束任務重疊。

    既有任務缺少時間估計時採保守判定（視為重疊），不放行。
    """
    from .dispatch_guards import occupied_tasks
    reasons: list[dict] = []
    start = _naive(now or _dt.datetime.now())
    end = start + _dt.timedelta(minutes=max(est_total_min, 0.0))
    vid = (vehicle or {}).get("vehicle_id")
    oid = (operator or {}).get("operator_id")
    if not vid and not oid:
        return reasons
    for task in occupied_tasks(exclude):
        holders = []
        if vid and task.get("assigned_vehicle") == vid:
            holders.append(f"車輛 {vid}")
        if oid and task.get("assigned_operator") == oid:
            holders.append(f"人員 {oid}")
        if not holders:
            continue
        assigned = _naive(_parse_ts(task.get("assigned_at")))
        est = task.get("estimated_total_minutes")
        if assigned is None or est is None:
            reasons.append(_reason(
                "task_time_overlap",
                f"{'、'.join(holders)} 仍有未結束任務 {task['task_id']}（無時間估計，保守視為重疊）",
                task_id=task["task_id"]))
            continue
        other_end = assigned + _dt.timedelta(minutes=float(est))
        if start < other_end and assigned < end:
            reasons.append(_reason(
                "task_time_overlap",
                f"{'、'.join(holders)} 的任務 {task['task_id']} 預估執行到 "
                f"{other_end.isoformat(timespec='minutes')}，與本趟時間重疊",
                task_id=task["task_id"]))
    return reasons


def evaluate_feasibility(
    stations: list[dict],
    vehicle: Optional[dict] = None,
    operator: Optional[dict] = None,
    *,
    mode: Optional[str] = None,
    now: Optional[_dt.datetime] = None,
    config: Optional[dict] = None,
    start_lat=None,
    start_lng=None,
    est_total_min: Optional[float] = None,
    exclude_task: Optional[str] = None,
    check_resources: bool = True,
) -> dict:
    """評估一趟是否可執行。預覽與確認共用（ADR-304 §1）。

    check_resources=False 時只做載量／視野／班別檢查（用於尚未選定人車的預覽）。
    回傳 {load_plan, blocking_reasons, onboard_start, onboard_end, est_total_min}。
    """
    cfg = config or get_config()
    plan, reasons, onboard_end = build_load_plan(
        stations, vehicle, cfg, start_lat, start_lng, now)

    if est_total_min is None:
        per_stop = float(cfg.get("travel", {}).get("每站搬運_分鐘", 5))
        est_total_min = (plan[-1]["arrival_offset_min"] + per_stop) if plan else 0.0

    # 與 dispatch_guards.validate_stations 的總量規則同步，讓預覽與確認回報同一組原因
    capacity = int((vehicle or {}).get("max_capacity") or 0)
    if capacity:
        total = sum(stop_quantity(stop) for stop in stations)
        if total > capacity:
            reasons.append(_reason(
                "total_quantity_exceeds_capacity",
                "派工數量超過車輛容量，請重新預覽",
                total_quantity=total, capacity=capacity))

    reasons.extend(_shift_reasons(stations, mode, now))
    if check_resources:
        reasons.extend(_labor_reasons(operator, float(est_total_min)))
        reasons.extend(_overlap_reasons(vehicle, operator, float(est_total_min),
                                        now, exclude_task))

    onboard_start = plan[0]["onboard_before"] if plan else None
    return {
        "load_plan": plan,
        "blocking_reasons": reasons,
        "onboard_start": onboard_start,
        "onboard_end": onboard_end,
        "est_total_min": round(float(est_total_min), 1),
        "capacity": int((vehicle or {}).get("max_capacity") or 0) or None,
    }


def first_blocking_message(result: dict) -> Optional[str]:
    reasons = result.get("blocking_reasons") or []
    return reasons[0]["message"] if reasons else None
