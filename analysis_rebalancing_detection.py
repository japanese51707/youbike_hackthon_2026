"""
調度介入痕跡辨識分析
====================
核心邏輯：
- 在 30 分鐘間隔內，一個站的「可借車數」自然增長（使用者還車）有合理上限
- 如果可借車數在 30 分鐘內突增超過合理閾值 → 極大可能是調度員補車
- 反之，可借車數在 30 分鐘內突降超過合理閾值 → 可能是調度員取車

方法：
1. 計算每站每個時段的「可借車數變化量」（delta）
2. 根據站點大小和時段，推算「自然還車速率上限」
3. delta 超過上限 → 標記為「疑似調度補車」
4. delta 低於下限（負向超出自然借車速率）→ 標記為「疑似調度取車」
"""

import pandas as pd
import numpy as np
from pathlib import Path

OUTPUT_DIR = Path("output")
PARQUET_DIR = OUTPUT_DIR / "youbike_parquet"
RESULTS_DIR = OUTPUT_DIR / "analysis_results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


def load_all_data():
    """載入所有月份的 Parquet 資料"""
    dfs = []
    for partition in sorted(PARQUET_DIR.iterdir()):
        if partition.is_dir() and "year_month=" in partition.name:
            ym = partition.name.split("=")[1]
            df = pd.read_parquet(partition / "data.parquet")
            df["year_month"] = ym
            dfs.append(df)
    return pd.concat(dfs, ignore_index=True)


def detect_rebalancing(df):
    """辨識調度介入痕跡"""
    print("📊 計算每站每時段的車輛變化量...")

    # 轉換日期並排序
    df["dt"] = pd.to_datetime(df["日期"])
    df = df.sort_values(["場站名稱", "dt"]).reset_index(drop=True)

    # 計算每站的可借車數變化量（與前一筆的差異）
    df["delta_available"] = df.groupby("場站名稱")["可借車數"].diff()

    # 計算時間差（秒），確保是連續的 30 分鐘間隔
    df["time_diff"] = df.groupby("場站名稱")["dt"].diff().dt.total_seconds()

    # 只保留正常 30 分鐘間隔的資料（允許 25~35 分鐘的誤差）
    mask_valid = (df["time_diff"] >= 1500) & (df["time_diff"] <= 2100)
    df_valid = df[mask_valid].copy()

    print(f"   有效連續記錄數: {len(df_valid):,}")

    # === 定義閾值 ===
    # 自然還車速率上限：根據站點大小
    # 大站（>50格）在尖峰時段 30 分鐘最多自然還車約 8~10 台
    # 中站（20~50格）約 5~7 台
    # 小站（<20格）約 3~4 台
    # 調度補車通常一次會放 5~15 台
    # 保守閾值：30 分鐘內增加超過 8 台 → 疑似調度補車

    REBALANCE_ADD_THRESHOLD = 8   # 正向突增閾值
    REBALANCE_REMOVE_THRESHOLD = -8  # 負向突降閾值

    # 標記疑似調度介入
    df_valid["疑似補車"] = (df_valid["delta_available"] >= REBALANCE_ADD_THRESHOLD).astype(int)
    df_valid["疑似取車"] = (df_valid["delta_available"] <= REBALANCE_REMOVE_THRESHOLD).astype(int)
    df_valid["疑似調度"] = ((df_valid["疑似補車"] == 1) | (df_valid["疑似取車"] == 1)).astype(int)

    return df_valid


