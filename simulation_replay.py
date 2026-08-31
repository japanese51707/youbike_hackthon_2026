"""
模擬重放引擎（T1, D1）
======================
目的：證明「本系統比人工調度好」的唯一可行途徑。

步驟：
1. 用 T2（v2 辨識）把歷史中的調度介入標記出來
2. 還原「無人工干預」的自然供需曲線（介入時段以前後趨勢內插）
3. 在還原後的時間軸上重放：若本系統依規則引擎下調度決策，車輛數如何演變
4. 輸出 Before/After 對比指標

誠實邊界（必須在簡報中主動說明）：
- 重放模擬有內生性問題 — 系統調度會改變使用者行為，模擬無法捕捉此效應
- 歷史調度辨識本身是概率性的，還原的「自然曲線」是推估而非事實
- 此模擬用於方向性驗證（「有改善」），數字精度不宜過度解讀

驗收標準：
- 輸出表：情境（實際歷史 / 無調度自然 / 本系統模擬）× 指標（尖峰空站率、全日空站率、滿站率、調度趟次）
- 模擬情境的尖峰空站率有具體數字可與實際 8.41% 對比
"""

import pandas as pd
import numpy as np
from pathlib import Path

OUTPUT_DIR = Path("output")
PARQUET_DIR = OUTPUT_DIR / "youbike_parquet"
V2_DIR = OUTPUT_DIR / "analysis_results_v2"
SIM_DIR = OUTPUT_DIR / "simulation_results"
SIM_DIR.mkdir(parents=True, exist_ok=True)

# === 系統規則引擎參數（D8: 外部化，此處集中定義） ===
CONFIG = {
    "調度車數量": 20,
    "每車容量": 25,
    "每趟最大站數": 5,
    "響應時間_時段數": 1,  # 1 個時段 = 30 分鐘後才能到達
    "觸發閾值_空站危險": 15,  # 可借車數 ≤ 此值 且 借用率 ≤ 觸發比例 → 考慮補車
    "觸發比例_低水位%": 20,  # 借用率低於此 → 觸發補車考慮
    "觸發比例_高水位%": 85,  # 借用率高於此 → 觸發取車考慮
    "目標水位_補車後%": 50,  # 補車後的目標借用率
    "目標水位_取車後%": 50,  # 取車後的目標借用率
    "每時段最大調度次數": 40,  # 所有車加起來每 30 分鐘最多處理幾站（容量約束）
    "信心閾值_辨識調度": 0.5,  # v2 辨識的信心分數閾值
}


def load_data():
    """載入 v2 辨識結果"""
    print("📂 載入 v2 辨識資料...")
    df = pd.read_parquet(V2_DIR / "rebalancing_v2.parquet")
    print(f"   筆數: {len(df):,}")
    return df


def restore_natural_curve(df):
    """
    還原「無人工干預」的自然供需曲線
    方法：對高信心調度介入的時段，用線性內插還原自然值
    """
    print("\n🔄 還原自然供需曲線...")

    df = df.sort_values(["場站名稱", "日期"]).reset_index(drop=True)

    # 標記高信心調度介入
    df["is_rebalanced"] = (df["rebalance_confidence"] >= CONFIG["信心閾值_辨識調度"]).astype(int)

    rebalanced_count = df["is_rebalanced"].sum()

    # 向量化方式：把被標記的可借車數設為 NaN，再 per-station interpolate
    df["natural_available"] = df["可借車數"].astype(float)
    df.loc[df["is_rebalanced"] == 1, "natural_available"] = np.nan

    # per-station 線性內插
    df["natural_available"] = df.groupby("場站名稱")["natural_available"].transform(
        lambda x: x.interpolate(method="linear", limit_direction="both")
    )

    # 處理仍有 NaN 的（首尾或整段被標記的站）
    df["natural_available"] = df.groupby("場站名稱")["natural_available"].transform(
        lambda x: x.ffill().bfill()
    )

    # 邊界：不超過容量、不低於 0
    df["natural_available"] = df["natural_available"].clip(lower=0)
    df["natural_available"] = np.minimum(df["natural_available"], df["總車柱數"])

    print(f"   被還原的時段數: {rebalanced_count:,}")
    print(f"   佔比: {rebalanced_count / len(df) * 100:.2f}%")

    return df


