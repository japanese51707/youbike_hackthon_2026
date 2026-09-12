"""規則引擎測試（A2）：固定雙向觸發（下界防空/上界防滿）與 basis 依據欄位。"""

from core.rule_engine import evaluate_station
from core.interfaces import PredictionInterval
from config_loader import get_config


def _station(available, total, usage):
    return {"station_id": "S", "station_name": "測試站", "district": "測試區",
            "total_docks": total, "available_bikes": available,
            "usage_rate": usage, "lat": 25.0, "lng": 121.0}


def test_trigger_supply_by_lower_bound():
    """快空站：預測下界低 → 觸發補車，basis=預測區間下界。"""
    cfg = get_config()
    st = _station(available=3, total=40, usage=7.5)
    pred = PredictionInterval(predicted_available=1, lower_bound=0, upper_bound=3, horizon_minutes=30)
    rec = evaluate_station(st, pred, cfg)
    assert rec is not None
    assert rec["action"] == "補車"
    assert rec["basis"] == "預測區間下界"
    assert "空站" in rec["reason"]


def test_trigger_collect_by_upper_bound():
    """快滿站：預測上界高 → 觸發取車，basis=預測區間上界。"""
    cfg = get_config()
    st = _station(available=37, total=40, usage=92.5)
    pred = PredictionInterval(predicted_available=39, lower_bound=37, upper_bound=40, horizon_minutes=30)
    rec = evaluate_station(st, pred, cfg)
    assert rec is not None
    assert rec["action"] == "取車"
    assert rec["basis"] == "預測區間上界"
    assert "滿站" in rec["reason"]


def test_normal_station_no_trigger():
    """正常站：預測落在安全區 → 不觸發。"""
    cfg = get_config()
    st = _station(available=20, total=40, usage=50)
    pred = PredictionInterval(predicted_available=20, lower_bound=16, upper_bound=24, horizon_minutes=30)
    assert evaluate_station(st, pred, cfg) is None


def test_degradation_basis_when_no_prediction():
    """無預測時走保底門檻，basis 明確標明降級（NFR-5 失敗要看得見）。"""
    cfg = get_config()
    st = _station(available=2, total=40, usage=5)   # 借用率低於保底門檻
    rec = evaluate_station(st, None, cfg)
    assert rec is not None
    assert "保底門檻" in rec["basis"]
    assert rec["action"] == "補車"
    assert rec["urgency_tier"] == "warning"
    assert rec["is_censored_demand"] is False


def test_empty_station_without_prediction_is_censored():
    """無預測但已空：仍屬截斷層，前端緊急調度才看得到。"""
    cfg = get_config()
    rec = evaluate_station(_station(available=0, total=40, usage=0), None, cfg)
    assert rec is not None
    assert rec["action"] == "補車"
    assert rec["urgency_tier"] == "censored"
    assert rec["is_censored_demand"] is True


def test_full_station_without_prediction_is_censored():
    """無預測但已滿：仍屬截斷層。"""
    cfg = get_config()
    rec = evaluate_station(_station(available=40, total=40, usage=100), None, cfg)
    assert rec is not None
    assert rec["action"] == "取車"
    assert rec["urgency_tier"] == "censored"
    assert rec["is_censored_demand"] is True


# ── ADR-111 截斷訊號三層判斷測試 ──

def test_censored_empty_still_outflow():
    """截斷層：空站(現況0)預測仍將淨流出(raw_lower<0穿透空站底) → 最高緊急補車。"""
    cfg = get_config()
    st = _station(available=0, total=40, usage=0)
    # raw 照實給穿透值(到達存量 -5，缺口5台)；夾過值顯示 0
    pred = PredictionInterval(predicted_available=0, lower_bound=0, upper_bound=2,
                              horizon_minutes=30,
                              raw_lower_bound=-5, raw_upper_bound=2, raw_predicted=-3)
    rec = evaluate_station(st, pred, cfg)
    assert rec is not None
    assert rec["action"] == "補車"
    assert rec["urgency_tier"] == "censored"
    assert rec["is_censored_demand"] is True
    assert rec["breach_horizon_min"] == 30
    assert "壓抑" in rec["reason"]


def test_censored_full_still_inflow():
    """截斷層：滿站(現況接近總柱)預測仍將淨流入(raw_upper>total穿透滿站頂) → 最高緊急取車。"""
    cfg = get_config()
    st = _station(available=40, total=40, usage=100)
    pred = PredictionInterval(predicted_available=40, lower_bound=38, upper_bound=40,
                              horizon_minutes=30,
                              raw_lower_bound=38, raw_upper_bound=46, raw_predicted=43)
    rec = evaluate_station(st, pred, cfg)
    assert rec is not None
    assert rec["action"] == "取車"
    assert rec["urgency_tier"] == "censored"
    assert rec["is_censored_demand"] is True


def test_warning_near_empty_not_breached():
    """警示層：快空但未穿透邊界(raw_lower≥0) → warning，非censored。"""
    cfg = get_config()
    st = _station(available=3, total=40, usage=7.5)
    pred = PredictionInterval(predicted_available=1, lower_bound=0, upper_bound=3,
                              horizon_minutes=30,
                              raw_lower_bound=0, raw_upper_bound=3, raw_predicted=1)
    rec = evaluate_station(st, pred, cfg)
    assert rec is not None
    assert rec["action"] == "補車"
    assert rec["urgency_tier"] == "warning"
    assert rec["is_censored_demand"] is False


def test_empty_without_prediction_is_high_on_dispatch_list():
    """無預測的已空站必須進 high，否則調度面板緊急分頁會是空的。"""
    from core.dispatcher import build_dispatch_list

    class _NoPred:
        def predict(self, station, horizon_minutes=30):
            raise NotImplementedError("test")

    stations = [
        {**_station(available=0, total=40, usage=0), "station_id": "EMPTY",
         "available_docks": 40, "status": "empty"},
        {**_station(available=2, total=40, usage=5), "station_id": "LOW",
         "available_docks": 38, "status": "low"},
    ]
    recs = build_dispatch_list(stations, get_config(), predictor=_NoPred(), apply_capacity=False)
    by_id = {r["station_id"]: r for r in recs}
    assert by_id["EMPTY"]["urgency_tier"] == "censored"
    assert by_id["EMPTY"]["priority_level"] == "high"
    assert by_id["EMPTY"]["priority_score"] >= 70
    assert by_id["LOW"]["urgency_tier"] == "warning"
    assert by_id["LOW"]["priority_level"] == "medium"


def test_normal_tier_no_censor():
    """正常層：安全區 → 不觸發(None)，不應標截斷。"""
    cfg = get_config()
    st = _station(available=20, total=40, usage=50)
    pred = PredictionInterval(predicted_available=20, lower_bound=16, upper_bound=24,
                              horizon_minutes=30,
                              raw_lower_bound=16, raw_upper_bound=24, raw_predicted=20)
    assert evaluate_station(st, pred, cfg) is None
