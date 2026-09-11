"""Pass 3a：修正後協定的時序 CV 超參數搜尋（ADR-110 + ADR-122）。

與修正前的差別：
  - 每一折各自 build_training_frame(fit_mask=該折訓練月)，統計量不跨折共用
  - 折的切分依「標籤的目標時間」，不依輸入時間
  - 訓練列排除截斷、整段視野的調度介入、補值標籤
  - 選參目標：正常區間（可借≥1 且 可還≥1）且標籤為真實觀測的 P50 MAE，折平均

成本控制：以站點子集選參（ADR-110 本來就以單一代表視野選參），最終評估用全量全站。
"""
import json, random, sys, time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, "/home/claude/yb/backend")
sys.path.insert(0, "/home/claude/work")
from prediction.feature_pipeline import build_training_frame

TRAIN_END = "2026-05-31"
HORIZON = 60                      # 代表視野
TGT = f"target_delta_{HORIZON}"
FOLDS = [([1, 2, 3], 4), ([1, 2, 3, 4], 5)]
WORK = Path("/home/claude/work")

SPACE = {
    "n_estimators": [200, 300, 500, 800],
    "learning_rate": [0.02, 0.03, 0.05, 0.1],
    "num_leaves": [15, 31, 63, 127],
    "min_child_samples": [20, 50, 100, 200],
    "subsample": [0.7, 0.8, 1.0],
    "colsample_bytree": [0.7, 0.8, 1.0],
    "reg_lambda": [0.0, 1.0, 5.0],
}
DEFAULT = {"n_estimators": 300, "learning_rate": 0.05, "num_leaves": 31,
           "min_child_samples": 50, "subsample": 1.0, "colsample_bytree": 1.0,
           "reg_lambda": 0.0}
# ADR-110 當初（以有洩漏的協定）選出的參數，一併放進候選比較
ADR110 = {"n_estimators": 300, "learning_rate": 0.1, "num_leaves": 127,
          "min_child_samples": 200, "subsample": 0.7, "colsample_bytree": 0.8,
          "reg_lambda": 0.0}


def mae(a, b):
    return float(np.mean(np.abs(np.asarray(a) - np.asarray(b))))


def build_folds(chunks):
    df = pd.concat([pd.read_parquet(WORK / "chunks" / f"chunk_{c:02d}.parquet") for c in chunks],
                   ignore_index=True)
    print(f"tuning subset: {len(df):,} rows, {df['場站名稱'].nunique()} stations", flush=True)
    out = []
    for train_months, valid_month in FOLDS:
        t0 = time.time()
        frame, feats = build_training_frame(
            df, TRAIN_END, with_weather=True, with_poi=True, with_profile=True,
            with_terrain=True,
            fit_mask=lambda f, m=train_months:
                (f["dt"] + pd.Timedelta(minutes=HORIZON)).dt.month.isin(m))
        tmonth = (frame["dt"] + pd.Timedelta(minutes=HORIZON)).dt.month
        y = frame[TGT].to_numpy("float32")
        finite = np.isfinite(y)
        observed = (frame[f"target_imputed_{HORIZON}"] == 0).to_numpy()
        keep = (finite & observed
                & (frame[f"is_censored_{HORIZON}"].to_numpy() == 0)
                & (frame[f"is_rebalancing_{HORIZON}"].to_numpy() == 0))
        tr = keep & tmonth.isin(train_months).to_numpy()
        va = finite & observed & (tmonth == valid_month).to_numpy()
        ab = frame["available_bikes"].to_numpy("float32")
        ad = frame["available_docks"].to_numpy("float32")
        normal = va & (ab >= 1) & (ad >= 1)
        X = frame[feats].to_numpy("float32")
        out.append({"Xtr": X[tr], "ytr": y[tr], "Xva": X[va], "yva": y[va],
                    "normal": normal[va], "feats": feats})
        print(f"  fold {train_months}->{valid_month}: train {tr.sum():,} / valid {va.sum():,}"
              f" (normal {normal.sum():,}) built in {time.time()-t0:.0f}s", flush=True)
        del frame, X
    return out


def cv_score(folds, params):
    import lightgbm as lgb
    from lgbm_util import fit
    scores = []
    for f in folds:
        ds = lgb.Dataset(f["Xtr"], label=f["ytr"], free_raw_data=False)
        booster = fit(ds, params, 0.5)
        pred = booster.predict(f["Xva"])
        scores.append(mae(f["yva"][f["normal"]], pred[f["normal"]]))
        del ds, booster
    return float(np.mean(scores))


def main():
    chunks = [int(c) for c in sys.argv[1].split(",")] if len(sys.argv) > 1 else [0, 1]
    trials = int(sys.argv[2]) if len(sys.argv) > 2 else 12
    folds = build_folds(chunks)

    results = {}
    for name, params in (("default", DEFAULT), ("adr110", ADR110)):
        t0 = time.time()
        results[name] = {"params": params, "cv_mae": cv_score(folds, params)}
        print(f"[baseline-params] {name}: CV {results[name]['cv_mae']:.4f} "
              f"({time.time()-t0:.0f}s)", flush=True)

    random.seed(42)
    best_name, best = "default", results["default"]["cv_mae"]
    for i in range(trials):
        params = {k: random.choice(v) for k, v in SPACE.items()}
        t0 = time.time()
        score = cv_score(folds, params)
        mark = ""
        if score < best:
            best, best_name = score, f"trial{i+1}"
            results[best_name] = {"params": params, "cv_mae": score}
            mark = "  ★新最佳"
        print(f"  trial {i+1:>2}/{trials}: CV {score:.4f} ({time.time()-t0:.0f}s){mark}",
              flush=True)

    winner = results[best_name]
    print(f"\n最佳：{best_name} CV {winner['cv_mae']:.4f}")
    print(f"參數：{winner['params']}")
    print(f"對照 default {results['default']['cv_mae']:.4f} / "
          f"ADR-110 {results['adr110']['cv_mae']:.4f}")
    (WORK / "tuned_params.json").write_text(
        json.dumps({"winner": best_name, "results": results,
                    "subset_chunks": chunks, "horizon": HORIZON}, ensure_ascii=False, indent=2),
        encoding="utf-8")


if __name__ == "__main__":
    main()
