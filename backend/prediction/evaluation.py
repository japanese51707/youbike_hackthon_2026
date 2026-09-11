"""
離線評估協議（prediction.evaluation）— ADR-122 §7
==================================================
把「怎麼算指標」集中在這裡，讓修正前後、不同模型、不同基準用同一把尺。

每個視野都報：
  - MAE（全樣本／正常區間／已空區／決策相關區）
  - P10–P90 覆蓋率（名目 80%）與分位數交叉率（應為 0）
  - 空／滿事件的 precision／recall／F1（規則引擎真正在意的決策面）
並與兩個簡單基準對照：
  - persistence：Δ=0（最笨的基準；存量不變）
  - seasonal naive：站 × 平假日 × 時段的訓練期中位數（既有 baseline）

★ADR-122 C：主指標只用「標籤來自真實觀測」的列；補值列另外分開報，不混進主數字。
★截斷列（ADR-105）：觀測 Δ=0 且當下空站或滿站，那個 0 是被物理邊界壓抑的假值，訓練時已排除。
  若評估仍用它當答案，等於要求模型複製一個已被宣告為不可信的標籤——永遠猜 0 的 persistence
  與中位數常為 0 的 seasonal naive 會天生占便宜。因此本模組把截斷列拆出來單獨報
  （excluding_censored / censored_only），讓「模型在可信標籤上的表現」與「截斷列的行為」分開看。

對外暴露：
    evaluate_horizon(...) -> dict
    format_report(rows) -> str
"""

from __future__ import annotations

import numpy as np

# 規則引擎的安全緩衝（config.trigger）；事件＝到達後可借或可還 ≤ 緩衝
DANGER_BUFFER = 2


def mae(y_true, y_pred) -> float:
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    if y_true.size == 0:
        return float("nan")
    return float(np.mean(np.abs(y_true - y_pred)))


def _safe(fn, mask, *args):
    return fn(*(a[mask] for a in args)) if mask.sum() else float("nan")


def danger_events(available, total, delta) -> np.ndarray:
    """點估計下是否進危險區：到達存量 ≤ 緩衝，或可還位 ≤ 緩衝。"""
    arrival = np.asarray(available, dtype=float) + np.asarray(delta, dtype=float)
    total = np.asarray(total, dtype=float)
    return (arrival <= DANGER_BUFFER) | ((total - arrival) <= DANGER_BUFFER)


def danger_by_interval(available, total, lower, upper) -> np.ndarray:
    """區間下界判危險（與 rule_engine ADR-111 一致）：防空看 P10、防滿看 P90。"""
    available = np.asarray(available, dtype=float)
    total = np.asarray(total, dtype=float)
    arr_lo = available + np.asarray(lower, dtype=float)
    arr_hi = available + np.asarray(upper, dtype=float)
    return (arr_lo <= DANGER_BUFFER) | ((total - arr_hi) <= DANGER_BUFFER)


def prf(pred_positive: np.ndarray, actual: np.ndarray) -> dict:
    tp = int((pred_positive & actual).sum())
    fp = int((pred_positive & ~actual).sum())
    fn = int((~pred_positive & actual).sum())
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {"precision": precision, "recall": recall, "f1": f1,
            "tp": tp, "fp": fp, "fn": fn}


