"""
LightGBM 訓練 + 驗證（prediction.train）— P1
=============================================
第一個誠實數字：seasonal naive baseline vs LightGBM，同一驗證集比較。

依 ADR-002/004/015：
- 時間切分（1~5月訓、6月驗），禁隨機切分
- quantile regression 出 P10/P50/P90（規則引擎吃下界/上界）
- 截斷樣本（is_censored）訓練時排除（ADR-015：Δ=0且空/滿站的假資料）
- 分區間評估（健康/接近空/已空），不只報整體平均

用法：
    python backend/prediction/train.py                 # 全量
    python backend/prediction/train.py --sample 60     # 子集(N站)快速驗證管線
"""

from __future__ import annotations
import argparse
import io
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
from prediction.feature_pipeline import build_training_frame
from prediction.baseline import fit_seasonal_naive, predict_seasonal_naive

BUCKET = "youbike-hackathon-2026"
TRAIN_END = "2026-05-31"   # 1~5月訓、6月驗


def load_data(sample_n: int | None = None) -> pd.DataFrame:
    """讀 S3 全部月份 Parquet（1~6月）。sample_n 只取前 N 站快速驗證管線。"""
    import boto3
    import pyarrow.parquet as pq
    s3 = boto3.client("s3")
    months = ["2026-01", "2026-02", "2026-03", "2026-04", "2026-05", "2026-06"]
    dfs = []
    for m in months:
        obj = s3.get_object(Bucket=BUCKET, Key=f"youbike_data/year_month={m}/data.parquet")
        dfs.append(pq.read_table(io.BytesIO(obj["Body"].read())).to_pandas())
    df = pd.concat(dfs, ignore_index=True)
    if sample_n:
        keep = df["場站名稱"].drop_duplicates().head(sample_n)
        df = df[df["場站名稱"].isin(keep)]
    return df


def mae(y_true, y_pred) -> float:
    return float(np.mean(np.abs(np.asarray(y_true) - np.asarray(y_pred))))


def evaluate_by_zone(frame, y_true, y_pred_lgb, y_pred_base):
    """分區間評估（ADR-015）：健康/接近空/已空，各報 MAE。"""
    ab = frame["available_bikes"].values
    zones = {
        "已空(可借=0)": ab <= 0,
        "接近空(1-3)": (ab >= 1) & (ab <= 3),
        "健康(>3)": ab > 3,
    }
    rows = []
    for name, mask in zones.items():
        if mask.sum() == 0:
            continue
        rows.append((name, int(mask.sum()),
                     round(mae(y_true[mask], y_pred_base[mask]), 3),
                     round(mae(y_true[mask], y_pred_lgb[mask]), 3)))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=None, help="只取前 N 站快速驗證")
    args = ap.parse_args()

    print(f"[1/5] 讀 S3 資料{'(子集 '+str(args.sample)+' 站)' if args.sample else '(全量)'} ...", flush=True)
    df = load_data(args.sample)
    print(f"      列數 {len(df):,}｜站數 {df['場站名稱'].nunique()}", flush=True)

    print("[2/5] 組裝特徵（防洩漏：窗口限訓練期、forward fill、截斷標記）...", flush=True)
    frame, feat_cols = build_training_frame(df, TRAIN_END)
    frame = frame.dropna(subset=["target_delta"])   # 最後一格無目標

    train = frame[frame["is_train"] == 1].copy()
    valid = frame[frame["is_train"] == 0].copy()
    # 截斷樣本訓練時排除（ADR-015）
    train_clean = train[train["is_censored"] == 0]
    print(f"      訓練 {len(train):,}（排除截斷 {len(train)-len(train_clean):,} → {len(train_clean):,}）｜驗證 {len(valid):,}", flush=True)

    print("[3/5] seasonal naive baseline ...", flush=True)
    table, gmed = fit_seasonal_naive(train_clean)
    base_pred = predict_seasonal_naive(valid, table, gmed).values
    base_mae = mae(valid["target_delta"].values, base_pred)
    print(f"      baseline MAE = {base_mae:.3f}", flush=True)

    print("[4/5] LightGBM quantile (P10/P50/P90) ...", flush=True)
    import lightgbm as lgb
    Xtr = train_clean[feat_cols].astype(float)
    ytr = train_clean["target_delta"].astype(float)
    Xva = valid[feat_cols].astype(float)
    yva = valid["target_delta"].astype(float).values

    # ⚠️ 超參數為「未調參的起始預設值」，尚未做超參數優化（審查 F-07 rolling CV 選參尚未做）。
    #   objective/alpha 有依據（ADR-002/004：quantile 出區間、規則引擎吃下界）；
    #   但 n_estimators/learning_rate/num_leaves/min_child_samples 是常見起始值，非調校結果。
    #   分位數 alpha=0.1/0.9 目前是拍的，審查 6.2 指出應由營運成本(漏報vs誤報)用 newsvendor 決定。
    #   → 「模型贏不了 baseline」有一部分可能來自未調參，不全是資料問題。待後續優化並記 ADR。
    preds = {}
    for q, alpha in [("p10", 0.10), ("p50", 0.50), ("p90", 0.90)]:
        m = lgb.LGBMRegressor(objective="quantile", alpha=alpha,
                              n_estimators=300, learning_rate=0.05,   # ← 未調參的預設值
                              num_leaves=31, min_child_samples=50, verbose=-1)
        m.fit(Xtr, ytr)
        preds[q] = m.predict(Xva)

    lgb_mae = mae(yva, preds["p50"])
    print(f"      LightGBM P50 MAE = {lgb_mae:.3f}", flush=True)

    # 區間覆蓋率（P10~P90 名目 80%）+ 分位數交叉檢查
    lo = np.minimum(preds["p10"], preds["p90"])
    hi = np.maximum(preds["p10"], preds["p90"])
    coverage = float(np.mean((yva >= lo) & (yva <= hi)))
    crossing = float(np.mean(preds["p10"] > preds["p90"]))

    print("[5/5] 結果", flush=True)
    print("=" * 56, flush=True)
    print(f"baseline(seasonal naive) MAE : {base_mae:.3f}", flush=True)
    print(f"LightGBM P50             MAE : {lgb_mae:.3f}", flush=True)
    improve = (base_mae - lgb_mae) / base_mae * 100 if base_mae else 0
    print(f"改善                          : {improve:+.1f}%", flush=True)
    print(f"區間覆蓋率(P10~P90,名目80%)   : {coverage*100:.1f}%", flush=True)
    print(f"分位數交叉率(應接近0)         : {crossing*100:.2f}%", flush=True)
    print("-" * 56, flush=True)
    print("分區間 MAE（baseline / LightGBM）：", flush=True)
    for name, n, bm, lm in evaluate_by_zone(valid, yva, preds["p50"], base_pred):
        print(f"  {name:14} n={n:>8,}  {bm:>7.3f} / {lm:>7.3f}", flush=True)
    print("=" * 56, flush=True)
    print("註：截斷樣本已排除訓練；分區間看『已空』區才是關鍵（系統存在理由）", flush=True)


if __name__ == "__main__":
    main()
