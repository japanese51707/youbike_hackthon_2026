"""第四批（ADR-124）：最適化調整係數的生效接線——三態、護欄、可追溯、批次讀取。

係數乘在 ADR-115 動態目標水位的「預期流量」項；安全緩衝與 80/20 護欄不受影響。
決策邊界（ADR-004）：係數只改目標水位這一個量，不改觸發門檻與觸發結果。
"""

import pytest

from config_loader import get_config
from core.interfaces import MultiHorizonPrediction, PredictionInterval
from core.rule_engine import _dynamic_target_available, evaluate_station, generate_recommendations
from params import coefficients as coef
from params import commit_optimized, set_base


def _station(sid="S", available=3, total=40):
    return {"station_id": sid, "station_name": f"站{sid}", "district": "板橋區",
            "total_docks": total, "available_bikes": available,
            "available_docks": total - available,
            "usage_rate": available / total * 100, "lat": 25.0, "lng": 121.0}


def _multi(total, available, d60_lo, d60_hi, sid="S"):
    lo, hi = available + d60_lo, available + d60_hi
    mid = (lo + hi) / 2
    return MultiHorizonPrediction(station_id=sid, intervals=[PredictionInterval(
        predicted_available=max(0, min(total, mid)),
        lower_bound=max(0, min(total, lo)), upper_bound=max(0, min(total, hi)),
        horizon_minutes=60, raw_lower_bound=lo, raw_upper_bound=hi, raw_predicted=mid)])


def _set_mode(monkeypatch, mode, limits=None):
    cfg = get_config()
    monkeypatch.setitem(cfg["optimization"], "係數套用模式", mode)
    if limits:
        monkeypatch.setitem(cfg["optimization"], "係數上下限", limits)
    return cfg


def _store(sid, base=1.0, weekend=1.0):
    set_base(sid, {"target_level": 0.5})
    return commit_optimized(sid, {"base_outflow_coef": base, "env_coef_weekend": weekend},
                            reason="測試係數", operator="OP-003")


# ── 係數作用在預期流量上 ──

def test_coefficient_scales_expected_flow_only():
    """係數 1.2 → 後續最大流出 18 變 21.6；安全緩衝 4.8 不受影響。"""
    target = get_config()["target"]
    multi = _multi(40, 3, d60_lo=-18, d60_hi=0)
    base = _dynamic_target_available("補車", 40, 3, target, multi, 1.0)
    scaled = _dynamic_target_available("補車", 40, 3, target, multi, 1.2)
    assert abs(base - 22.8) < 0.5          # 4.8 + 18
    assert abs(scaled - 26.4) < 0.5        # 4.8 + 18*1.2，緩衝沒被乘
    assert abs((scaled - base) - 3.6) < 0.1


def test_coefficient_never_breaks_guardrails():
    """係數再大也不會突破 80/20 護欄。"""
    target = get_config()["target"]
    multi = _multi(40, 3, d60_lo=-60, d60_hi=0)
    assert _dynamic_target_available("補車", 40, 3, target, multi, 1.25) <= 40 * 0.8 + 1e-6


# ── 三態 ──

def test_off_mode_output_is_identical_to_unwired(monkeypatch):
    """off：完全不讀參數，輸出與未接線逐欄相同。"""
    _set_mode(monkeypatch, "off")
    _store("S", base=1.25)
    station, multi = _station(), _multi(40, 3, -18, 0)
    wired = generate_recommendations([station], predictor=_Pred(multi))[0]
    unwired = evaluate_station(dict(station), multi.intervals[0], multi=multi)
    # generate_recommendations 會多兩個預測狀態欄位，其餘必須逐欄相同
    extra_keys = {"prediction_status", "prediction_missing_features"}
    assert set(wired) - extra_keys == set(unwired)
    assert all(wired[k] == unwired[k] for k in set(wired) - extra_keys)
    assert not {"coefficient_mode", "shadow_quantity", "param_version"} & set(wired)


def test_shadow_mode_keeps_decision_and_reports_delta(monkeypatch):
    """shadow：採用基準值，但附上「若生效會變成多少」。"""
    _set_mode(monkeypatch, "shadow")
    _store("S", base=1.25)
    # 流出 8 台：基準 4.8+8=12.8 → 補 10 台；係數 1.25 → 4.8+10=14.8 → 補 12 台，
    # 兩者都在「每車容量 15」之下，差異才看得出來（否則會被上限蓋掉）
    station, multi = _station(), _multi(40, 3, -8, 0)
    baseline = evaluate_station(dict(station), multi.intervals[0], multi=multi)
    rec = generate_recommendations([station], predictor=_Pred(multi))[0]
    assert rec["coefficient_mode"] == "shadow"
    assert rec["quantity"] == baseline["quantity"]           # 決策不變
    assert rec["shadow_quantity"] > baseline["quantity"]     # 但看得到影子值
    assert rec["shadow_quantity_delta"] == rec["shadow_quantity"] - baseline["quantity"]
    assert rec["applied_coefficients"]["base_outflow_coef"] == 1.25


