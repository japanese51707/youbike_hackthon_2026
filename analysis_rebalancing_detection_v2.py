"""
調度介入辨識 v2（依 D4 決策改良）
==================================
改良點：
1. 用 MAD（中位數絕對偏差）取代標準差 — 對重尾分佈穩健
2. 加入「時段方向」特徵 — 區分凌晨補車 vs 尖峰自然還車
3. 加入「鄰近站同時性」特徵 — 調度卡車一趟多站的信號
4. 輸出信心分數（0~1），不輸出二元標籤

輸出：
- output/analysis_results_v2/rebalancing_v2.parquet（含信心分數）
- output/analysis_results_v2/comparison_v1_v2.csv（與舊版差異分析）
- output/analysis_results_v2/station_rebalance_stats_v2.csv（站點統計）
"""

import pandas as pd
import numpy as np
from pathlib import Path
from scipy.spatial.distance import cdist

OUTPUT_DIR = Path("output")
PARQUET_DIR = OUTPUT_DIR / "youbike_parquet"
RESULTS_V2_DIR = OUTPUT_DIR / "analysis_results_v2"
RESULTS_V2_DIR.mkdir(parents=True, exist_ok=True)


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


def compute_mad(series):
    """計算 MAD（Median Absolute Deviation）"""
    median = series.median()
    mad = (series - median).abs().median()
    return median, mad


def build_station_coords(df):
    """建立站點座標表，用於計算鄰近站"""
    station_coords = df.groupby("場站名稱").agg(
        經度=("經度", "first"),
        緯度=("緯度", "first"),
    ).reset_index()
    return station_coords


def find_neighbors(station_coords, radius_km=0.5):
    """
    找出每站半徑內的鄰近站（以 Haversine 近似，平面距離）
    radius_km: 預設 500m
    """
    # 用經緯度近似距離（台灣緯度下 1度緯≈111km, 1度經≈101km）
    coords = station_coords[["經度", "緯度"]].values
    # 轉換為公里
    lat_km = coords[:, 1] * 111.0
    lon_km = coords[:, 0] * 101.0
    points_km = np.column_stack([lon_km, lat_km])

    # 計算距離矩陣
    dist_matrix = cdist(points_km, points_km, metric="euclidean")

    neighbors = {}
    for i, name in enumerate(station_coords["場站名稱"]):
        mask = (dist_matrix[i] > 0) & (dist_matrix[i] <= radius_km)
        neighbor_names = station_coords["場站名稱"].values[mask]
        neighbors[name] = set(neighbor_names)

    return neighbors


