"""
規則引擎（core.rule_engine）— 動態觸發，吃預測區間
====================================================
職責（單一）：給定站點狀態 + 預測區間，判斷「要不要調度、補還是取、觸發原因」。
不做：預測（在 predictor）、排序/派發/資源限制（在 dispatcher）、緊急度分數（在 urgency）。

核心觸發邏輯（雙向保守，對齊 config 註解與 design §7）：
  - 防空站：吃預測「下界」lower_bound 當到達存量，若 ≤ 安全緩衝 → 補車
  - 防滿站：吃預測「上界」upper_bound，算可還位下界 =(總車柱−上界)，若 ≤ 安全緩衝 → 取車
  取兩側最悲觀的界觸發，避免點估計剛好落在安全區而漏觸發（NFR-1 可解釋性）。

  觸發靈敏度放大：
    調整後到達存量 = 當前存量 −（當前存量 − 下界）× 觸發靈敏度
    調整後可還位   =（總柱−當前存量）−（上界 − 當前存量）× 觸發靈敏度

降級：沒有預測區間時，退回用當前值 + 保底門檻（借用率高/低水位），並在依據標明（NFR-5）。

對外暴露：
    evaluate_station(station, prediction, config) -> Optional[dict]   # 單站判斷
    generate_recommendations(stations, config, predictor) -> list[dict]  # 全部站
輸出 dict 對齊 api_contract DispatchRecommendation（英文欄位），但不含
priority_score/priority_level（那由 dispatcher + urgency 補上）。
"""

from __future__ import annotations
from typing import Optional

from config_loader import get_config
from .interfaces import PredictionInterval, get_predictor


def _mk_rec(station: dict, action: str, quantity: int, reason: str,
            basis: str, at_arrival: float,
            urgency_tier: str = "normal", is_censored_demand: bool = False,
            breach_horizon_min=None, arrival_by_horizon=None) -> dict:
    """組一筆規則引擎輸出（未含優先級，dispatcher 再補）。"""
    return {
        "station_id": station.get("station_id", ""),
        "station_name": station.get("station_name", ""),
        "district": station.get("district", ""),
        "action": action,                    # "補車" / "取車"
        "quantity": int(quantity),
        "reason": reason,                    # 人看得懂的中文原因
        "basis": basis,                      # 判斷依據：截斷訊號/區間下界上界/保底門檻/降級
        "current_available": int(station.get("available_bikes", 0)),
        "predicted_at_arrival": round(float(at_arrival), 1),
        "lat": station.get("lat", 0.0),
        "lng": station.get("lng", 0.0),
        # ADR-111 三層判斷輸出（前端呈現用）：
        "urgency_tier": urgency_tier,               # censored(最高緊急截斷)/warning(警示)/normal
        "is_censored_demand": is_censored_demand,   # 需求被物理邊界壓抑(缺很凶/爆很凶)
        "breach_horizon_min": breach_horizon_min,   # 最早穿透邊界的視野(分鐘)，None=未穿透
        "arrival_by_horizon": arrival_by_horizon or {},  # 各視野到達存量(現況+Δ)，前端趨勢圖
        # ADR-109 機制 C：流量信心分級（high/mid/low，依訓練期周轉量）。
        # ★純標註，供 dispatcher 排序當「同分次要鍵」用。★不進觸發判斷（守 ADR-104）。
        "confidence_tier": station.get("confidence_tier", "mid"),
    }


