"""驗證 ADR-125 的機制是否真的修好條件覆蓋率。

候選 booster 只用 1~5 月訓練，6 月完全沒被看過。因此把 6 月切兩半：
  前半 → 校準集（算 conformal 偏移）
  後半 → 驗證集（量校準前後的覆蓋率）
兩半都是模型沒看過的資料，是有效的 split-conformal 設定。

★與正式流程的差別：ADR-125 §2 規定正式的校準集要從「訓練期尾端」切出來。
  這裡用 6 月切半只是為了在不重訓的前提下驗證機制本身。
"""
import gc, json, sys
from pathlib import Path
import numpy as np, pandas as pd

sys.path.insert(0, "/home/claude/yb/backend")
from prediction.conformal import bucket_index, fit_horizon, offset_for

WORK = Path("/home/claude/work"); FEAT = WORK / "features"; MODELS = WORK / "candidate_models"
HORIZONS = [30, 60, 90, 120]
chunks = sorted(int(p.stem.split("_")[1]) for p in FEAT.glob("X_*.npy"))

import lightgbm as lgb
report = {}
for mins in HORIZONS:
    boosters = {q: lgb.Booster(model_file=str(MODELS / f"model_{mins}_{q}.txt"))
                for q in ("p10", "p50", "p90")}
    acc = {k: [] for k in ("y", "ab", "ad", "p10", "p50", "p90", "observed", "tmonth_row")}
    for c in chunks:
        meta = pd.read_parquet(FEAT / f"meta_{c:02d}.parquet")
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
        acc["observed"].append(m[f"observed_{mins}"].to_numpy() == 1)
        acc["tmonth_row"].append(np.arange(len(m)))     # 塊內順序＝時間順序（每站時間排序）
        del X, meta, m; gc.collect()
    d = {k: np.concatenate(v) for k, v in acc.items()}
    del acc; gc.collect()

    # 可信標籤（排除補值與截斷列，與第三批評估同口徑）
    censored = (d["y"] == 0) & ((d["ab"] <= 0) | (d["ad"] <= 0))
    keep = d["observed"] & ~censored
    y, ab = d["y"][keep], d["ab"][keep]
    lo, mid, hi = (ab + d["p10"][keep], ab + d["p50"][keep], ab + d["p90"][keep])
    # 到達存量口徑改回 Δ 口徑比較（y 本來就是 Δ）
    lo, mid, hi = lo - ab, mid - ab, hi - ab

    # 前半校準、後半驗證（用列序當時間代理：每站已依時間排序，全體切半近似時間切分）
    n = y.size
    half = n // 2
    rng = np.random.default_rng(0)
    order = rng.permutation(n)          # 隨機切半：可交換性成立，避免塊間站別造成偏差
    cal, val = order[:half], order[half:]

    entry = fit_horizon(y[cal], lo[cal], hi[cal], mid[cal], np.zeros(cal.size),
                        alpha=0.2, buckets=4, min_samples=500)
    sizes_val = np.abs(mid[val])
    offs = np.array([offset_for(entry, v) for v in sizes_val])

    def coverage(mask, offset):
        return float(((y[val][mask] >= lo[val][mask] - offset[mask])
                      & (y[val][mask] <= hi[val][mask] + offset[mask])).mean())

    zero = np.zeros(val.size)
    all_mask = np.ones(val.size, dtype=bool)
    moving = y[val] != 0
    width_before = float(np.mean(hi[val] - lo[val]))
    width_after = float(np.mean(hi[val] + offs - (lo[val] - offs)))
    report[mins] = {
        "n_cal": int(cal.size), "n_val": int(val.size), "n_moving": int(moving.sum()),
        "edges": entry["edges"], "offsets": entry["offsets"], "counts": entry["counts"],
        "global_offset": entry["global_offset"],
        "coverage_all_before": coverage(all_mask, zero),
        "coverage_all_after": coverage(all_mask, offs),
        "coverage_moving_before": coverage(moving, zero),
        "coverage_moving_after": coverage(moving, offs),
        "width_before": round(width_before, 3), "width_after": round(width_after, 3),
    }
    r = report[mins]
    print(f"\n===== {mins} 分（校準 {r['n_cal']:,} / 驗證 {r['n_val']:,} 列）=====", flush=True)
    print(f"  分桶偏移 {r['offsets']}（邊界 {[round(e,2) for e in r['edges']]}，全域 {r['global_offset']}）", flush=True)
    print(f"  整體覆蓋率  {r['coverage_all_before']*100:5.1f}% → {r['coverage_all_after']*100:5.1f}%", flush=True)
    print(f"  Δ≠0 覆蓋率  {r['coverage_moving_before']*100:5.1f}% → {r['coverage_moving_after']*100:5.1f}%"
          f"   ★這是要修的那一個", flush=True)
    print(f"  平均區間寬  {r['width_before']:.2f} → {r['width_after']:.2f} 台", flush=True)
    del d, boosters; gc.collect()

(WORK / "conformal_check.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, default=float),
                                           encoding="utf-8")
print("\nwritten conformal_check.json", flush=True)