def analyze_results(df_valid):
    """分析調度介入的統計結果"""
    print("\n" + "=" * 60)
    print("📋 調度介入辨識結果")
    print("=" * 60)

    total_records = len(df_valid)
    rebalance_records = df_valid["疑似調度"].sum()
    add_records = df_valid["疑似補車"].sum()
    remove_records = df_valid["疑似取車"].sum()

    print(f"\n  總有效記錄數: {total_records:,}")
    print(f"  疑似調度介入: {rebalance_records:,} ({rebalance_records/total_records*100:.2f}%)")
    print(f"    - 疑似補車: {add_records:,} ({add_records/total_records*100:.2f}%)")
    print(f"    - 疑似取車: {remove_records:,} ({remove_records/total_records*100:.2f}%)")

    # 按月份統計
    print("\n  === 按月份 ===")
    monthly = df_valid.groupby("year_month").agg(
        總記錄=("疑似調度", "count"),
        調度次數=("疑似調度", "sum"),
        補車次數=("疑似補車", "sum"),
        取車次數=("疑似取車", "sum"),
    )
    monthly["調度比例%"] = (monthly["調度次數"] / monthly["總記錄"] * 100).round(2)
    print(monthly.to_string())

    # 按小時統計（調度的時間分佈）
    print("\n  === 調度時間分佈（小時）===")
    df_rebalanced = df_valid[df_valid["疑似調度"] == 1].copy()
    df_rebalanced["hour"] = df_rebalanced["dt"].dt.hour
    hourly = df_rebalanced.groupby("hour").size()
    print(hourly.to_string())

    # 找出最常被調度的站
    print("\n  === 最常被調度的 Top 20 站點 ===")
    station_rebalance = df_valid.groupby("場站名稱").agg(
        總記錄=("疑似調度", "count"),
        調度次數=("疑似調度", "sum"),
        補車次數=("疑似補車", "sum"),
        取車次數=("疑似取車", "sum"),
    )
    station_rebalance["調度比例%"] = (station_rebalance["調度次數"] / station_rebalance["總記錄"] * 100).round(2)
    top_stations = station_rebalance.sort_values("調度次數", ascending=False).head(20)
    print(top_stations.to_string())

    # 按行政區統計
    print("\n  === 按行政區調度頻率 ===")
    district_rebalance = df_valid.groupby("行政區").agg(
        總記錄=("疑似調度", "count"),
        調度次數=("疑似調度", "sum"),
    )
    district_rebalance["調度比例%"] = (district_rebalance["調度次數"] / district_rebalance["總記錄"] * 100).round(2)
    district_rebalance = district_rebalance.sort_values("調度比例%", ascending=False)
    print(district_rebalance.to_string())

    # 補車量的分佈
    print("\n  === 疑似補車量分佈 ===")
    add_amounts = df_valid[df_valid["疑似補車"] == 1]["delta_available"]
    print(f"  補車量統計:")
    print(f"    平均: {add_amounts.mean():.1f} 台")
    print(f"    中位數: {add_amounts.median():.1f} 台")
    print(f"    最大: {add_amounts.max():.0f} 台")
    print(f"    標準差: {add_amounts.std():.1f}")

    print("\n  === 疑似取車量分佈 ===")
    remove_amounts = df_valid[df_valid["疑似取車"] == 1]["delta_available"]
    print(f"  取車量統計:")
    print(f"    平均: {remove_amounts.mean():.1f} 台")
    print(f"    中位數: {remove_amounts.median():.1f} 台")
    print(f"    最小: {remove_amounts.min():.0f} 台")
    print(f"    標準差: {remove_amounts.std():.1f}")

    return station_rebalance, df_rebalanced


def save_results(df_valid, station_rebalance):
    """儲存分析結果"""
    # 存標記後的完整資料
    output_cols = ["日期", "城市", "行政區", "場站名稱", "總車柱數",
                   "可借車數", "可還位數", "經度", "緯度",
                   "delta_available", "疑似補車", "疑似取車", "疑似調度", "year_month"]
    df_valid[output_cols].to_parquet(
        RESULTS_DIR / "rebalancing_detected.parquet",
        engine="pyarrow",
        index=False,
    )

    # 存站點調度統計
    station_rebalance.to_csv(RESULTS_DIR / "station_rebalance_stats.csv", encoding="utf-8-sig")

    print(f"\n💾 結果已儲存:")
    print(f"   {RESULTS_DIR / 'rebalancing_detected.parquet'}")
    print(f"   {RESULTS_DIR / 'station_rebalance_stats.csv'}")


def main():
    print("=" * 60)
    print("調度介入痕跡辨識分析")
    print("=" * 60)

    print("\n📂 載入資料...")
    df = load_all_data()
    print(f"   總筆數: {len(df):,}")

    df_valid = detect_rebalancing(df)
    station_rebalance, df_rebalanced = analyze_results(df_valid)
    save_results(df_valid, station_rebalance)

    print("\n✅ 分析完成！")


if __name__ == "__main__":
    main()