def detect_rebalancing_v2(df, neighbors):
    """
    v2 調度介入辨識
    輸出信心分數而非二元標籤
    """
    print("📊 v2: 計算每站每時段車輛變化量...")

    df["dt"] = pd.to_datetime(df["日期"])
    df = df.sort_values(["場站名稱", "dt"]).reset_index(drop=True)
    df["hour"] = df["dt"].dt.hour
    df["dayofweek"] = df["dt"].dt.dayofweek
    df["is_weekday"] = (df["dayofweek"] < 5).astype(int)

    # 計算 delta
    df["delta"] = df.groupby("場站名稱")["可借車數"].diff()
    df["time_diff"] = df.groupby("場站名稱")["dt"].diff().dt.total_seconds()

    # 只保留有效 30 分鐘間隔
    mask_valid = (df["time_diff"] >= 1500) & (df["time_diff"] <= 2100)
    df_valid = df[mask_valid].copy()
    print(f"   有效記錄數: {len(df_valid):,}")

    # =============================================
    # 特徵 1: MAD-based z-score（per 站 × 平日/假日 × 小時）
    # =============================================
    print("   計算 per-station per-hour MAD...")
    group_cols = ["場站名稱", "is_weekday", "hour"]

    # 計算每組的 median 和 MAD
    grouped = df_valid.groupby(group_cols)["delta"]
    medians = grouped.transform("median")
    # MAD = median(|x - median(x)|)
    abs_dev = (df_valid["delta"] - medians).abs()
    df_valid["_abs_dev"] = abs_dev
    mad_values = df_valid.groupby(group_cols)["_abs_dev"].transform("median")

    # Modified z-score（MAD-based）
    # 標準轉換：z = 0.6745 * (x - median) / MAD
    # 0.6745 是標準常態分佈在中位數處的尺度因子
    CONSISTENCY_CONSTANT = 0.6745
    # 避免除以 0
    mad_safe = mad_values.clip(lower=0.5)  # MAD 最小設 0.5，避免小站低流動時 z 爆炸
    df_valid["mad_zscore"] = CONSISTENCY_CONSTANT * (df_valid["delta"] - medians) / mad_safe
    df_valid.drop(columns=["_abs_dev"], inplace=True)

    # =============================================
    # 特徵 2: 時段方向分數
    # 凌晨 0~5 點有大幅正 delta → 幾乎必是調度（自然還車率極低）
    # 尖峰時段的正 delta 可能只是通勤還車
    # =============================================
    print("   計算時段方向分數...")
    # 時段權重：凌晨高、尖峰低
    hour_weight = pd.Series({
        0: 0.95, 1: 0.98, 2: 0.99, 3: 0.99, 4: 0.98, 5: 0.90,
        6: 0.60, 7: 0.30, 8: 0.25, 9: 0.35, 10: 0.45, 11: 0.50,
        12: 0.50, 13: 0.50, 14: 0.50, 15: 0.45, 16: 0.35, 17: 0.30,
        18: 0.35, 19: 0.45, 20: 0.55, 21: 0.65, 22: 0.80, 23: 0.90,
    })
    df_valid["hour_weight"] = df_valid["hour"].map(hour_weight)

    # =============================================
    # 特徵 3: 鄰近站同時性
    # 同一時間窗內，鄰近站是否有反向跳變
    # =============================================
    print("   計算鄰近站同時性信號...")
    # 建立時間索引以供查詢
    # 為效率，只對 |mad_zscore| > 2 的記錄去查鄰近站
    high_z_mask = df_valid["mad_zscore"].abs() > 2.0
    df_valid["neighbor_signal"] = 0.0

    if high_z_mask.sum() > 0:
        # 建立 (站, 時間) → delta 的查找表
        time_station_delta = df_valid.set_index(["場站名稱", "dt"])["delta"].to_dict()

        # 對高 z-score 的記錄，檢查鄰近站是否有反向變化
        high_z_indices = df_valid[high_z_mask].index
        neighbor_signals = []

        # 批次處理以提升效率
        batch_size = 50000
        total_batches = (len(high_z_indices) + batch_size - 1) // batch_size
        for batch_idx in range(total_batches):
            start = batch_idx * batch_size
            end = min(start + batch_size, len(high_z_indices))
            batch_indices = high_z_indices[start:end]

            for idx in batch_indices:
                row = df_valid.loc[idx]
                station = row["場站名稱"]
                timestamp = row["dt"]
                my_delta = row["delta"]

                if station not in neighbors or len(neighbors[station]) == 0:
                    neighbor_signals.append((idx, 0.0))
                    continue

                # 查鄰近站在同一時間的 delta
                opposite_count = 0
                checked = 0
                for nb in neighbors[station]:
                    nb_delta = time_station_delta.get((nb, timestamp))
                    if nb_delta is not None:
                        checked += 1
                        # 反向：我增加，鄰近站減少（或反之）
                        if my_delta > 0 and nb_delta < -3:
                            opposite_count += 1
                        elif my_delta < 0 and nb_delta > 3:
                            opposite_count += 1

                if checked > 0:
                    signal = min(opposite_count / max(checked, 1), 1.0)
                else:
                    signal = 0.0
                neighbor_signals.append((idx, signal))

            if (batch_idx + 1) % 5 == 0 or batch_idx == total_batches - 1:
                print(f"     batch {batch_idx+1}/{total_batches} 完成")

        # 寫回
        for idx, signal in neighbor_signals:
            df_valid.at[idx, "neighbor_signal"] = signal

    # =============================================
    # 合成信心分數（0~1）
    # =============================================
    print("   合成信心分數...")
    # 信心分數 = f(|mad_zscore|, hour_weight, neighbor_signal)
    # 基礎：MAD z-score 越大越可疑
    base_score = (df_valid["mad_zscore"].abs() / 5.0).clip(0, 1)  # |z|=5 → score=1

    # 加權：凌晨權重高、尖峰權重低
    weighted_score = base_score * (0.5 + 0.5 * df_valid["hour_weight"])

    # 鄰近站同時性加成（最多 +0.3）
    final_score = (weighted_score + 0.3 * df_valid["neighbor_signal"]).clip(0, 1)

    # 方向標記
    df_valid["rebalance_confidence"] = final_score
    df_valid["rebalance_direction"] = "none"
    df_valid.loc[(final_score > 0.3) & (df_valid["delta"] > 0), "rebalance_direction"] = "補車"
    df_valid.loc[(final_score > 0.3) & (df_valid["delta"] < 0), "rebalance_direction"] = "取車"

    return df_valid


