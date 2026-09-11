"""分層分析：低流量站是否查表就夠、高周轉站是否才需要模型。

對每個視野，把驗證列依「訓練期周轉量」分成十等分，比較
  模型 P50  vs  seasonal naive  vs  persistence
的 MAE 與空滿事件 F1，並計算「以周轉量門檻切換兩種方法」的混合策略在 6 月的表現。

★口徑：主比較用「未截斷列」（ADR-105/122）——截斷列的答案是被物理邊界壓抑的 0，
  用它比 MAE 會讓永遠猜 0 的方法天生占便宜，先前全量評估已證實這點。
★誠實聲明：十等分的邊界取自「訓練期周轉量分布」，不是拿 6 月表現去調出來的；
  但「在哪個門檻切換」若直接用 6 月挑，會有選擇偏誤，所以下面同時報多個門檻的敏感度。
"""
import gc, json, sys
from pathlib import Path
import numpy as np, pandas as pd

sys.path.insert(0, "/home/claude/yb/backend")
from prediction.evaluation import danger_by_interval, danger_events, mae, prf

WORK = Path("/home/claude/work"); FEAT = WORK / "features"; MODELS = WORK / "candidate_models"
HORIZONS = [30, 60, 90, 120]
chunks = sorted(int(p.stem.split("_")[1]) for p in FEAT.glob("X_*.npy"))

import lightgbm as lgb
report = {}
for mins in HORIZONS:
    boosters = {q: lgb.Booster(model_file=str(MODELS / f"model_{mins}_{q}.txt"))
                for q in ("p10", "p50", "p90")}
    acc = {k: [] for k in ("y", "ab", "ad", "total", "base", "p10", "p50", "p90",
                           "observed", "turnover")}
    for c in chunks:
        meta = pd.read_parquet(FEAT / f"meta_{c:02d}.parquet")
        strata = pd.read_parquet(FEAT / f"strata_{c:02d}.parquet")
        mask = (meta[f"train_{mins}"].to_numpy() == 0) & np.isfinite(meta[f"y_{mins}"].to_numpy())
        if not mask.any():
            continue
        X = np.load(FEAT / f"X_{c:02d}.npy", mmap_mode="r")[mask]
        for q in ("p10", "p50", "p90"):
            acc[q].append(boosters[q].predict(X))
        m = meta.loc[mask]
        acc["y"].append(m[f"y_{mins}"].to_numpy("float32"))
        acc["ab"].append(m["available_bikes"].to_numpy("float32"))
        acc["ad"].append(m["available_docks"].to_numpy("float32"))
        acc["total"].append(m["total_docks"].to_numpy("float32"))
        acc["base"].append(m[f"base_{mins}"].to_numpy("float32"))
        acc["observed"].append(m[f"observed_{mins}"].to_numpy() == 1)
        acc["turnover"].append(strata.loc[mask, "turnover"].to_numpy("float32"))
        del X, meta, m, strata; gc.collect()
    d = {k: np.concatenate(v) for k, v in acc.items()}
    del acc; gc.collect()

    censored = (d["y"] == 0) & ((d["ab"] <= 0) | (d["ad"] <= 0))
    keep = d["observed"] & ~censored          # 可信標籤
    t = d["turnover"][keep]
    y, ab, tot = d["y"][keep], d["ab"][keep], d["total"][keep]
    mdl, base = d["p50"][keep], d["base"][keep]
    lo, hi = d["p10"][keep], d["p90"][keep]
    actual = danger_events(ab, tot, y)

    # 十等分（依訓練期周轉量）
    edges = np.quantile(t, np.linspace(0, 1, 11))
    edges[0], edges[-1] = -np.inf, np.inf
    bins = []
    for i in range(10):
        g = (t >= edges[i]) & (t < edges[i + 1])
        if g.sum() == 0:
            continue
        bins.append({
            "decile": i + 1,
            "turnover_lo": float(edges[i]) if np.isfinite(edges[i]) else 0.0,
            "turnover_hi": float(edges[i + 1]) if np.isfinite(edges[i + 1]) else float(t.max()),
            "n": int(g.sum()),
            "model_mae": mae(y[g], mdl[g]),
            "naive_mae": mae(y[g], base[g]),
            "persist_mae": mae(y[g], np.zeros(int(g.sum()))),
            "model_f1": prf(danger_by_interval(ab[g], tot[g], lo[g], hi[g]), actual[g])["f1"],
            "naive_f1": prf(danger_events(ab[g], tot[g], base[g]), actual[g])["f1"],
        })

    # 門檻敏感度：低於門檻用查表、高於門檻用模型
    qs = (0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 1.0)
    thresholds = [float(np.quantile(t, q)) if q < 1.0 else float(t.max()) + 1.0 for q in qs]
    blend = []
    for q, thr in zip(qs, thresholds):
        low = t < thr
        pred = np.where(low, base, mdl)
        blend.append({"quantile": q, "threshold": thr,
                      "share_lookup": float(low.mean()), "mae": mae(y, pred)})
    report[mins] = {"n_trusted": int(keep.sum()), "deciles": bins, "blend": blend,
                    "pure_model_mae": mae(y, mdl), "pure_naive_mae": mae(y, base)}

    print(f"\n===== {mins} 分（可信標籤 {keep.sum():,} 列）=====", flush=True)
    print(f"{'十分位':>6} {'周轉量區間':>16} {'列數':>10} {'模型MAE':>9} {'查表MAE':>9} "
          f"{'誰贏':>6} {'模型F1':>8} {'查表F1':>8}", flush=True)
    for b in bins:
        win = "模型" if b["model_mae"] < b["naive_mae"] else "查表"
        print(f"{b['decile']:>6} {b['turnover_lo']:>7.2f}~{b['turnover_hi']:<8.2f} "
              f"{b['n']:>10,} {b['model_mae']:>9.3f} {b['naive_mae']:>9.3f} {win:>6} "
              f"{b['model_f1']*100:>7.1f}% {b['naive_f1']*100:>7.1f}%", flush=True)
    print(f"  純模型 {report[mins]['pure_model_mae']:.4f} / 純查表 "
          f"{report[mins]['pure_naive_mae']:.4f}", flush=True)
    print("  混合門檻敏感度（低於門檻用查表）：", flush=True)
    for b in blend:
        print(f"    切在第 {b['quantile']*100:>3.0f} 百分位（查表占 {b['share_lookup']*100:>5.1f}%）"
              f" → MAE {b['mae']:.4f}", flush=True)
    del d, boosters; gc.collect()

(WORK / "strata_eval.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, default=float),
                                       encoding="utf-8")
print("\nwritten strata_eval.json", flush=True)
