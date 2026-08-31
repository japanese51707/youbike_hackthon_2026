"""
動態目標水位 + 潮汐 pattern 分析
================================
1. 動態目標水位：按站 × 星期 × 時段，計算理想的借用率
2. 潮汐分析：按時段計算各行政區的淨流量方向
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


def analyze_target_level(df):
    """
    計算動態目標水位
    - 核心概念：每站在不同星期×時段，「使用者實際需要借車的比例」不同
    - 目標水位 = 讓空站/滿站機率最低的車輛比例
    """
    print("\n" + "=" * 60)
    print("📊 動態目標水位分析")
    print("=" * 60)

    df["dt"] = pd.to_datetime(df["日期"])
    df["hour"] = df["dt"].dt.hour
    df["dayofweek"] = df["dt"].dt.dayofweek  # 0=Monday, 6=Sunday
    df["is_weekday"] = (df["dayofweek"] < 5).astype(int)

    # 計算每站 × 平日/假日 × 小時 的平均借用率
    target_level = df.groupby(["場站名稱", "行政區", "is_weekday", "hour"]).agg(
        平均借用率=("借用率", "mean"),
        平均空位率=("空位率", "mean"),
        空站次數=("是否空站", "sum"),
        滿站次數=("是否滿站", "sum"),
        記錄數=("借用率", "count"),
        總車柱數=("總車柱數", "first"),
    ).reset_index()

    # 理想目標水位 = 平均借用率 + buffer
    # buffer 的概念：如果一個站借用率平均 60%（大家都要借車），
    # 那目標水位應該維持在 70~80%（多留一些車給使用者借）
    # 如果一個站借用率平均 30%（大家都在還車），
    # 那目標水位應該維持在 20~30%（多留空位給使用者還）
    target_level["目標借用率"] = target_level["平均借用率"] + 10  # buffer +10%
    target_level["目標借用率"] = target_level["目標借用率"].clip(15, 85)  # 不低於15%不高於85%

    # 顯示一些例子
    print("\n  === 捷運站範例（平日）===")
    sample_stations = ["捷運南勢角站(4號出口)", "捷運新莊站(1號出口)", "板橋車站"]
    for station in sample_stations:
        st_data = target_level[
            (target_level["場站名稱"] == station) & (target_level["is_weekday"] == 1)
        ].sort_values("hour")
        if len(st_data) > 0:
            print(f"\n  {station}（平日）:")
            print(f"  {'時段':<6} {'平均借用率':<10} {'目標借用率':<10} {'空站次數':<8} {'滿站次數'}")
            for _, row in st_data.iterrows():
                print(f"  {int(row['hour']):02d}:00  {row['平均借用率']:>7.1f}%  {row['目標借用率']:>7.1f}%  "
                      f"{int(row['空站次數']):>6}  {int(row['滿站次數']):>6}")

    # 儲存
    target_level.to_parquet(RESULTS_DIR / "dynamic_target_level.parquet", index=False)
    print(f"\n💾 已儲存: {RESULTS_DIR / 'dynamic_target_level.parquet'}")
    print(f"   共 {len(target_level):,} 筆（站 × 平日假日 × 時段）")

    return target_level, df


def analyze_tidal_pattern(df):
    """
    潮汐 pattern 分析
    - 計算每站每時段的「淨流量」= 上一時段可借車數 - 當前可借車數
    - 正值 = 車被借走（流出）
    - 負值 = 車被還回（流入）
    """
    print("\n" + "=" * 60)
    print("📊 潮汐 Pattern 分析")
    print("=" * 60)

    df = df.sort_values(["場站名稱", "dt"]).reset_index(drop=True)

    # 計算淨流量（前一時段 - 當前 = 被借走的數量）
    df["net_flow"] = df.groupby("場站名稱")["可借車數"].diff() * -1
    # 正值=有人借走, 負值=有人還回

    # 過濾有效間隔
    df["time_diff"] = df.groupby("場站名稱")["dt"].diff().dt.total_seconds()
    df_valid = df[(df["time_diff"] >= 1500) & (df["time_diff"] <= 2100)].copy()

    # === 按行政區 × 小時 × 平日/假日 彙總 ===
    tidal_district = df_valid.groupby(["行政區", "is_weekday", "hour"]).agg(
        平均淨流出=("net_flow", "mean"),
        淨流出標準差=("net_flow", "std"),
        記錄數=("net_flow", "count"),
    ).reset_index()

    # 顯示結果
    print("\n  === 平日各時段淨流量方向（正=借出/流出，負=還車/流入）===")
    print("  行政區排列順序：以早上 7~9 點流出量排序（通勤站）")

    # 找出早上通勤流出最大的行政區
    morning_flow = tidal_district[
        (tidal_district["is_weekday"] == 1) &
        (tidal_district["hour"].isin([7, 8]))
    ].groupby("行政區")["平均淨流出"].mean().sort_values(ascending=False)

    print(f"\n  {'行政區':<8} {'07~08流出':<10} {'特性'}")
    print(f"  {'-'*40}")
    for district, flow in morning_flow.head(10).items():
        if flow > 0.3:
            char = "🔴 通勤借車區（早上流出）"
        elif flow < -0.3:
            char = "🔵 通勤還車區（早上流入）"
        else:
            char = "⚪ 混合型"
        print(f"  {district:<8} {flow:>+.2f} 台/站  {char}")

    print(f"\n  ...")

    for district, flow in morning_flow.tail(10).items():
        if flow > 0.3:
            char = "🔴 通勤借車區（早上流出）"
        elif flow < -0.3:
            char = "🔵 通勤還車區（早上流入）"
        else:
            char = "⚪ 混合型"
        print(f"  {district:<8} {flow:>+.2f} 台/站  {char}")

    # === 尖峰時段分析 ===
    print("\n  === 尖峰時段辨識（平日）===")
    overall_hourly = df_valid[df_valid["is_weekday"] == 1].groupby("hour").agg(
        平均淨流出=("net_flow", "mean"),
        空站比例=("是否空站", "mean"),
        滿站比例=("是否滿站", "mean"),
    )
    overall_hourly["空站比例%"] = (overall_hourly["空站比例"] * 100).round(2)
    overall_hourly["滿站比例%"] = (overall_hourly["滿站比例"] * 100).round(2)

    print(f"\n  {'時段':<6} {'平均淨流出':<12} {'空站比例':<10} {'滿站比例':<10} {'狀態'}")
    print(f"  {'-'*55}")
    for hour, row in overall_hourly.iterrows():
        if row["空站比例%"] > 2.0 or row["滿站比例%"] > 2.0:
            status = "⚠️ 壓力時段"
        elif abs(row["平均淨流出"]) > 0.3:
            status = "📈 流動活躍"
        else:
            status = ""
        print(f"  {hour:02d}:00  {row['平均淨流出']:>+8.3f} 台  "
              f"{row['空站比例%']:>6.2f}%  {row['滿站比例%']:>6.2f}%   {status}")

    # === 假日 vs 平日對比 ===
    print("\n  === 平日 vs 假日 空滿站比例 ===")
    weekday_data = df_valid[df_valid["is_weekday"] == 1]
    weekend_data = df_valid[df_valid["is_weekday"] == 0]
    wd_empty = weekday_data["是否空站"].mean() * 100
    wd_full = weekday_data["是否滿站"].mean() * 100
    we_empty = weekend_data["是否空站"].mean() * 100
    we_full = weekend_data["是否滿站"].mean() * 100
    print(f"  平日 - 空站率: {wd_empty:.2f}%, 滿站率: {wd_full:.2f}%")
    print(f"  假日 - 空站率: {we_empty:.2f}%, 滿站率: {we_full:.2f}%")

    # 儲存
    tidal_district.to_parquet(RESULTS_DIR / "tidal_pattern_by_district.parquet", index=False)

    # 另外存尖峰時段摘要
    overall_hourly.to_csv(RESULTS_DIR / "peak_hours_summary.csv", encoding="utf-8-sig")

    print(f"\n💾 已儲存:")
    print(f"   {RESULTS_DIR / 'tidal_pattern_by_district.parquet'}")
    print(f"   {RESULTS_DIR / 'peak_hours_summary.csv'}")

    return tidal_district


def main():
    print("=" * 60)
    print("動態目標水位 + 潮汐 Pattern 分析")
    print("=" * 60)

    print("\n📂 載入資料...")
    df = load_all_data()
    print(f"   總筆數: {len(df):,}")

    target_level, df = analyze_target_level(df)
    tidal = analyze_tidal_pattern(df)

    print("\n" + "=" * 60)
    print("✅ 全部分析完成！")
    print("=" * 60)


if __name__ == "__main__":
    main()
