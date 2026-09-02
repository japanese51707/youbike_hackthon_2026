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