def simulate_system_dispatch(df):
    """
    模擬「本系統」的調度決策（完全向量化版）
    簡化規則（D6: heuristic 版）：
    - 每個時段掃描所有站
    - 借用率 < 20% → 需要補車（優先級 = 缺多少台）
    - 借用率 > 85% → 需要取車
    - 按優先級排序，受限於每時段最大調度次數
    - 補車/取車到目標水位 50%

    效能策略：
    - 向量化判斷哪些站需要調度
    - 按時段排名用 groupby + rank 實現，不逐時段迴圈
    """
    print("\n🚛 模擬系統調度決策...")

    df = df.sort_values(["日期", "場站名稱"]).reset_index(drop=True)

    # 用自然曲線作為起點
    df["sim_available"] = df["natural_available"].copy()

    low_threshold = CONFIG["觸發比例_低水位%"]
    high_threshold = CONFIG["觸發比例_高水位%"]
    target_pct = CONFIG["目標水位_補車後%"]
    max_dispatches = CONFIG["每時段最大調度次數"]

    # 計算模擬借用率
    df["sim_usage_rate"] = df["sim_available"] / df["總車柱數"] * 100

    # 找出需要介入的
    needs_add = df["sim_usage_rate"] < low_threshold
    needs_remove = df["sim_usage_rate"] > high_threshold
    df["needs_dispatch"] = needs_add | needs_remove

    # 計算目標和缺口
    target_bikes = (df["總車柱數"] * target_pct / 100).round()
    df["deficit"] = (target_bikes - df["sim_available"]).abs()

    # 向量化排名：每個時段內按 deficit 降序排名
    # 只對需要調度的記錄排名
    df["priority_rank"] = np.nan
    dispatch_mask = df["needs_dispatch"]
    if dispatch_mask.sum() > 0:
        df.loc[dispatch_mask, "priority_rank"] = df[dispatch_mask].groupby("日期")["deficit"].rank(
            method="first", ascending=False
        )

    # 只有排名 <= max_dispatches 的才真的被調度
    dispatched_mask = dispatch_mask & (df["priority_rank"] <= max_dispatches)

    # 對被調度的站，把 sim_available 調整到目標水位
    df.loc[dispatched_mask, "sim_available"] = target_bikes[dispatched_mask]

    total_dispatches = dispatched_mask.sum()
    total_bikes_moved = df.loc[dispatched_mask, "deficit"].sum()

    # 重新計算模擬後的指標
    df["sim_usage_rate"] = df["sim_available"] / df["總車柱數"] * 100
    df["sim_is_empty"] = (df["sim_available"] <= 0).astype(int)
    df["sim_is_full"] = (df["sim_available"] >= df["總車柱數"]).astype(int)

    print(f"   模擬調度總次數: {total_dispatches:,}")
    print(f"   模擬搬運總台數: {total_bikes_moved:,.0f}")

    # 每天平均調度趟次（每趟服務多站，假設 3 站/趟）
    total_days = df["日期"].str[:10].nunique()
    daily_trips = total_dispatches / total_days / 3  # 3 站/趟
    print(f"   模擬每日調度趟數: {daily_trips:.0f}")

    return df, total_dispatches


