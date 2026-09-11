"""ADR-122 §7：評估協定本身的單元測試（不訓練模型，只驗指標口徑）。

守住三件事：補值標籤不進主指標、截斷列被拆開報、事件判定對模型用區間下界、對基準用點估計。
"""

import numpy as np

from prediction.evaluation import danger_by_interval, danger_events, evaluate_horizon, prf


def test_imputed_labels_are_excluded_from_headline_metrics():
    y = np.array([0.0, 0.0, 5.0, 5.0])
    observed = np.array([True, True, True, False])   # 最後一列標籤是補出來的
    out = evaluate_horizon(
        30, y_true=y, available=np.array([5.0] * 4), total_docks=np.array([20.0] * 4),
        p10=np.zeros(4), p50=np.zeros(4), p90=np.zeros(4), label_observed=observed)
    assert out["n_rows"] == 4 and out["n_observed"] == 3 and out["n_imputed_labels"] == 1
    # 主指標只吃 3 列真實觀測：|0-0|,|0-0|,|5-0| → 5/3
    assert abs(out["models"]["model"]["mae"] - 5 / 3) < 1e-9
    assert out["imputed_only"]["n"] == 1


def test_censored_rows_are_reported_separately():
    """截斷列＝觀測 Δ=0 且空站；那個 0 是被壓抑的假值，不該混進「模型準不準」的主判斷。"""
    y = np.array([0.0, 0.0, 4.0, -4.0])
    censored = np.array([True, True, False, False])
    out = evaluate_horizon(
        60, y_true=y, available=np.array([0.0, 0.0, 10.0, 10.0]),
        total_docks=np.array([20.0] * 4),
        p10=np.array([-3.0, -3.0, 1.0, -6.0]),
        p50=np.array([-2.0, -2.0, 3.0, -5.0]),
        p90=np.array([-1.0, -1.0, 5.0, -3.0]),
        baselines={"persistence": np.zeros(4)},
        label_censored=censored)
    assert out["censored_only"]["n"] == 2
    assert out["excluding_censored"]["n"] == 2
    # 截斷列上 persistence 完美、模型看起來很差——這正是不該用它下結論的理由
    assert out["censored_only"]["models"]["persistence"]["mae"] == 0.0
    assert out["censored_only"]["models"]["model"]["mae"] == 2.0
    # 可信標籤上模型才是公平比較：|4-3|,|−4−(−5)| = 1.0
    assert out["excluding_censored"]["models"]["model"]["mae"] == 1.0


def test_event_basis_differs_between_model_and_baseline():
    """模型用 P10/P90 區間下界判危險（與 rule_engine ADR-111 一致），基準只能用點估計。"""
    out = evaluate_horizon(
        30, y_true=np.array([-1.0]), available=np.array([5.0]), total_docks=np.array([20.0]),
        p10=np.array([-4.0]), p50=np.array([-1.0]), p90=np.array([0.0]),
        baselines={"persistence": np.array([0.0])})
    assert out["models"]["model"]["event_basis"] == "interval"
    assert out["models"]["persistence"]["event_basis"] == "point"
    # 到達存量下界 5-4=1 ≤ 緩衝 2 → 模型判危險；點估計 5+0=5 → 基準不判危險
    assert danger_by_interval([5.0], [20.0], [-4.0], [0.0])[0]
    assert not danger_events([5.0], [20.0], [0.0])[0]


def test_prf_counts_are_aggregatable():
    """precision/recall 回傳 tp/fp/fn，才能跨塊相加——全量評估是分塊算的。"""
    pred = np.array([True, True, False, False])
    actual = np.array([True, False, True, False])
    r = prf(pred, actual)
    assert (r["tp"], r["fp"], r["fn"]) == (1, 1, 1)
    assert abs(r["precision"] - 0.5) < 1e-9 and abs(r["recall"] - 0.5) < 1e-9
