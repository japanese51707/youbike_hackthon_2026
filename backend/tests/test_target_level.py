"""
ADR-115 動態目標水位測試
========================
驗證補/抽車量「補到幾台」由固定 50% 改為動態（補到能吸收後續 60 分最悲觀淨流量的水位，
夾 80/20 護欄）。補車看 P10（悲觀流出）、抽車看 P90（樂觀流入）。

用假的 MultiHorizonPrediction 餵不同的 60 分累積 Δ，驗證：
  - 尖峰（大流出）補足量
  - 離峰（小流出）補少或不補
  - 晚間（大流入）抽車量
  - 80/20 護欄封頂/兜底
  - 比例緩衝隨站大小縮放
  - 無 multi 時降級退回固定 50%
  - quantity ≤ 車容量
"""
from __future__ import annotations

from core.rule_engine import evaluate_station, _dynamic_target_available
from core.interfaces import PredictionInterval, MultiHorizonPrediction
from config_loader import get_config


def _station(available, total, usage):
    return {"station_id": "S", "station_name": "測試站", "district": "測試區",
            "total_docks": total, "available_bikes": available,
            "usage_rate": usage, "lat": 25.0, "lng": 121.0}


def _iv(horizon, raw_lo, raw_hi, total, available):
    """組單視野區間：raw 照實，夾過值夾 [0,total]。predicted 取中點。"""
    mid = (raw_lo + raw_hi) / 2
    return PredictionInterval(
        predicted_available=max(0, min(total, mid)),
        lower_bound=max(0, min(total, raw_lo)),
        upper_bound=max(0, min(total, raw_hi)),
        horizon_minutes=horizon,
        raw_lower_bound=raw_lo, raw_upper_bound=raw_hi, raw_predicted=mid)


def _multi(total, available, d60_lo, d60_hi):
    """組多視野：只給 60 分視野的累積 Δ（到達存量 = 現況 + Δ）。"""
    lo60 = available + d60_lo
    hi60 = available + d60_hi
    return MultiHorizonPrediction(station_id="S", intervals=[_iv(60, lo60, hi60, total, available)])


# ── 直接測 _dynamic_target_available（目標存量）──

def test_target_peak_supply_high_water():
    """捷運站早尖峰：60分P10累積Δ=-18(狂流出) → 目標存量高(補得多)。"""
    cfg = get_config()["target"]
    total, avail = 40, 3
    multi = _multi(total, avail, d60_lo=-18, d60_hi=0)   # P10 流出18
    tgt = _dynamic_target_available("補車", total, avail, cfg, multi)
    # 安全底線 40*0.12=4.8 + 18 = 22.8，夾[8,32] → 22.8
    assert abs(tgt - 22.8) < 0.5


def test_target_offpeak_low_water_falls_back_to_middle():
    """離峰：60分P10累積Δ=-3(小流出) → 目標存量低，接近安全底線(回落到中間概念)。"""
    cfg = get_config()["target"]
    total, avail = 40, 15
    multi = _multi(total, avail, d60_lo=-3, d60_hi=5)
    tgt = _dynamic_target_available("補車", total, avail, cfg, multi)
    # 4.8 + 3 = 7.8，夾[8,32] → 兜底到 8（現況15已高於 → evaluate 不補，見下）
    assert abs(tgt - 8.0) < 0.5


def test_target_evening_collect():
    """住宅區晚上：60分P90累積Δ=+12(狂流入) → 目標存量壓低(抽車)。"""
    cfg = get_config()["target"]
    total, avail = 40, 35
    multi = _multi(total, avail, d60_lo=-2, d60_hi=12)   # P90 流入12
    tgt = _dynamic_target_available("取車", total, avail, cfg, multi)
    # 目標空位 = 4.8 + 12 = 16.8 → 目標存量 = 40-16.8 = 23.2，夾[8,32] → 23.2
    assert abs(tgt - 23.2) < 0.5


def test_target_guardrail_caps_at_80pct():
    """護欄封頂：極端大流出也不補超過 80%。"""
    cfg = get_config()["target"]
    total, avail = 40, 2
    multi = _multi(total, avail, d60_lo=-100, d60_hi=0)   # 誇張流出
    tgt = _dynamic_target_available("補車", total, avail, cfg, multi)
    assert abs(tgt - 40 * 0.80) < 0.01   # 封在 32


def test_ratio_buffer_scales_with_station_size():
    """比例緩衝隨站大小縮放：大站底線遠大於小站(解決固定2台大站風險)。"""
    cfg = get_config()["target"]
    # 無後續流出時，補車目標存量 = 安全底線 = 柱數*12%（夾下限後）
    big = _dynamic_target_available("補車", 60, 0, cfg, _multi(60, 0, -0, 5))
    small = _dynamic_target_available("補車", 20, 0, cfg, _multi(20, 0, -0, 5))
    # 大站底線 7.2 → 夾下限[12,48] → 12；小站底線 2.4 → 夾下限[4,16] → 4
    assert big > small
    assert abs(big - 12.0) < 0.5    # 60*0.20 下限
    assert abs(small - 4.0) < 0.5   # 20*0.20 下限


def test_degrade_no_multi_falls_back_to_fixed():
    """無 multi → 降級退回固定 預設借用率百分比(50%)。"""
    cfg = get_config()["target"]
    tgt = _dynamic_target_available("補車", 40, 3, cfg, multi=None)
    assert abs(tgt - 20.0) < 0.01   # 40*50%


# ── 端到端 evaluate_station（含觸發 + 動態量）──

def test_evaluate_peak_supply_quantity():
    """尖峰快空站端到端：觸發補車，量 = 動態目標(22.8) - 現況(3) ≈ 20，且 ≤ 車容量。"""
    cfg = get_config()
    total, avail = 40, 3
    # 觸發：下界低 → 補車；multi 給 60 分大流出
    multi = _multi(total, avail, d60_lo=-18, d60_hi=0)
    pred = multi.for_horizon(30) if False else _iv(30, 0, 3, total, avail)
    rec = evaluate_station(_station(avail, total, 7.5), pred, cfg, multi=multi)
    assert rec is not None
    assert rec["action"] == "補車"
    assert rec["quantity"] <= cfg["fleet"]["每車容量"]
    assert rec["quantity"] >= 15    # 補足量（22.8-3≈20，受車容量夾）


def test_evaluate_quantity_never_exceeds_vehicle_capacity():
    """量永遠不超過單車容量（ADR-114 上限）。"""
    cfg = get_config()
    total, avail = 100, 5
    multi = _multi(total, avail, d60_lo=-90, d60_hi=0)
    pred = _iv(30, 0, 3, total, avail)
    rec = evaluate_station(_station(avail, total, 5), pred, cfg, multi=multi)
    assert rec is not None
    assert rec["quantity"] == cfg["fleet"]["每車容量"]
