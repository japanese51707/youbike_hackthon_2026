"""Pass 3b：全量全站最終訓練與離線評估（ADR-122 §7）。

對每個視野：
  訓練列 = 標籤目標時間在訓練期、非截斷、整段視野無調度介入、標籤為真實觀測
  驗證列 = 標籤目標時間在 6 月
  模型   = LightGBM quantile P10/P50/P90（超參數由 tuned_params.json 指定）
  基準   = seasonal naive（站×平假日×時段訓練期中位數）與 persistence（Δ=0）
  指標   = MAE（全／正常區／已空區／決策區）、P10–P90 覆蓋率、分位數交叉率、
           空滿事件 precision/recall/F1（模型用區間下界判危險，與 ADR-111 規則引擎一致）

記憶體策略：特徵矩陣以 memmap 讀取，逐塊填進預先配置好的訓練矩陣；
每個視野只建一次 lgb.Dataset，三個分位數共用。
"""
import gc, json, sys, time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, "/home/claude/yb/backend")
sys.path.insert(0, "/home/claude/work")
from prediction.evaluation import evaluate_horizon, format_report, persistence_baseline
from lgbm_util import fit

WORK = Path("/home/claude/work")
FEAT = WORK / "features"
HORIZONS = [30, 60, 90, 120]
QUANTILES = [("p10", 0.10), ("p50", 0.50), ("p90", 0.90)]


def chunk_ids():
    return sorted(int(p.stem.split("_")[1]) for p in FEAT.glob("X_*.npy"))


def load_meta(c):
    return pd.read_parquet(FEAT / f"meta_{c:02d}.parquet")


def gather(chunks, masks, n_feats):
    """把各塊符合 mask 的列填進一個連續 float32 矩陣。"""
    total = int(sum(m.sum() for m in masks.values()))
    X = np.empty((total, n_feats), dtype="float32")
    pos = 0
    for c in chunks:
        mask = masks[c]
        if not mask.any():
            continue
        src = np.load(FEAT / f"X_{c:02d}.npy", mmap_mode="r")
        rows = src[mask]
        X[pos:pos + len(rows)] = rows
        pos += len(rows)
        del src, rows
        gc.collect()
    assert pos == total, (pos, total)
    return X