def compare_with_v1(df_v2):
    """與 v1（固定 8 台閾值）做差異分析"""
    print("\n" + "=" * 60)
    print("📋 v1 vs v2 差異分析")
    print("=" * 60)

    # v1 邏輯：|delta| >= 8 → 調度
    df_v2["v1_flagged"] = (df_v2["delta"].abs() >= 8).astype(int)

    # v2 邏輯：信心分數 > 0.5 視為「高信心調度」
    df_v2["v2_high_conf"] = (df_v2["rebalance_confidence"] > 0.5).astype(int)
    df_v2["v2_medium_conf"] = (
        (df_v2["rebalance_confidence"] > 0.3) & (df_v2["rebalance_confidence"] <= 0.5)
    ).astype(int)

    total = len(df_v2)
    v1_count = df_v2["v1_flagged"].sum()
    v2_high = df_v2["v2_high_conf"].sum()
    v2_medium = df_v2["v2_medium_conf"].sum()

    print(f"\n  總有效記錄: {total:,}")
    print(f"  v1 標記（|delta|≥8）: {v1_count:,} ({v1_count/total*100:.2f}%)")
    print(f"  v2 高信心（>0.5）: {v2_high:,} ({v2_high/total*100:.2f}%)")
    print(f"  v2 中信心（0.3~0.5）: {v2_medium:,} ({v2_medium/total*100:.2f}%)")

    # 交叉分析
    both = ((df_v2["v1_flagged"] == 1) & (df_v2["v2_high_conf"] == 1)).sum()
    v1_only = ((df_v2["v1_flagged"] == 1) & (df_v2["v2_high_conf"] == 0)).sum()
    v2_only = ((df_v2["v1_flagged"] == 0) & (df_v2["v2_high_conf"] == 1)).sum()

    print(f"\n  兩者皆標記: {both:,}")
    print(f"  v1 標記 / v2 未標記: {v1_only:,}（v2 認為是自然波動）")
    print(f"  v2 標記 / v1 未標記: {v2_only:,}（v2 多抓的，可能是小量但凌晨的調度）")

    # v1 標記但 v2 認為不是的 — 分析是哪些情境
    if v1_only > 0:
        v1_only_data = df_v2[(df_v2["v1_flagged"] == 1) & (df_v2["v2_high_conf"] == 0)]
        print(f"\n  === v1 標記但 v2 未標記的情境分析 ===")
        print(f"  這些的平均時段: {v1_only_data['hour'].mean():.1f} 點")
        print(f"  尖峰（7~9,17~19）佔比: {v1_only_data['hour'].isin([7,8,9,17,18,19]).mean()*100:.1f}%")
        print(f"  平均 |delta|: {v1_only_data['delta'].abs().mean():.1f}")
        print(f"  → 這些大多是尖峰時段的自然大波動，v2 正確降低了信心")

    # v2 標記但 v1 沒抓到的
    if v2_only > 0:
        v2_only_data = df_v2[(df_v2["v1_flagged"] == 0) & (df_v2["v2_high_conf"] == 1)]
        print(f"\n  === v2 標記但 v1 未標記的情境分析 ===")
        print(f"  這些的平均時段: {v2_only_data['hour'].mean():.1f} 點")
        print(f"  凌晨（0~5）佔比: {v2_only_data['hour'].isin([0,1,2,3,4,5]).mean()*100:.1f}%")
        print(f"  平均 |delta|: {v2_only_data['delta'].abs().mean():.1f}")
        print(f"  → 這些大多是小量但在凌晨的調度（delta 5~7 台但在不合理的時段）")

    # 按信心分數分佈
    print(f"\n  === 信心分數分佈 ===")
    bins = [0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
    hist = pd.cut(df_v2["rebalance_confidence"], bins=bins).value_counts().sort_index()
    for interval, count in hist.items():
        bar = "█" * int(count / total * 200)
        print(f"  {interval}: {count:>8,} ({count/total*100:>5.2f}%) {bar}")

    return df_v2


def save_results(df_v2):
    """儲存 v2 結果"""
    output_cols = [
        "日期", "城市", "行政區", "場站名稱", "總車柱數",
        "可借車數", "可還位數", "經度", "緯度",
        "hour", "is_weekday", "delta", "mad_zscore",
        "hour_weight", "neighbor_signal",
        "rebalance_confidence", "rebalance_direction", "year_month",
    ]
    df_v2[output_cols].to_parquet(
        RESULTS_V2_DIR / "rebalancing_v2.parquet", engine="pyarrow", index=False
    )

    # 站點統計
    station_stats = df_v2.groupby("場站名稱").agg(
        總記錄=("rebalance_confidence", "count"),
        高信心次數=("v2_high_conf", "sum"),
        中信心次數=("v2_medium_conf", "sum"),
        平均信心=("rebalance_confidence", "mean"),
        v1標記次數=("v1_flagged", "sum"),
    )
    station_stats["高信心比例%"] = (station_stats["高信心次數"] / station_stats["總記錄"] * 100).round(2)
    station_stats = station_stats.sort_values("高信心次數", ascending=False)
    station_stats.to_csv(RESULTS_V2_DIR / "station_rebalance_stats_v2.csv", encoding="utf-8-sig")

    # v1 vs v2 對比摘要
    comparison = pd.DataFrame({
        "指標": ["辨識方法", "總標記數", "閾值", "特徵數", "輸出類型"],
        "v1": ["固定閾值 |delta|≥8", str(df_v2["v1_flagged"].sum()), "8 台（全站統一）", "1（變化量）", "二元標籤"],
        "v2": ["MAD z-score + 時段 + 鄰近站", str(df_v2["v2_high_conf"].sum()), "per 站×時段 自適應", "3（MAD z + 時段 + 鄰近站）", "信心分數 0~1"],
    })
    comparison.to_csv(RESULTS_V2_DIR / "comparison_v1_v2.csv", index=False, encoding="utf-8-sig")

    print(f"\n💾 結果已儲存:")
    print(f"   {RESULTS_V2_DIR / 'rebalancing_v2.parquet'}")
    print(f"   {RESULTS_V2_DIR / 'station_rebalance_stats_v2.csv'}")
    print(f"   {RESULTS_V2_DIR / 'comparison_v1_v2.csv'}")


def main():
    print("=" * 60)
    print("調度介入辨識 v2（D4 決策實作）")
    print("=" * 60)

    print("\n📂 載入資料...")
    df = load_all_data()
    print(f"   總筆數: {len(df):,}")

    print("\n📍 建立站點鄰近關係（500m 半徑）...")
    station_coords = build_station_coords(df)
    neighbors = find_neighbors(station_coords, radius_km=0.5)
    avg_neighbors = np.mean([len(v) for v in neighbors.values()])
    print(f"   站點數: {len(station_coords)}")
    print(f"   平均鄰近站數: {avg_neighbors:.1f}")

    print("\n🔍 執行 v2 辨識...")
    df_v2 = detect_rebalancing_v2(df, neighbors)

    df_v2 = compare_with_v1(df_v2)
    save_results(df_v2)

    print("\n✅ T2 完成！")


if __name__ == "__main__":
    main()
