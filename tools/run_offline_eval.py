"""
第三批 A 離線評估（ADR-122 §7）
================================
用本機 1~6 月 Parquet，比較「修正前的評估協議」與「修正後的評估協議」，
並與兩個簡單基準（persistence、seasonal naive）對照。

修正前（legacy）：依輸入時間切分、單一視野的截斷與介入遮罩、統計量用整段訓練期擬合、
                  補值列當成真實答案一起評。
修正後（fixed）  ：依目標時間切分、逐視野遮罩、統計量只用訓練期（ADR-122 A 預設最嚴格窗口）、
                  主指標只用真實觀測的標籤。

用法（預設子集 60 站，先看得到數字再決定要不要全量）：
    PYTHONPATH=backend python3 tools/run_offline_eval.py --data-dir output/youbike_parquet
    PYTHONPATH=backend python3 tools/run_offline_eval.py --stations 200 --out docs/analysis/xxx.md
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from prediction.evaluation import (  # noqa: E402
    evaluate_horizon, format_report, persistence_baseline)
from prediction.feature_pipeline import HORIZON_STEPS, build_training_frame  # noqa: E402
from prediction.baseline import fit_seasonal_naive, predict_seasonal_naive  # noqa: E402

TRAIN_END = "2026-05-31"
HP = {"n_estimators": 200, "learning_rate": 0.05, "num_leaves": 31,
      "min_child_samples": 50, "verbose": -1}


def load_local(data_dir: Path, n_stations: int | None) -> pd.DataFrame:
    """讀本機 Parquet（不打 S3）。n_stations 取前 N 站做子集。"""
    import pyarrow.parquet as pq
    parts = sorted(data_dir.glob("year_month=*/*.parquet"))
    if not parts:
        raise SystemExit(f"找不到 Parquet：{data_dir}")
    frames = [pq.read_table(p).to_pandas() for p in parts]
    df = pd.concat(frames, ignore_index=True)
    if n_stations:
        keep = df["場站名稱"].drop_duplicates().head(n_stations)
        df = df[df["場站名稱"].isin(keep)]
    return df


def _fit_predict(train, valid, feat_cols, target):
    import lightgbm as lgb
    preds = {}
    X = train[feat_cols].astype(float)
    y = train[target].astype(float)
    Xv = valid[feat_cols].astype(float)
    for name, alpha in (("p10", 0.10), ("p50", 0.50), ("p90", 0.90)):
        model = lgb.LGBMRegressor(objective="quantile", alpha=alpha, **HP)
        model.fit(X, y)
        preds[name] = model.predict(Xv)
    return preds


def run_protocol(df: pd.DataFrame, protocol: str, factors: bool = False) -> list[dict]:
    """protocol='legacy' 重現修正前的做法；'fixed' 走 ADR-122 修正後的做法。

    factors=True 併入已採用的靜態／半靜態因子（POI、行為指紋、地形）。
    天氣因子需 _weather_cache，本機評估未帶入時會關閉並在報告標明。
    """
    kw = dict(with_weather=False, with_poi=factors,
              with_profile=factors, with_terrain=factors)
    if protocol == "legacy":
        # 修正前：統計量用「輸入時間在訓練期」的所有列擬合（含標籤跨界的列）
        frame, feat_cols = build_training_frame(
            df, TRAIN_END, **kw,
            fit_mask=lambda f: f["dt"] < pd.Timestamp(TRAIN_END) + pd.Timedelta(days=1))
    else:
        frame, feat_cols = build_training_frame(df, TRAIN_END, **kw)

    rows = []
    for h, mins in HORIZON_STEPS.items():
        target = f"target_delta_{mins}"
        sub = frame.dropna(subset=[target])
        if protocol == "legacy":
            train = sub[sub["is_train"] == 1]
            valid = sub[sub["is_train"] == 0]
            clean = train[(train["is_censored"] == 0) & (train["is_rebalancing"] == 0)]
            observed = None                      # 修正前：補值列也當真實答案
        else:
            train = sub[sub[f"is_train_{mins}"] == 1]
            valid = sub[sub[f"is_train_{mins}"] == 0]
            clean = train[(train[f"is_censored_{mins}"] == 0)
                          & (train[f"is_rebalancing_{mins}"] == 0)
                          & (train[f"target_imputed_{mins}"] == 0)]
            observed = (valid[f"target_imputed_{mins}"] == 0).values
        if clean.empty or valid.empty:
            continue

        preds = _fit_predict(clean, valid, feat_cols, target)
        table, gmed = fit_seasonal_naive(clean, target_col=target)
        seasonal = predict_seasonal_naive(valid, table, gmed).values
        # ADR-105/122：截斷列（觀測 Δ=0 且空站或滿站）的標籤不可信，拆開報
        y_values = valid[target].astype(float).values
        ab_values = valid["available_bikes"].values
        ad_values = valid["available_docks"].values
        censored = (y_values == 0) & ((ab_values <= 0) | (ad_values <= 0))
        result = evaluate_horizon(
            mins,
            y_true=y_values,
            available=ab_values,
            total_docks=valid["total_docks"].values,
            p10=preds["p10"], p50=preds["p50"], p90=preds["p90"],
            baselines={"seasonal_naive": seasonal,
                       "persistence": persistence_baseline(len(valid))},
            label_observed=observed, label_censored=censored)
        result["n_train_rows"] = int(len(clean))
        rows.append(result)
        print(f"  [{protocol}] {mins} 分：訓練 {len(clean):,} / 驗證 {len(valid):,} 列",
              flush=True)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default="output/youbike_parquet")
    ap.add_argument("--stations", type=int, default=60, help="子集站數；0=全量")
    ap.add_argument("--out", default=None, help="把報告寫成 Markdown")
    ap.add_argument("--json", default=None, help="把原始指標寫成 JSON")
    ap.add_argument("--factors", action="store_true",
                    help="併入已採用因子（POI／行為指紋／地形；天氣需本機快取，未帶入）")
    ap.add_argument("--protocols", default="legacy,fixed",
                    help="要跑哪些協定，逗號分隔")
    args = ap.parse_args()

    data_dir = (ROOT / args.data_dir) if not Path(args.data_dir).is_absolute() else Path(args.data_dir)
    print(f"讀取 {data_dir}（子集 {args.stations or '全量'} 站）...", flush=True)
    df = load_local(data_dir, args.stations or None)
    print(f"  列數 {len(df):,}｜站數 {df['場站名稱'].nunique()}", flush=True)

    results = {}
    for protocol in [x.strip() for x in args.protocols.split(",") if x.strip()]:
        print(f"\n=== {protocol}（因子={'開' if args.factors else '關'}）===", flush=True)
        results[protocol] = run_protocol(df, protocol, factors=args.factors)

    report = []
    for protocol, rows in results.items():
        title = "修正前（依輸入時間切分／單一視野遮罩／補值當答案）" if protocol == "legacy" \
            else "修正後（ADR-122：目標時間切分／逐視野遮罩／只用真實觀測標籤）"
        report.append(f"### {protocol}：{title}\n")
        report.append("```")
        report.append(format_report(rows))
        report.append("```\n")
    text = "\n".join(report)
    print("\n" + text)

    if args.out:
        out = (ROOT / args.out) if not Path(args.out).is_absolute() else Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        print(f"報告已寫入 {out}")
    if args.json:
        jp = (ROOT / args.json) if not Path(args.json).is_absolute() else Path(args.json)
        jp.parent.mkdir(parents=True, exist_ok=True)
        jp.write_text(json.dumps(results, ensure_ascii=False, indent=2, default=float),
                      encoding="utf-8")
        print(f"原始指標已寫入 {jp}")


if __name__ == "__main__":
    main()
