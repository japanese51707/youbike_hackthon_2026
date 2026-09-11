"""第四批：conformal 校準的數學保證、分組退回與成套檢查（離線量測庫）。

ADR-127 已否決把 conformal 接到上線路徑：430 萬列實測偏移全為 0。
本檔保留 CQR 的數學測試，因為 tools/fullscale_eval/conformal_check.py 仍用這個庫做離線量測；
最後一項測試則守住「上線不得有校準接線」這條界線。
"""

import json

import numpy as np
import pytest

from prediction import conformal


def _synthetic(n=4000, seed=0):
    """造一組「區間刻意太窄」的資料：名目 80% 但實際只涵蓋約 50%。"""
    rng = np.random.default_rng(seed)
    y = rng.normal(0, 3, n)
    lower = np.full(n, -2.0)      # 真實 80% 區間約 ±3.84，這裡只給 ±2
    upper = np.full(n, 2.0)
    return y, lower, upper


def test_conformity_score_definition():
    y = np.array([0.0, 5.0, -5.0])
    lo = np.array([-1.0, -1.0, -1.0])
    hi = np.array([1.0, 1.0, 1.0])
    # 落在區間內 → 負值；超出上界 → y-hi；低於下界 → lo-y
    assert list(conformal.conformity(y, lo, hi)) == [-1.0, 4.0, 4.0]


def test_calibration_restores_nominal_coverage():
    """CQR 的核心保證：校準後覆蓋率 ≥ 名目（這裡 80%）。"""
    y, lo, hi = _synthetic()
    before = float(((y >= lo) & (y <= hi)).mean())
    assert before < 0.6, "測試資料應該是刻意太窄的區間"
    entry = conformal.fit_horizon(y, lo, hi, np.zeros_like(y), np.zeros_like(y),
                                  alpha=0.2, buckets=1, min_samples=0)
    offset = entry["global_offset"]
    after = float(((y >= lo - offset) & (y <= hi + offset)).mean())
    assert after >= 0.80, f"校準後覆蓋率 {after:.3f} 應 ≥ 名目 0.80"


def test_offset_is_never_negative():
    """區間本來就夠寬時，偏移為 0——不得反過來把區間縮窄。"""
    rng = np.random.default_rng(1)
    y = rng.normal(0, 1, 2000)
    lo, hi = np.full(2000, -10.0), np.full(2000, 10.0)
    entry = conformal.fit_horizon(y, lo, hi, np.zeros_like(y), np.zeros_like(y),
                                  alpha=0.2, buckets=1, min_samples=0)
    assert entry["global_offset"] == 0.0


def test_grouped_offsets_differ_by_magnitude():
    """條件覆蓋率：預測量級越大、實際變異越大，該桶需要越大的偏移。

    這正是全量評估看到的形狀——整體覆蓋率合格，但「站點真的在動」的列被蓋不住。
    """
    rng = np.random.default_rng(2)
    n = 8000
    magnitude = rng.uniform(0, 6, n)                    # 連續量級，避免分位數邊界退化
    y = rng.normal(0, 1, n) * (0.3 + magnitude)         # 量級越大、散得越開
    lo, hi = np.full(n, -1.0), np.full(n, 1.0)
    entry = conformal.fit_horizon(y, lo, hi, magnitude, np.zeros(n),
                                  alpha=0.2, buckets=4, min_samples=0)
    assert len(entry["offsets"]) == 4
    assert entry["offsets"] == sorted(entry["offsets"]), entry["offsets"]
    assert entry["offsets"][-1] > entry["offsets"][0] * 2
    # 分組校準的重點：每一桶自己的覆蓋率都要達標，不是只有整體達標
    index = np.array([conformal.bucket_index(v, entry["edges"]) for v in magnitude])
    for b, off in enumerate(entry["offsets"]):
        idx = index == b
        assert idx.sum() > 0
        cov = float(((y[idx] >= lo[idx] - off) & (y[idx] <= hi[idx] + off)).mean())
        assert cov >= 0.80, (b, cov)
    # 對照：只用全域偏移，大量級的桶會蓋不住（這就是為什麼要分組）
    glob = entry["global_offset"]
    top = index == 3
    assert float(((y[top] >= lo[top] - glob) & (y[top] <= hi[top] + glob)).mean()) < 0.80


def test_small_bucket_falls_back_to_global():
    entry = {"edges": [1.0], "offsets": [0.5, 9.9], "counts": [1000, 3],
             "global_offset": 2.0, "min_samples": 500}
    assert conformal.offset_for(entry, 0.2) == 0.5     # 樣本夠 → 用該桶
    assert conformal.offset_for(entry, 5.0) == 2.0     # 樣本不足 → 退回全域
    assert conformal.offset_for(None, 5.0) == 0.0


def test_bucket_index_handles_degenerate_edges():
    assert conformal.bucket_index(3.0, []) == 0
    assert conformal.bucket_index(float("nan"), [1.0, 2.0]) == 0
    assert conformal.bucket_index(1.5, [1.0, 2.0]) == 1
    assert conformal.bucket_index(9.0, [1.0, 2.0]) == 2


# ── 成套檢查（ADR-121 原則）──

def test_load_rejects_mismatched_fingerprint(tmp_path):
    conformal.save(tmp_path, {"schema_version": 1, "model_fingerprint": "AAA",
                              "horizons": {"30": {}}})
    assert conformal.load(tmp_path, "AAA") is not None
    assert conformal.load(tmp_path, "BBB") is None      # 不成套 → 視為未校準


def test_load_missing_or_broken_file_is_none(tmp_path):
    assert conformal.load(tmp_path, "AAA") is None      # 缺檔不拋錯
    (tmp_path / conformal.FILENAME).write_text("{ not json", encoding="utf-8")
    assert conformal.load(tmp_path, "AAA") is None
    (tmp_path / conformal.FILENAME).write_text(json.dumps({"schema_version": 99}),
                                               encoding="utf-8")
    assert conformal.load(tmp_path, None) is None


# ── ADR-127：serving 不得有校準接線 ──

def test_serving_has_no_conformal_wiring():
    """ADR-127：conformal 只留為離線量測庫；上線路徑不得有開關、快取或輸出欄位。

    要重新啟用必須先立新 ADR，不是把旗標打開——這個測試就是那道閘門。
    """
    from core.interfaces import LightGBMPredictor, PredictionInterval
    from config_loader import get_config
    assert not hasattr(LightGBMPredictor, "_calibration")
    assert not hasattr(LightGBMPredictor, "_CONFORMAL")
    assert not hasattr(PredictionInterval(predicted_available=5, lower_bound=3,
                                          upper_bound=7, horizon_minutes=30), "calibration")
    assert not [k for k in get_config().get("prediction", {}) if "校準" in k]
