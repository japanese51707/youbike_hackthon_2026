"""
離線批次算全站行為指紋，存快取（ADR-104/113 靜態層）
=====================================================
讀 S3 歷史，逐站 compute_profile，存 backend/features/_profile_cache.json。
比照 _elevation_cache.json —— 靜態/半靜態資料預算好，API 回快取不每次現算（省資源）。

鍵：station_id（API 以此查）。值：compute_profile + classify_station_type 的結果。
更新頻率：每天/每週離線重跑一次（行為指紋是六個月歷史算的，不需即時）。

用法：.venv/bin/python tools/build_profile_cache.py
"""
from __future__ import annotations
import sys
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
import warnings
warnings.filterwarnings("ignore")

import pandas as pd
from core.data.historical import HistoricalDataSource
from features.station_profile import compute_profile, classify_station_type

_CACHE = ROOT / "backend" / "features" / "_profile_cache.json"


def main():
    h = HistoricalDataSource()
    df = h._df().copy()   # 整月全站 30 分格
    df["timestamp"] = df["timestamp"].astype(str)
    print(f"歷史：{df['station_id'].nunique()} 站、{len(df):,} 列", flush=True)

    cache = {}
    n = 0
    for sid, g in df.groupby("station_id"):
        series = g.sort_values("timestamp")[
            ["timestamp", "available_bikes", "available_docks"]].copy()
        total = int(g["total_docks"].median()) if "total_docks" in g else None
        prof = compute_profile(series, total)
        prof["station_type_label"] = classify_station_type(prof)
        cache[str(sid)] = prof
        n += 1
        if n % 300 == 0:
            print(f"  已算 {n} 站…", flush=True)

    _CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    non_sparse = sum(1 for v in cache.values() if not v.get("sparse"))
    print(f"\n✓ 存 {_CACHE}")
    print(f"  共 {len(cache)} 站（{non_sparse} 站有足夠歷史、{len(cache)-non_sparse} 站 sparse）")


if __name__ == "__main__":
    main()
