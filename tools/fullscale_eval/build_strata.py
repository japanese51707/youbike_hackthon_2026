"""補一份「站別身分 + 訓練期周轉量」的 meta，供分層分析用。

X_*.npy 不變，只多產出 strata_{c}.parquet：
  station_code  站點在本塊內的編號（配合 stations_{c}.json 還原站名）
  turnover      訓練期逐格絕對變化平均（ADR-109 的周轉量定義，只用訓練期算）
  total_docks   柱數（分層的另一個候選維度）
"""
import gc, json, sys, time
from pathlib import Path
import numpy as np, pandas as pd

sys.path.insert(0, "/home/claude/yb/backend")
from prediction.feature_pipeline import build_training_frame

TRAIN_END = "2026-05-31"
WORK = Path("/home/claude/work"); OUT = WORK / "features"


def main(chunk: int):
    t0 = time.time()
    df = pd.read_parquet(WORK / "chunks" / f"chunk_{chunk:02d}.parquet")
    frame, _ = build_training_frame(df, TRAIN_END, with_weather=False, with_poi=False,
                                    with_profile=False, with_terrain=False)
    del df; gc.collect()
    keys = frame["station_key"].astype("category")
    strata = pd.DataFrame({
        "station_code": keys.cat.codes.to_numpy("int16"),
        "turnover": frame["station_turnover"].to_numpy("float32"),
        "total_docks": frame["total_docks"].to_numpy("float32"),
    })
    strata.to_parquet(OUT / f"strata_{chunk:02d}.parquet", compression="zstd")
    (OUT / f"stations_{chunk:02d}.json").write_text(
        json.dumps(list(keys.cat.categories), ensure_ascii=False), encoding="utf-8")
    print(f"[chunk {chunk}] strata {strata.shape}, {len(keys.cat.categories)} stations, "
          f"{time.time()-t0:.0f}s", flush=True)


if __name__ == "__main__":
    main(int(sys.argv[1]))