def compute_metrics(df):
    """計算三個情境的對比指標"""
    print("\n" + "=" * 60)
    print("📋 模擬重放結果 — Before / After 對比")
    print("=" * 60)

    # 定義尖峰時段
    df["hour"] = df["hour"].astype(int) if "hour" in df.columns else pd.to_datetime(df["日期"]).dt.hour
    df["is_weekday"] = df["is_weekday"].astype(int)
    peak_mask = df["is_weekday"] == 1  # 平日
    peak_hour_mask = peak_mask & df["hour"].isin([7, 8, 9])  # 早上尖峰

    # === 情境 A: 實際歷史（含人工調度） ===
    actual_empty_rate = df["是否空站"].mean() * 100 if "是否空站" in df.columns else (df["可借車數"] == 0).mean() * 100
    actual_full_rate = df["是否滿站"].mean() * 100 if "是否滿站" in df.columns else (df["可還位數"] == 0).mean() * 100
    actual_peak_empty = (df.loc[peak_hour_mask, "可借車數"] == 0).mean() * 100

    # 實際調度次數（v2 高信心）
    actual_dispatches = (df["rebalance_confidence"] >= CONFIG["信心閾值_辨識調度"]).sum()
    actual_daily_trips = actual_dispatches / df["日期"].str[:10].nunique() / 3

    # === 情境 B: 無調度自然曲線 ===
    natural_empty = (df["natural_available"] <= 0).mean() * 100
    natural_full = (df["natural_available"] >= df["總車柱數"]).mean() * 100
    natural_peak_empty = (df.loc[peak_hour_mask, "natural_available"] <= 0).mean() * 100

    # === 情境 C: 本系統模擬 ===
    sim_empty = df["sim_is_empty"].mean() * 100
    sim_full = df["sim_is_full"].mean() * 100
    sim_peak_empty = df.loc[peak_hour_mask, "sim_is_empty"].mean() * 100
    sim_daily_trips = df["needs_dispatch"].sum() / df["日期"].str[:10].nunique() / 3

    # 輸出對比表
    results = pd.DataFrame({
        "指標": ["全日空站率(%)", "尖峰空站率(07-09平日%)", "全日滿站率(%)", "每日調度趟數(估)"],
        "實際歷史(含人工調度)": [
            f"{actual_empty_rate:.2f}",
            f"{actual_peak_empty:.2f}",
            f"{actual_full_rate:.2f}",
            f"{actual_daily_trips:.0f}",
        ],
        "無調度自然曲線": [
            f"{natural_empty:.2f}",
            f"{natural_peak_empty:.2f}",
            f"{natural_full:.2f}",
            "0",
        ],
        "本系統模擬": [
            f"{sim_empty:.2f}",
            f"{sim_peak_empty:.2f}",
            f"{sim_full:.2f}",
            f"{sim_daily_trips:.0f}",
        ],
    })

    print("\n" + results.to_string(index=False))

    # 改善幅度
    print("\n  === 改善幅度 ===")
    print(f"  尖峰空站率: {actual_peak_empty:.2f}% → {sim_peak_empty:.2f}% "
          f"(改善 {actual_peak_empty - sim_peak_empty:.2f} 個百分點)")
    print(f"  全日空站率: {actual_empty_rate:.2f}% → {sim_empty:.2f}% "
          f"(改善 {actual_empty_rate - sim_empty:.2f} 個百分點)")

    if sim_daily_trips > 0 and actual_daily_trips > 0:
        efficiency = (actual_peak_empty - sim_peak_empty) / sim_daily_trips
        print(f"  每趟調度減少的尖峰空站率: {efficiency:.4f} 個百分點/趟")

    # 誠實邊界
    print("\n  ⚠️ 誠實邊界聲明:")
    print("  - 重放模擬有內生性：系統調度會改變使用者行為，模擬未能捕捉此效應")
    print("  - 調度辨識為概率性推估，自然曲線是近似而非事實")
    print("  - 數字用於方向性驗證，不宜過度解讀精確值")

    # 儲存
    results.to_csv(SIM_DIR / "before_after_comparison.csv", index=False, encoding="utf-8-sig")

    # 儲存詳細的月份拆解
    monthly_stats = []
    for ym in sorted(df["year_month"].unique()):
        ym_mask = df["year_month"] == ym
        ym_peak = ym_mask & peak_hour_mask
        monthly_stats.append({
            "月份": ym,
            "實際尖峰空站率%": (df.loc[ym_peak, "可借車數"] == 0).mean() * 100 if ym_peak.sum() > 0 else 0,
            "自然尖峰空站率%": (df.loc[ym_peak, "natural_available"] <= 0).mean() * 100 if ym_peak.sum() > 0 else 0,
            "模擬尖峰空站率%": df.loc[ym_peak, "sim_is_empty"].mean() * 100 if ym_peak.sum() > 0 else 0,
        })
    monthly_df = pd.DataFrame(monthly_stats)
    monthly_df.to_csv(SIM_DIR / "monthly_comparison.csv", index=False, encoding="utf-8-sig")

    print(f"\n💾 已儲存:")
    print(f"   {SIM_DIR / 'before_after_comparison.csv'}")
    print(f"   {SIM_DIR / 'monthly_comparison.csv'}")

    return results


def main():
    print("=" * 60)
    print("模擬重放引擎（T1, D1）")
    print("=" * 60)
    print(f"\n⚙️ 系統參數:")
    for k, v in CONFIG.items():
        print(f"   {k}: {v}")

    df = load_data()
    df = restore_natural_curve(df)
    df, total_dispatches = simulate_system_dispatch(df)
    results = compute_metrics(df)

    print("\n" + "=" * 60)
    print("✅ T1 模擬重放引擎完成！")
    print("=" * 60)


if __name__ == "__main__":
    main()