def evaluate_station(
    station: dict,
    prediction: Optional[PredictionInterval],
    config: Optional[dict] = None,
    multi=None,
) -> Optional[dict]:
    """判斷單站是否需要調度。需要則回一筆建議 dict，否則回 None。

    prediction：觸發判斷用的單視野區間（依調度員響應時間挑的視野）。
    multi：（可選）MultiHorizonPrediction，用來補齊 4 視野 arrival_by_horizon（前端趨勢圖）
           並掃出「最早穿透邊界的視野」（ADR-107/111/113）。
    """
    cfg = config or get_config()
    trig = cfg["trigger"]
    target = cfg["target"]
    fleet = cfg["fleet"]

    total = float(station.get("total_docks", 0) or 0)
    if total <= 0:
        return None
    available = float(station.get("available_bikes", 0) or 0)
    buffer_bikes = float(trig["安全緩衝_台數"])
    sensitivity = float(trig["觸發靈敏度"])
    horizon = fleet["響應時間_分鐘"]
    usage_rate = available / total * 100

    action = None
    reason = None
    basis = None
    at_arrival = available
    urgency_tier = "normal"          # ADR-111 三層：censored / warning / normal
    is_censored_demand = False       # 需求被物理邊界壓抑
    breach_horizon_min = None        # 最早穿透邊界的視野（分鐘）

    if prediction is not None:
        # 防空：下界放大後的到達存量
        arrival = available - (available - prediction.lower_bound) * sensitivity
        # 防滿：可還位 = 空位；上界放大後的可還位下界
        docks_empty = total - available
        returnable_lower = docks_empty - (prediction.upper_bound - available) * sensitivity

        # ADR-111 截斷判斷（用 raw 照實值，不夾）：
        #   raw_lower < 0 → 到達存量穿透空站底（需求被壓抑的缺車，最高緊急補車）
        #   raw_upper > total → 到達存量穿透滿站頂（需求被壓抑的爆滿，最高緊急取車）
        raw_lo = prediction.raw_lower_bound
        raw_hi = prediction.raw_upper_bound

        if raw_lo is not None and raw_lo < 0:
            # 截斷層（最高緊急）：空站仍將流出
            action, basis = "補車", "截斷訊號（到達存量穿透空站底）"
            urgency_tier, is_censored_demand = "censored", True
            breach_horizon_min = prediction.horizon_minutes
            at_arrival = 0.0   # 物理實際到達 0（顯示用）
            reason = (f"現況 {available:.0f} 台，{horizon} 分鐘後預測仍將淨流出至 "
                      f"{raw_lo:.1f} 台（缺口約 {abs(raw_lo):.0f} 台）——需求被壓抑，最高緊急補車")
        elif raw_hi is not None and raw_hi > total:
            # 截斷層（最高緊急）：滿站仍將流入
            action, basis = "取車", "截斷訊號（到達存量穿透滿站頂）"
            urgency_tier, is_censored_demand = "censored", True
            breach_horizon_min = prediction.horizon_minutes
            at_arrival = total   # 物理實際到達滿（顯示用）
            reason = (f"現況 {available:.0f} 台，{horizon} 分鐘後預測仍將淨流入至 "
                      f"{raw_hi:.1f} 台（超出 {raw_hi - total:.0f} 台）——需求被壓抑，最高緊急取車")
        elif arrival <= buffer_bikes:
            # 警示層：快空（未穿透）
            action, basis, urgency_tier = "補車", "預測區間下界", "warning"
            at_arrival = arrival
            reason = (f"{horizon} 分鐘後預測到達存量最低 {arrival:.1f} 台，"
                      f"低於安全緩衝 {buffer_bikes:.0f} 台，即將空站")
        elif returnable_lower <= buffer_bikes:
            # 警示層：快滿（未穿透）
            action, basis, urgency_tier = "取車", "預測區間上界", "warning"
            at_arrival = total - returnable_lower
            reason = (f"{horizon} 分鐘後預測可還位最低 {returnable_lower:.1f} 個，"
                      f"低於安全緩衝 {buffer_bikes:.0f} 個，即將滿站")

    # 降級/保底：沒有預測，或預測未觸發但踩到保底水位（警示層）
    if action is None:
        if usage_rate < trig["低水位_借用率百分比"]:
            action, basis, urgency_tier = "補車", "保底門檻（借用率低水位）", "warning"
            at_arrival = available
            reason = (f"借用率 {usage_rate:.0f}% 低於保底門檻 "
                      f"{trig['低水位_借用率百分比']}%"
                      + ("（無預測，降級判斷）" if prediction is None else "（動態判斷未觸發）"))
        elif usage_rate > trig["高水位_借用率百分比"]:
            action, basis, urgency_tier = "取車", "保底門檻（借用率高水位）", "warning"
            at_arrival = available
            reason = (f"借用率 {usage_rate:.0f}% 高於保底門檻 "
                      f"{trig['高水位_借用率百分比']}%"
                      + ("（無預測，降級判斷）" if prediction is None else "（動態判斷未觸發）"))

    if action is None:
        return None

    # 數量：補/取到預設目標水位，單站不超過一車容量
    target_available = total * float(target["預設借用率百分比"]) / 100
    if action == "補車":
        quantity = max(1, round(target_available - available))
    else:
        quantity = max(1, round(available - target_available))
    quantity = int(min(quantity, fleet["每車容量"]))

    # 各視野到達存量（前端趨勢圖用）：有 multi 就補齊 4 視野；否則只填當前 horizon
    arrival_by_horizon = {}
    if multi is not None and getattr(multi, "intervals", None):
        for iv in sorted(multi.intervals, key=lambda x: x.horizon_minutes):
            arrival_by_horizon[str(iv.horizon_minutes)] = round(float(iv.raw_predicted), 1)
        # 掃最早穿透邊界的視野（ADR-111：raw 穿底/穿頂），比單一響應視野更完整
        earliest = None
        for iv in sorted(multi.intervals, key=lambda x: x.horizon_minutes):
            lo = iv.raw_lower_bound if iv.raw_lower_bound is not None else iv.lower_bound
            hi = iv.raw_upper_bound if iv.raw_upper_bound is not None else iv.upper_bound
            if (lo is not None and lo < 0) or (hi is not None and hi > total):
                earliest = iv.horizon_minutes
                break
        if earliest is not None:
            breach_horizon_min = earliest
    elif prediction is not None:
        arrival_by_horizon[str(prediction.horizon_minutes)] = round(
            float(prediction.raw_predicted), 1)

    return _mk_rec(station, action, quantity, reason, basis, at_arrival,
                   urgency_tier=urgency_tier, is_censored_demand=is_censored_demand,
                   breach_horizon_min=breach_horizon_min,
                   arrival_by_horizon=arrival_by_horizon)


def generate_recommendations(
    stations: list[dict],
    config: Optional[dict] = None,
    predictor=None,
) -> list[dict]:
    """對一批站點跑規則引擎，回傳所有「需要調度」的建議（未排序）。

    predictor 預設用 mock；A6 整合時傳入 B 的真實 predictor。
    排序、優先級、資源限制由 dispatcher 負責，不在這裡做。
    """
    cfg = config or get_config()
    pred = predictor or get_predictor()
    horizon = cfg["fleet"]["響應時間_分鐘"]

    out = []
    for st in stations:
        interval = None
        multi = None
        try:
            # 有 predict_multi（真實 LightGBM）就一次拿 4 視野；觸發用最接近響應時間的視野
            if hasattr(pred, "predict_multi"):
                multi = pred.predict_multi(st)
                interval = multi.for_horizon(horizon)
            else:
                interval = pred.predict(st, horizon)
        except NotImplementedError:
            interval = None   # 預測不可用 → 走降級
        rec = evaluate_station(st, interval, cfg, multi=multi)
        if rec is not None:
            out.append(rec)
    return out
