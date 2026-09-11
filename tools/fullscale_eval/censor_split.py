"""補充分析：把驗證列拆成「截斷列」與「未截斷列」分開比。

ADR-105/122：截斷列＝觀測 Δ=0 且當下空站或滿站，那個 0 是被物理邊界壓抑的假值，
訓練時已刻意排除。若在評估時仍用這個 0 當答案，等於要求模型去複製它——
persistence（永遠猜 0）與 seasonal naive（中位數常為 0）天生占便宜。
這支腳本量化這件事到底影響多少。
"""
import gc, json, sys
from pathlib import Path
import numpy as np, pandas as pd

sys.path.insert(0, "/home/claude/yb/backend")
from prediction.evaluation import danger_by_interval, danger_events, mae, prf

WORK = Path("/home/claude/work"); FEAT = WORK / "features"
MODELS = WORK / "candidate_models"
HORIZONS = [30, 60, 90, 120]
chunks = sorted(int(p.stem.split("_")[1]) for p in FEAT.glob("X_*.npy"))

import lightgbm as lgb
out = {}
for mins in HORIZONS:
    boosters = {q: lgb.Booster(model_file=str(MODELS / f"model_{mins}_{q}.txt"))
                for q in ("p10", "p50", "p90")}
    acc = {k: [] for k in ("y", "ab", "ad", "total", "base", "p10", "p50", "p90", "observed")}
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
        acc["total"].append(m["total_docks"].to_numpy("float32"))
        acc["base"].append(m[f"base_{mins}"].to_numpy("float32"))
        acc["observed"].append((m[f"observed_{mins}"].to_numpy() == 1))
        del X, meta, m; gc.collect()
    d = {k: np.concatenate(v) for k, v in acc.items()}
    del acc; gc.collect()

    obs = d["observed"]
    # ADR-105 截斷定義：觀測 Δ=0 且當下空站(可借=0)或滿站(可還=0)
    censored = (d["y"] == 0) & ((d["ab"] <= 0) | (d["ad"] <= 0))
    zero = d["y"] == 0
    groups = {
        "全部": obs,
        "未截斷": obs & ~censored,
        "截斷列": obs & censored,
        "未截斷且Δ≠0": obs & ~censored & ~zero,
    }
    res = {}
    for name, g in groups.items():
        if g.sum() == 0:
            continue
        actual = danger_events(d["ab"][g], d["total"][g], d["y"][g])
        model_pos = danger_by_interval(d["ab"][g], d["total"][g], d["p10"][g], d["p90"][g])
        base_pos = danger_events(d["ab"][g], d["total"][g], d["base"][g])
        res[name] = {
            "n": int(g.sum()),
            "model_mae": mae(d["y"][g], d["p50"][g]),
            "naive_mae": mae(d["y"][g], d["base"][g]),
            "persist_mae": mae(d["y"][g], np.zeros(int(g.sum()))),
            "coverage": float(((d["y"][g] >= d["p10"][g]) & (d["y"][g] <= d["p90"][g])).mean()),
            "model_event": prf(model_pos, actual),
            "naive_event": prf(base_pos, actual),
        }
    out[mins] = res
    print(f"\n===== {mins} 分 =====", flush=True)
    for name, r in res.items():
        print(f"  {name:12} n={r['n']:>9,}  MAE 模型 {r['model_mae']:.3f} / naive "
              f"{r['naive_mae']:.3f} / persist {r['persist_mae']:.3f}"
              f"  覆蓋 {r['coverage']*100:.1f}%"
              f"  事件F1 模型 {r['model_event']['f1']*100:.1f}% / naive {r['naive_event']['f1']*100:.1f}%",
              flush=True)
    del d, boosters; gc.collect()

(WORK / "censor_split.json").write_text(json.dumps(out, ensure_ascii=False, indent=2, default=float),
                                        encoding="utf-8")
print("\nwritten censor_split.json", flush=True)