def test_on_mode_actually_changes_quantity(monkeypatch):
    """on：實際採用，補車量隨係數上升。"""
    _set_mode(monkeypatch, "on")
    _store("S", base=1.25)
    station, multi = _station(), _multi(40, 3, -8, 0)
    baseline = evaluate_station(dict(station), multi.intervals[0], multi=multi)
    rec = generate_recommendations([station], predictor=_Pred(multi))[0]
    assert rec["coefficient_mode"] == "on"
    assert rec["quantity"] > baseline["quantity"]
    assert rec["param_version"] is not None
    assert "shadow_quantity" not in rec


def test_mode_does_not_change_whether_it_triggers(monkeypatch):
    """決策邊界：係數只改數量，不改「要不要調度」與動作方向。"""
    station, multi = _station(available=20, total=40), _multi(40, 20, -2, 2)
    _set_mode(monkeypatch, "off")
    off = generate_recommendations([dict(station)], predictor=_Pred(multi))
    _set_mode(monkeypatch, "on")
    _store("S", base=1.25)
    on = generate_recommendations([dict(station)], predictor=_Pred(multi))
    assert [r["action"] for r in off] == [r["action"] for r in on]
    assert len(off) == len(on)


# ── 護欄與壞資料 ──

@pytest.mark.parametrize("stored,expected", [
    (3.0, 1.25),      # 超過上限 → 夾住
    (0.1, 0.8),       # 低於下限 → 夾住
    (1.1, 1.1),       # 範圍內 → 照用
])
def test_coefficient_clamped_to_limits(monkeypatch, stored, expected):
    cfg = _set_mode(monkeypatch, "on", limits=[0.8, 1.25])
    entry = {"version": "V1", "params": {"base_outflow_coef": stored}}
    assert coef.resolve(entry, is_dayoff=False, config=cfg)["value"] == expected


@pytest.mark.parametrize("bad", [None, "1.2", True, float("nan"), float("inf"), 0, -1.0])
def test_bad_coefficient_is_treated_as_one(monkeypatch, bad):
    """壞值一律視為 1.0（不影響），不得讓壞資料放大調度量。"""
    cfg = _set_mode(monkeypatch, "on")
    entry = {"version": "V1", "params": {"base_outflow_coef": bad}}
    assert coef.resolve(entry, is_dayoff=False, config=cfg)["value"] == 1.0


def test_weekend_coefficient_only_applies_on_dayoff(monkeypatch):
    cfg = _set_mode(monkeypatch, "on")
    entry = {"version": "V1", "params": {"base_outflow_coef": 1.1, "env_coef_weekend": 1.1}}
    weekday = coef.resolve(entry, is_dayoff=False, config=cfg)
    holiday = coef.resolve(entry, is_dayoff=True, config=cfg)
    assert weekday["value"] == 1.1 and "env_coef_weekend" not in weekday["applied"]
    assert holiday["value"] == 1.21 and holiday["applied"]["env_coef_weekend"] == 1.1


def test_station_without_params_is_unaffected(monkeypatch):
    """沒有參數版本的站：mode 有標、係數 1.0、數量與 off 相同。"""
    _set_mode(monkeypatch, "on")
    station, multi = _station(sid="NOPARAM"), _multi(40, 3, -18, 0)
    baseline = evaluate_station(dict(station), multi.intervals[0], multi=multi)
    rec = generate_recommendations([station], predictor=_Pred(multi))[0]
    assert rec["coefficient_mode"] == "on"
    assert rec["param_version"] is None
    assert rec["quantity"] == baseline["quantity"]


# ── 批次讀取 ──

def test_params_are_loaded_in_one_batch(monkeypatch):
    """1,000 站不可以打 1,000 次 DB。"""
    from db import params_repo
    for i in range(5):
        _store(f"B{i}", base=1.1)
    calls = {"n": 0}
    real = params_repo.get_active_many

    def counting(ids):
        calls["n"] += 1
        return real(ids)

    monkeypatch.setattr(params_repo, "get_active_many", counting)
    _set_mode(monkeypatch, "on")
    stations = [_station(sid=f"B{i}") for i in range(5)]
    multi = _multi(40, 3, -18, 0)
    generate_recommendations(stations, predictor=_Pred(multi))
    assert calls["n"] == 1


def test_off_mode_does_not_touch_the_database(monkeypatch):
    from db import params_repo
    def boom(ids):
        raise AssertionError("off 模式不應該讀參數")
    monkeypatch.setattr(params_repo, "get_active_many", boom)
    _set_mode(monkeypatch, "off")
    generate_recommendations([_station()], predictor=_Pred(_multi(40, 3, -18, 0)))


class _Pred:
    """固定回同一組多視野預測的假 predictor。"""

    def __init__(self, multi):
        self._multi = multi

    def predict_multi(self, station):
        return self._multi

    def predict(self, station, horizon_minutes=30):
        return self._multi.for_horizon(horizon_minutes) or self._multi.intervals[0]
