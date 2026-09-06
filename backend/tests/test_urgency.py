"""緊急度分數測試（ADR-112）：分層打底(censored>warning) + 五因素排序。"""

from core.interfaces import RealUrgencyCalculator, PredictionInterval


def _station(available, total, hour=8, sk="25.0_121.0"):
    return {"station_id": "S", "station_key": sk, "total_docks": total,
            "available_bikes": available, "hour": hour}


def _pred(lower, upper, horizon=30, raw_lower=None, raw_upper=None):
    return PredictionInterval(predicted_available=(lower + upper) / 2,
                              lower_bound=max(0, lower), upper_bound=upper,
                              horizon_minutes=horizon,
                              raw_lower_bound=raw_lower, raw_upper_bound=raw_upper)


def test_censored_always_higher_than_warning():
    """分層打底鐵則:任何 censored 站分數 > 任何 warning 站(不被人流等翻轉)。"""
    urg = RealUrgencyCalculator()
    # censored:空站穿透底(raw_lower<0)
    st_c = _station(0, 40)
    pred_c = _pred(0, 2, horizon=120, raw_lower=-3, raw_upper=2)  # 就算最晚視野
    score_c = urg.calc_urgency(st_c, pred_c, "補車")
    # warning:快空未穿透,但給最急條件(早視野)
    st_w = _station(3, 40)
    pred_w = _pred(1, 3, horizon=30, raw_lower=1, raw_upper=3)
    score_w = urg.calc_urgency(st_w, pred_w, "補車")
    assert score_c >= 70.0, f"censored應打底70+,得{score_c}"
    assert score_w < 70.0, f"warning應<70,得{score_w}"
    assert score_c > score_w, "censored必須>warning(分層打底)"


def test_earlier_breach_more_urgent():
    """同censored層:越早穿透越急(30分>120分)。"""
    urg = RealUrgencyCalculator()
    st = _station(0, 40)
    early = urg.calc_urgency(st, _pred(0, 2, 30, raw_lower=-3, raw_upper=2), "補車")
    late = urg.calc_urgency(st, _pred(0, 2, 120, raw_lower=-3, raw_upper=2), "補車")
    assert early > late, "早穿透應比晚穿透急"


def test_deeper_breach_more_urgent():
    """同censored層:穿透幅度越深越急(缺口大)。"""
    urg = RealUrgencyCalculator()
    st = _station(0, 40)
    deep = urg.calc_urgency(st, _pred(0, 2, 30, raw_lower=-15, raw_upper=2), "補車")
    shallow = urg.calc_urgency(st, _pred(0, 2, 30, raw_lower=-2, raw_upper=2), "補車")
    assert deep > shallow, "缺口深應比缺口淺急"


def test_score_in_range():
    """分數落在 0~100。"""
    urg = RealUrgencyCalculator()
    st = _station(0, 40)
    s = urg.calc_urgency(st, _pred(0, 2, 30, raw_lower=-20, raw_upper=2), "補車")
    assert 0 <= s <= 100
