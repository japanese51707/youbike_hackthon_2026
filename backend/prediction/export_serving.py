"""Reconstruct a legacy model's frozen features from the exact local training period.

Usage: PYTHONPATH=backend .venv/bin/python -m prediction.export_serving --data-dir output/youbike_parquet
Does not train or replace boosters. Fails if the reconstructed row count differs.
"""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import pandas as pd
from prediction.feature_pipeline import _attach_station_key, build_training_frame
from prediction.serving_features import export_frame, save_bundle


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--model-dir", type=Path, default=Path(__file__).parent / "_models")
    args = parser.parse_args()
    from functools import lru_cache
    from features import calendar_holiday, poi_distance
    calendar_holiday.get_holiday_feature = lru_cache(maxsize=2048)(calendar_holiday.get_holiday_feature)
    poi_distance.distances_to_poi = lru_cache(maxsize=3000)(poi_distance.distances_to_poi)
    meta = json.loads((args.model_dir / "meta.json").read_text())
    paths = [args.data_dir / f"year_month=2026-{month:02d}" / "data.parquet" for month in range(1, 7)]
    provenance = {str(p.relative_to(args.data_dir)): sha256(p.read_bytes()).hexdigest() for p in paths}
    columns = ["場站名稱", "日期", "可借車數", "可還位數", "總車柱數", "經度", "緯度"]
    print("Loading original January–June partitions", flush=True)
    df = pd.concat([pd.read_parquet(p, columns=columns) for p in paths], ignore_index=True)
    df = _attach_station_key(df)
    stations, rows = {}, 0
    # Station statistics are independent; small groups avoid constructing a 13M × 45 frame.
    grouped = df.groupby("station_key", sort=True)
    for index, (key, group) in enumerate(grouped):
        frame, _ = build_training_frame(group, "2026-12-31", with_weather=False,
                                        with_poi=True, with_profile=True, with_terrain=True)
        rows += len(frame)
        stations.update(export_frame(frame, meta["feature_cols"]))
        if index % 100 == 0:
            print(f"{index + 1}/{len(grouped)} stations; {rows} reconstructed rows", flush=True)
    if rows != meta["train_rows"]:
        raise ValueError(f"Training rows mismatch: {rows} != {meta['train_rows']}; refusing publication")
    path = save_bundle(args.model_dir, meta["feature_cols"], stations,
                       str(df["日期"].min()), str(df["日期"].max()),
                       {"kind": "legacy_reconstruction", "partition_sha256": provenance,
                        "reconstructed_rows": rows})
    print(f"Saved {path}: {len(stations)} stations; {path.stat().st_size} bytes", flush=True)


if __name__ == "__main__":
    main()