def main():
    params_path = WORK / "tuned_params.json"
    tuned = json.loads(params_path.read_text(encoding="utf-8"))
    # tune.py 的 running-best 初始化只看 default，所以這裡直接對所有已評估的參數組取最小 CV。
    winner = min(tuned["results"].items(), key=lambda kv: kv[1]["cv_mae"])[0]
    params = tuned["results"][winner]["params"]
    tuned["winner"] = winner
    print(f"超參數來源：{params_path.name}（{winner}，CV "
          f"{tuned['results'][winner]['cv_mae']:.4f}）\n{params}", flush=True)
    print("  對照：" + "、".join(f"{k} {v['cv_mae']:.4f}" for k, v in
                                 sorted(tuned["results"].items(), key=lambda kv: kv[1]["cv_mae"]))
          + "\n", flush=True)

    chunks = chunk_ids()
    feats = json.loads((FEAT / f"feats_{chunks[0]:02d}.json").read_text(encoding="utf-8"))
    for c in chunks[1:]:
        assert json.loads((FEAT / f"feats_{c:02d}.json").read_text(encoding="utf-8")) == feats
    metas = {c: load_meta(c) for c in chunks}
    n_rows = sum(len(m) for m in metas.values())
    print(f"塊數 {len(chunks)}｜總列數 {n_rows:,}｜特徵 {len(feats)}", flush=True)

    rows = []
    for mins in HORIZONS:
        t0 = time.time()
        tr_masks = {c: metas[c][f"keep_{mins}"].to_numpy() == 1 for c in chunks}
        va_masks = {c: ((metas[c][f"train_{mins}"].to_numpy() == 0)
                        & np.isfinite(metas[c][f"y_{mins}"].to_numpy())) for c in chunks}
        n_tr = int(sum(m.sum() for m in tr_masks.values()))
        n_va = int(sum(m.sum() for m in va_masks.values()))
        print(f"[{mins}分] 訓練 {n_tr:,} 列／驗證 {n_va:,} 列", flush=True)

        y_tr = np.concatenate([metas[c].loc[tr_masks[c], f"y_{mins}"].to_numpy("float32")
                               for c in chunks])
        X_tr = gather(chunks, tr_masks, len(feats))
        import lightgbm as lgb
        dataset = lgb.Dataset(X_tr, label=y_tr, free_raw_data=False)
        boosters = {}
        for name, alpha in QUANTILES:
            t1 = time.time()
            boosters[name] = fit(dataset, params, alpha)
            print(f"    {name} 訓練完成 {time.time()-t1:.0f}s", flush=True)
        del dataset, X_tr, y_tr
        gc.collect()

        # 驗證逐塊預測，避免一次載入全部
        preds = {name: [] for name, _ in QUANTILES}
        cols = {k: [] for k in ("y", "ab", "ad", "total", "observed", "base")}
        for c in chunks:
            mask = va_masks[c]
            if not mask.any():
                continue
            src = np.load(FEAT / f"X_{c:02d}.npy", mmap_mode="r")
            Xva = src[mask]
            for name, _ in QUANTILES:
                preds[name].append(boosters[name].predict(Xva))
            meta = metas[c].loc[mask]
            cols["y"].append(meta[f"y_{mins}"].to_numpy("float32"))
            cols["ab"].append(meta["available_bikes"].to_numpy("float32"))
            cols["ad"].append(meta["available_docks"].to_numpy("float32"))
            cols["total"].append(meta["total_docks"].to_numpy("float32"))
            cols["observed"].append(meta[f"observed_{mins}"].to_numpy() == 1)
            cols["base"].append(meta[f"base_{mins}"].to_numpy("float32"))
            del src, Xva, meta
            gc.collect()
        merged = {k: np.concatenate(v) for k, v in cols.items()}
        p = {name: np.concatenate(v) for name, v in preds.items()}
        del preds, cols
        gc.collect()

        result = evaluate_horizon(
            mins, y_true=merged["y"], available=merged["ab"], total_docks=merged["total"],
            p10=p["p10"], p50=p["p50"], p90=p["p90"],
            baselines={"seasonal_naive": merged["base"],
                       "persistence": persistence_baseline(len(merged["y"]))},
            label_observed=merged["observed"])
        result["n_train_rows"] = n_tr
        result["seconds"] = round(time.time() - t0, 1)
        rows.append(result)
        print(f"[{mins}分] 完成，{result['seconds']:.0f}s", flush=True)

        # 保留 booster 供之後匯出候選模型
        outdir = WORK / "candidate_models"
        outdir.mkdir(exist_ok=True)
        for name, booster in boosters.items():
            booster.save_model(str(outdir / f"model_{mins}_{name}.txt"))
        del boosters, merged, p
        gc.collect()

    (WORK / "full_eval.json").write_text(
        json.dumps({"params": params, "tuning": tuned["winner"], "rows": rows},
                   ensure_ascii=False, indent=2, default=float), encoding="utf-8")
    text = format_report(rows)
    (WORK / "full_eval.md").write_text(text, encoding="utf-8")
    print("\n" + text, flush=True)
    (WORK / "candidate_models" / "meta.json").write_text(json.dumps({
        "feature_cols": feats, "horizons": HORIZONS,
        "quantiles": {"p10": 0.10, "p50": 0.50, "p90": 0.90},
        "tuned_params": params,
        "note": "ADR-122 候選模型：修正後協定（目標時間切分／逐視野遮罩／排除補值標籤）訓練；"
                "僅 1~5 月訓練列，未含 6 月，故與上線用全量模型口徑不同",
    }, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
