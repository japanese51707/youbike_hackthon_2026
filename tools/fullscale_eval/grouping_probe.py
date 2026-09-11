"""找出「哪個推論時算得出來的變數」能分離出覆蓋不足的列（ADR-125 分組變數選擇）。

|P50 − 現況| 被實測證明無效（四個視野偏移全 0）。原因是零膨脹：模型對大多數列
（含很多實際會動的列）都預測接近 0，所以這個變數分不出「會不會動」。
這裡對多個候選變數各切十等分，看覆蓋率的離散程度——離散越大，分組校準越有效。
"""
import gc, json, sys
from pathlib import Path
import numpy as np, pandas as pd

sys.path.insert(0, "/home/claude/yb/backend")
WORK = Path("/home/claude/work"); FEAT = WORK / "features"; MODELS = WORK / "candidate_models"
MINS = 60
chunks = sorted(int(p.stem.split("_")[1]) for p in FEAT.glob("X_*.npy"))
feats = json.loads((FEAT / f"feats_{chunks[0]:02d}.json").read_text())
IDX = {name: i for i, name in enumerate(feats)}

import lightgbm as lgb
boosters = {q: lgb.Booster(model_file=str(MODELS / f"model_{MINS}_{q}.txt"))
            for q in ("p10", "p50", "p90")}
cols = ["y", "ab", "ad", "p10", "p50", "p90", "observed", "slot_p50", "chg1", "chg2",
        "total", "turnover"]
acc = {k: [] for k in cols}
for c in chunks:
    meta = pd.read_parquet(FEAT / f"meta_{c:02d}.parquet")
    strata = pd.read_parquet(FEAT / f"strata_{c:02d}.parquet")
    mask = (meta[f"train_{MINS}"].to_numpy() == 0) & np.isfinite(meta[f"y_{MINS}"].to_numpy())
    X = np.load(FEAT / f"X_{c:02d}.npy", mmap_mode="r")[mask]
    for q in ("p10", "p50", "p90"):
        acc[q].append(boosters[q].predict(X))
    m = meta.loc[mask]
    acc["y"].append(m[f"y_{MINS}"].to_numpy("float32"))
    acc["ab"].append(m["available_bikes"].to_numpy("float32"))
    acc["ad"].append(m["available_docks"].to_numpy("float32"))
    acc["total"].append(m["total_docks"].to_numpy("float32"))
    acc["observed"].append(m[f"observed_{MINS}"].to_numpy() == 1)
    acc["slot_p50"].append(X[:, IDX["station_slot_p50"]])
    acc["chg1"].append(X[:, IDX["change_1hr"]])
    acc["chg2"].append(X[:, IDX["change_2hr"]])
    acc["turnover"].append(strata.loc[mask, "turnover"].to_numpy("float32"))
    del X, meta, m, strata; gc.collect()
d = {k: np.concatenate(v) for k, v in acc.items()}
del acc; gc.collect()

censored = (d["y"] == 0) & ((d["ab"] <= 0) | (d["ad"] <= 0))
keep = d["observed"] & ~censored
y = d["y"][keep]
lo = d["p10"][keep]; mid = d["p50"][keep]; hi = d["p90"][keep]
covered = (y >= lo) & (y <= hi)
print(f"可信標籤 {keep.sum():,} 列；整體覆蓋率 {covered.mean()*100:.1f}%；"
      f"Δ≠0 覆蓋率 {covered[y != 0].mean()*100:.1f}%\n", flush=True)

candidates = {
    "區間寬度 hi-lo": hi - lo,
    "|P50|（現用，已證實無效）": np.abs(mid),
    "|station_slot_p50|": np.abs(np.nan_to_num(d["slot_p50"][keep])),
    "|近1小時變化|": np.abs(np.nan_to_num(d["chg1"][keep])),
    "|近2小時變化|": np.abs(np.nan_to_num(d["chg2"][keep])),
    "站點周轉量": d["turnover"][keep],
    "借用率": d["ab"][keep] / np.maximum(d["total"][keep], 1),
}
result = {}
for name, values in candidates.items():
    edges = np.quantile(values, np.linspace(0, 1, 11))
    edges[0], edges[-1] = -np.inf, np.inf
    covs, ns = [], []
    for i in range(10):
        g = (values >= edges[i]) & (values < edges[i + 1])
        if g.sum() < 1000:
            continue
        covs.append(float(covered[g].mean())); ns.append(int(g.sum()))
    spread = (max(covs) - min(covs)) if covs else 0.0
    result[name] = {"coverage_by_decile": [round(c, 3) for c in covs], "spread": round(spread, 3)}
    print(f"{name:28} 離散 {spread*100:5.1f}pp  "
          + " ".join(f"{c*100:5.1f}" for c in covs), flush=True)

best = max(result.items(), key=lambda kv: kv[1]["spread"])
print(f"\n★分離能力最強：{best[0]}（覆蓋率離散 {best[1]['spread']*100:.1f} 個百分點）", flush=True)
(WORK / "grouping_probe.json").write_text(json.dumps(result, ensure_ascii=False, indent=2),
                                          encoding="utf-8")