def evaluate_horizon(
    horizon_min: int,
    y_true,
    available,
    total_docks,
    p10=None,
    p50=None,
    p90=None,
    baselines: dict | None = None,
    label_observed=None,
    label_censored=None,
) -> dict:
    """算單一視野的完整指標。

    label_observed：布林陣列，True＝該列標籤來自真實觀測。主指標只用這些列（ADR-122 C）；
    補值列以 imputed_* 另外回報，不混進主數字。
    label_censored：布林陣列，True＝該列標籤是被物理邊界壓抑的截斷值（ADR-105）。
    有給的話另外回報 excluding_censored（可信標籤上的表現）與 censored_only（截斷列的行為），
    主指標維持涵蓋全部真實觀測列，兩種口徑都看得到。
    """
    y_true = np.asarray(y_true, dtype=float)
    available = np.asarray(available, dtype=float)
    total_docks = np.asarray(total_docks, dtype=float)
    n_all = y_true.size
    if label_observed is None:
        observed = np.ones(n_all, dtype=bool)
    else:
        observed = np.asarray(label_observed, dtype=bool)

    def sub(arr):
        return None if arr is None else np.asarray(arr, dtype=float)[observed]

    yt = y_true[observed]
    ab = available[observed]
    tot = total_docks[observed]
    docks = tot - ab
    lo, mid, hi = sub(p10), sub(p50), sub(p90)

    normal = (ab >= 1) & (docks >= 1)          # 未被物理邊界截斷的區間
    empty = ab <= 0
    decision = ab <= 3                          # 決策相關區（已空 + 接近空）

    out = {
        "horizon_min": horizon_min,
        "n_rows": int(n_all),
        "n_observed": int(observed.sum()),
        "n_imputed_labels": int(n_all - observed.sum()),
        "models": {},
    }

    def block(name, point, lower=None, upper=None):
        entry = {
            "mae": mae(yt, point),
            "mae_normal": _safe(mae, normal, yt, point),
            "mae_empty": _safe(mae, empty, yt, point),
            "mae_decision": _safe(mae, decision, yt, point),
        }
        actual = danger_events(ab, tot, yt)
        if lower is not None and upper is not None:
            entry["coverage"] = float(((yt >= lower) & (yt <= upper)).mean())
            entry["crossing_rate"] = float(((lower > point) | (point > upper)).mean())
            entry["event"] = prf(danger_by_interval(ab, tot, lower, upper), actual)
            entry["event_basis"] = "interval"   # 與規則引擎一致：P10 防空 / P90 防滿
        else:
            entry["event"] = prf(danger_events(ab, tot, point), actual)
            entry["event_basis"] = "point"      # 無區間，用點估計（與模型不完全對等）
        entry["n_actual_events"] = int(actual.sum())
        return entry

    if mid is not None:
        out["models"]["model"] = block("model", mid, lo, hi)
    for name, values in (baselines or {}).items():
        out["models"][name] = block(name, np.asarray(values, dtype=float)[observed])

    # 補值列另外報（誠實揭露，不進主指標）
    if mid is not None and (~observed).any():
        out["imputed_only"] = {
            "n": int((~observed).sum()),
            "mae": mae(y_true[~observed], np.asarray(p50, dtype=float)[~observed]),
        }

    # ADR-105/122：截斷列的標籤不可信，拆開報
    if label_censored is not None:
        censored = np.asarray(label_censored, dtype=bool)[observed]
        for key, keep in (("excluding_censored", ~censored), ("censored_only", censored)):
            if keep.sum() == 0:
                continue
            entry = {"n": int(keep.sum()), "models": {}}
            for name, block_ in out["models"].items():
                point = mid if name == "model" else np.asarray(
                    baselines[name], dtype=float)[observed]
                sub_entry = {"mae": mae(yt[keep], point[keep])}
                if name == "model" and lo is not None and hi is not None:
                    sub_entry["coverage"] = float(
                        ((yt[keep] >= lo[keep]) & (yt[keep] <= hi[keep])).mean())
                    pred_pos = danger_by_interval(ab[keep], tot[keep], lo[keep], hi[keep])
                else:
                    pred_pos = danger_events(ab[keep], tot[keep], point[keep])
                sub_entry["event"] = prf(pred_pos, danger_events(ab[keep], tot[keep], yt[keep]))
                entry["models"][name] = sub_entry
            out[key] = entry
    return out


def persistence_baseline(n: int) -> np.ndarray:
    """最笨的基準：預測淨變化為 0（存量不變）。"""
    return np.zeros(n, dtype=float)


def format_report(rows: list[dict]) -> str:
    """把 evaluate_horizon 的輸出排成可讀表格。"""
    lines = []
    header = (f"{'視野':>5} {'模型':>14} {'MAE':>8} {'正常區':>8} {'已空區':>8} "
              f"{'決策區':>8} {'覆蓋率':>8} {'交叉率':>7} {'精確':>7} {'召回':>7} {'F1':>7}")
    lines.append(header)
    lines.append("-" * len(header))
    for row in rows:
        for name, m in row["models"].items():
            cov = f"{m['coverage']*100:>7.1f}%" if "coverage" in m else f"{'—':>8}"
            cross = f"{m['crossing_rate']*100:>6.1f}%" if "crossing_rate" in m else f"{'—':>7}"
            lines.append(
                f"{row['horizon_min']:>4}分 {name:>14} {m['mae']:>8.3f} "
                f"{m['mae_normal']:>8.3f} {m['mae_empty']:>8.3f} {m['mae_decision']:>8.3f} "
                f"{cov} {cross} {m['event']['precision']*100:>6.1f}% "
                f"{m['event']['recall']*100:>6.1f}% {m['event']['f1']*100:>6.1f}%")
        lines.append(
            f"       樣本 {row['n_observed']:,} 列（補值標籤另計 {row['n_imputed_labels']:,} 列）"
            f"｜實際事件 {next(iter(row['models'].values()))['n_actual_events']:,} 件")
        lines.append("-" * len(header))
    return "\n".join(lines)
