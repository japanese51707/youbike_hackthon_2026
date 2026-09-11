"""第四批（ADR-126）：未受供給限制的需求估計——只輸出、不進決策。

空站觀測到的 Δ=0 是被物理邊界壓抑的假值（ADR-105），所以後台看到的「缺 N 台」在空站上
一定是低估的。這裡用該站「沒空的時候」同時段的實際流出量當估計，並嚴格限制它只出現在輸出。
"""

from datetime import datetime, timedelta, timezone

import pytest

from config_loader import get_config
from prediction.serving_features import unconstrained_demand

TAIPEI = timezone(timedelta(hours=8))
OBSERVED = datetime(2026, 6, 15, 8, 10, tzinfo=TAIPEI)      # 平日早上 8:10 → slot 16


def _bundle(out=6.0, inflow=4.0, n=40, dayoff=0):
    return {
        "dayoff": {"20260615": dayoff},
        "stations": {"25.01_121.46": {"demand": {f"{dayoff}:16": {"out": out, "in": inflow, "n": n}}}},
    }


def _station(available, docks, total=20):
    return {"station_id": "S", "lat": 25.01, "lng": 121.46,
            "available_bikes": available, "available_docks": docks, "total_docks": total,
            "observed_at": OBSERVED.isoformat()}


@pytest.fixture(autouse=True)
def _enable(monkeypatch):
    monkeypatch.setitem(get_config()["prediction"], "輸出未受限需求估計", True)


def test_empty_station_gets_the_uncensored_outflow():
    """空站要補車：估計＝該站沒空時同時段的流出中位數。"""
    value, basis = unconstrained_demand(_station(0, 20), _bundle(out=6.0), "補車")
    assert (value, basis) == (6.0, "station_slot_uncensored")


def test_full_station_gets_the_uncensored_inflow():
    value, basis = unconstrained_demand(_station(20, 0), _bundle(inflow=4.0), "取車")
    assert (value, basis) == (4.0, "station_slot_uncensored")


def test_healthy_station_has_nothing_to_estimate():
    """站況正常時觀測本身沒被壓抑，不需要也不該給估計。"""
    value, basis = unconstrained_demand(_station(10, 10), _bundle(), "補車")
    assert value is None and basis == "not_censored"


def test_insufficient_samples_returns_null_not_a_number():
    value, basis = unconstrained_demand(_station(0, 20), _bundle(n=3), "補車")
    assert value is None and basis == "insufficient_samples"


def test_missing_bundle_section_is_not_an_error():
    """舊模型包沒有這個區塊 → 回 null，不拋錯（ADR-126 相容性）。"""
    value, basis = unconstrained_demand(_station(0, 20), {"dayoff": {"20260615": 0}, "stations": {}}, "補車")
    assert value is None and basis == "insufficient_samples"


def test_flag_off_produces_nothing(monkeypatch):
    monkeypatch.setitem(get_config()["prediction"], "輸出未受限需求估計", False)
    assert unconstrained_demand(_station(0, 20), _bundle(), "補車") == (None, None)


def test_dayoff_and_weekday_use_different_slots():
    """放假型態不同 → 查不同的統計格；查不到不得回退到別的格。"""
    weekday_bundle = _bundle(dayoff=0)
    value, basis = unconstrained_demand(_station(0, 20), weekday_bundle, "補車")
    assert value == 6.0
    holiday_bundle = {"dayoff": {"20260615": 1}, "stations": weekday_bundle["stations"]}
    value, basis = unconstrained_demand(_station(0, 20), holiday_bundle, "補車")
    assert value is None and basis == "insufficient_samples"


# ── 決策邊界：估計不得影響任何調度決定（ADR-126 第 1 點）──

def test_estimate_never_changes_the_dispatch_decision(monkeypatch):
    from core.rule_engine import generate_recommendations

    class _Pred:
        """回固定預測；需求估計可切換，用來證明它不影響任何決策欄位。"""

        def __init__(self, demand):
            self._demand = demand

        def predict(self, station, horizon_minutes=30):
            raise NotImplementedError            # 走降級路徑，讓結果完全可預期

        def unconstrained_demand(self, station, action):
            return self._demand

    station = {"station_id": "S", "station_name": "空站", "district": "板橋區",
               "total_docks": 20, "available_bikes": 0, "available_docks": 20,
               "usage_rate": 0.0, "lat": 25.01, "lng": 121.46,
               "observed_at": OBSERVED.isoformat()}
    decision_keys = ("action", "quantity", "predicted_at_arrival", "urgency_tier",
                     "basis", "reason", "is_censored_demand")

    without = generate_recommendations([dict(station)], predictor=_Pred((None, None)))[0]
    with_estimate = generate_recommendations([dict(station)], predictor=_Pred((9.0, "station_slot_uncensored")))[0]

    assert with_estimate["unconstrained_demand"] == 9.0
    assert with_estimate["demand_basis"] == "station_slot_uncensored"
    assert "unconstrained_demand" not in without
    for key in decision_keys:
        assert without[key] == with_estimate[key], key


def test_broken_estimator_does_not_break_dispatch():
    """估計器壞掉時，調度照跑——它只是附加資訊，不能拖垮主流程。"""
    from core.rule_engine import generate_recommendations

    class _Boom:
        def predict(self, station, horizon_minutes=30):
            raise NotImplementedError

        def unconstrained_demand(self, station, action):
            raise RuntimeError("bundle 壞了")

    station = {"station_id": "S", "station_name": "空站", "district": "板橋區",
               "total_docks": 20, "available_bikes": 0, "available_docks": 20,
               "usage_rate": 0.0, "lat": 25.01, "lng": 121.46}
    recs = generate_recommendations([station], predictor=_Boom())
    assert len(recs) == 1 and recs[0]["action"] == "補車"
    assert "unconstrained_demand" not in recs[0]
