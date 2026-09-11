"""Pass 2：單一站塊 → 特徵矩陣（float32）+ 評估用 meta，落地成檔案。

站級統計（station_slot_p50／周轉量／行為指紋／POI／地形／天氣／介入基準）本來就每站獨立算，
所以按站分塊不改變任何數字；分塊只是讓 7 GB 記憶體跑得動 13.3M 列。

每塊輸出：
  X_{c}.npy        特徵矩陣 float32 (n, n_feats)
  meta_{c}.parquet 評估欄位 + 逐視野的 y／訓練遮罩／真實觀測旗標／seasonal naive 基準
  feats_{c}.json   特徵欄順序（跨塊必須一致）
"""
import gc, json, resource, sys, time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, "/home/claude/yb/backend")
from prediction.feature_pipeline import HORIZON_STEPS, build_training_frame
from prediction.baseline import fit_seasonal_naive, predict_seasonal_naive

TRAIN_END = "2026-05-31"
WORK = Path("/home/claude/work")
OUT = WORK / "features"
OUT.mkdir(parents=True, exist_ok=True)


def rss_gb():
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e6


def main(chunk: int):
    t0 = time.time()
    df = pd.read_parquet(WORK / "chunks" / f"chunk_{chunk:02d}.parquet")
    print(f"[chunk {chunk}] loaded {len(df):,} rows, {df['場站名稱'].nunique()} stations, "
          f"{time.time()-t0:.0f}s, RSS {rss_gb():.2f} GB", flush=True)

    t1 = time.time()
    frame, feats = build_training_frame(df, TRAIN_END, with_weather=True, with_poi=True,
                                        with_profile=True, with_terrain=True)
    del df
    gc.collect()
    print(f"[chunk {chunk}] frame {frame.shape}, {len(feats)} feats, "
          f"{time.time()-t1:.0f}s, RSS {rss_gb():.2f} GB", flush=True)

    meta = pd.DataFrame({
        "available_bikes": frame["available_bikes"].to_numpy("float32"),
        "available_docks": frame["available_docks"].to_numpy("float32"),
        "total_docks": frame["total_docks"].to_numpy("float32"),
        "is_new_station": frame["is_new_station"].to_numpy("int8"),
    })
    for _h, mins in HORIZON_STEPS.items():
        tgt = f"target_delta_{mins}"
        y = frame[tgt].to_numpy("float32")
        train = frame[f"is_train_{mins}"].to_numpy("int8")
        observed = (frame[f"target_imputed_{mins}"] == 0).to_numpy()
        # 訓練可用：在訓練期、非截斷、整段視野無調度介入、標籤為真實觀測、y 非 NaN
        keep = ((train == 1) & np.isfinite(y) & observed
                & (frame[f"is_censored_{mins}"].to_numpy() == 0)
                & (frame[f"is_rebalancing_{mins}"].to_numpy() == 0))
        meta[f"y_{mins}"] = y
        meta[f"train_{mins}"] = train
        meta[f"keep_{mins}"] = keep.astype("int8")
        meta[f"observed_{mins}"] = observed.astype("int8")
        # seasonal naive：查表本身是每站算的，分塊等價；全域中位數以本塊訓練列為準
        clean = frame[keep]
        if len(clean):
            table, gmed = fit_seasonal_naive(clean, target_col=tgt)
            meta[f"base_{mins}"] = predict_seasonal_naive(frame, table, gmed).to_numpy("float32")
        else:
            meta[f"base_{mins}"] = np.zeros(len(frame), dtype="float32")
        del clean

    X = frame[feats].to_numpy("float32")
    del frame
    gc.collect()
    np.save(OUT / f"X_{chunk:02d}.npy", X)
    meta.to_parquet(OUT / f"meta_{chunk:02d}.parquet", compression="zstd")
    (OUT / f"feats_{chunk:02d}.json").write_text(json.dumps(feats, ensure_ascii=False),
                                                 encoding="utf-8")
    print(f"[chunk {chunk}] saved X{X.shape} ({X.nbytes/1e6:.0f} MB) + meta{meta.shape}; "
          f"total {time.time()-t0:.0f}s, peak RSS {rss_gb():.2f} GB", flush=True)


if __name__ == "__main__":
    main(int(sys.argv[1]))
