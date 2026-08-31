"""
規則引擎（T4, D8）
==================
- 吃 T3 預測模型的區間下界（D3）觸發調度
- 所有閾值從 config.yaml 讀取（D8）
- 輸出排序後的調度建議清單：哪一站、取或送、幾台、優先級、觸發原因（人看得懂的句子）

用法：
    python rule_engine.py --timestamp "2026-06-15 08:00:00"
    python rule_engine.py --demo  # 用範例資料展示

驗收標準：
- 給定一個時間點的站點狀態，輸出排序後的調度建議清單
- 觸發原因是人看得懂的句子，不是規則代號
"""

import yaml
import pandas as pd
import numpy as np
from pathlib import Path
from dataclasses import dataclass

CONFIG_PATH = Path("config.yaml")
MODEL_RESULTS = Path("output/model_results")
PARQUET_DIR = Path("output/youbike_parquet")


@dataclass
class DispatchRecommendation:
    """一條調度建議"""
    站名: str
    行政區: str
    動作: str          # "補車" 或 "取車"
    數量: int          # 幾台
    優先分數: float
    觸發原因: str       # 人看得懂的句子
    當前可借: int
    總車柱: int
    預測下界: float = 0.0
    預測上界: float = 0.0


def load_config():
    """載入外部化設定"""
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    return config


def evaluate_station(row, config):
    """
    評估單一站點是否需要調度
    回傳 DispatchRecommendation 或 None
    """
    trigger = config["trigger"]
    target = config["target"]
    priority_cfg = config["priority"]
    capacity = config["capacity"]

    station = row["場站名稱"]
    district = row["行政區"]
    available = row["可借車數"]
    total = row["總車柱數"]
    returnable = row["可還位數"]

    # 預測區間（如果有的話）
    pred_lower = row.get("pred_lower_10", available)
    pred_upper = row.get("pred_upper_90", available)

    if total == 0:
        return None

    usage_rate = available / total * 100
    # 用預測下界判斷（D3: 規則引擎對區間下界觸發）
    pred_lower_rate = pred_lower / total * 100 if pred_lower is not None else usage_rate

    reasons = []
    action = None
    quantity = 0

    # === 觸發條件判斷 ===

    # 條件 1: 可借車數極低（即將空站）
    if available <= trigger["空站危險_可借車數"]:
        reasons.append(f"可借車數僅 {available} 台，即將空站")
        action = "補車"

    # 條件 2: 預測下界觸發（即使現在還沒空，但模型預測下一時段可能空）
    elif pred_lower <= trigger["空站危險_可借車數"]:
        reasons.append(f"預測下界 {pred_lower:.0f} 台，30分鐘內可能空站")
        action = "補車"

    # 條件 3: 借用率低於低水位
    elif pred_lower_rate < trigger["低水位_借用率%"]:
        reasons.append(f"預測借用率 {pred_lower_rate:.0f}% 低於門檻 {trigger['低水位_借用率%']}%")
        action = "補車"

    # 條件 4: 可還位數極低（即將滿站）
    elif returnable <= trigger["滿站危險_可還位數"]:
        reasons.append(f"可還位數僅 {returnable} 台，即將滿站")
        action = "取車"

    # 條件 5: 借用率高於高水位
    elif usage_rate > trigger["高水位_借用率%"]:
        reasons.append(f"借用率 {usage_rate:.0f}% 超過門檻 {trigger['高水位_借用率%']}%")
        action = "取車"

    if action is None:
        return None

    # === 計算數量 ===
    target_available = int(total * target["補車後目標_借用率%"] / 100)
    if action == "補車":
        quantity = max(1, target_available - available)
    else:
        quantity = max(1, available - target_available)

    # 不超過每站上限
    quantity = min(quantity, capacity["每站最大搬運量"])

    # === 計算優先級分數 ===
    # 緊急度：距離空/滿還有幾台（越少越緊急）
    if action == "補車":
        urgency = max(1, trigger["空站危險_可借車數"] + 5 - available)
    else:
        urgency = max(1, trigger["滿站危險_可還位數"] + 5 - returnable)

    # 站點容量倒數（小站優先）
    capacity_factor = 1.0 / max(total, 10) * 100

    priority_score = (
        urgency * priority_cfg["緊急度權重"]
        + capacity_factor * priority_cfg["容量倒數權重"]
    )

    return DispatchRecommendation(
        站名=station,
        行政區=district,
        動作=action,
        數量=quantity,
        優先分數=round(priority_score, 2),
        觸發原因="；".join(reasons),
        當前可借=int(available),
        總車柱=int(total),
        預測下界=float(pred_lower) if pred_lower is not None else 0.0,
        預測上界=float(pred_upper) if pred_upper is not None else 0.0,
    )


def generate_dispatch_list(station_states: pd.DataFrame, config: dict) -> pd.DataFrame:
    """
    給定一個時間點的所有站點狀態，產出排序後的調度建議清單
    """
    recommendations = []
    for _, row in station_states.iterrows():
        rec = evaluate_station(row, config)
        if rec is not None:
            recommendations.append(rec)

    if not recommendations:
        return pd.DataFrame()

    # 按優先分數降序排列
    df_rec = pd.DataFrame([vars(r) for r in recommendations])
    df_rec = df_rec.sort_values("優先分數", ascending=False).reset_index(drop=True)

    # 截取前 N 站（容量約束）
    max_stations = config["capacity"]["每時段最大調度站數"]
    df_rec = df_rec.head(max_stations)

    return df_rec


def demo():
    """用 6 月資料的某個時間點展示規則引擎輸出"""
    print("=" * 70)
    print("規則引擎 Demo（T4）")
    print("=" * 70)

    config = load_config()
    print(f"\n⚙️  設定檔: {CONFIG_PATH}")
    print(f"   低水位觸發: 借用率 < {config['trigger']['低水位_借用率%']}%")
    print(f"   高水位觸發: 借用率 > {config['trigger']['高水位_借用率%']}%")
    print(f"   空站危險: 可借 ≤ {config['trigger']['空站危險_可借車數']} 台")
    print(f"   每時段最大站數: {config['capacity']['每時段最大調度站數']}")

    # 載入 6 月資料取某個尖峰時段
    print(f"\n📂 載入 6 月驗證資料...")
    df = pd.read_parquet(PARQUET_DIR / "year_month=2026-06" / "data.parquet")
    df["dt"] = pd.to_datetime(df["日期"])
    df["hour"] = df["dt"].dt.hour

    # 取平日早上 08:00 的一個快照
    target_time = "2026-06-02 08:00:00"  # 週一早上
    snapshot = df[df["日期"] == target_time].copy()

    if len(snapshot) == 0:
        # 找最接近的
        target_time = df[df["hour"] == 8]["日期"].iloc[0]
        snapshot = df[df["日期"] == target_time].copy()

    print(f"   選取時間: {target_time}")
    print(f"   站點數: {len(snapshot)}")

    # 模擬預測區間（用簡單邏輯：下界 = 當前 - 3, 上界 = 當前 + 3）
    # 正式版會接 T3 模型輸出
    snapshot["pred_lower_10"] = (snapshot["可借車數"] - 3).clip(lower=0)
    snapshot["pred_upper_90"] = (snapshot["可借車數"] + 3).clip(upper=snapshot["總車柱數"])

    # 產出建議清單
    dispatch_list = generate_dispatch_list(snapshot, config)

    if len(dispatch_list) == 0:
        print("\n   ✅ 此時段無站點需要調度")
        return

    print(f"\n📋 調度建議清單（前 {min(15, len(dispatch_list))} 站）:")
    print(f"{'排序':<4} {'站名':<24} {'區域':<6} {'動作':<4} {'數量':<4} "
          f"{'優先':<6} {'現有':<4} {'容量':<4} {'觸發原因'}")
    print("-" * 110)

    for i, row in dispatch_list.head(15).iterrows():
        print(f"{i+1:<4} {row['站名']:<24} {row['行政區']:<6} {row['動作']:<4} "
              f"{row['數量']:<4} {row['優先分數']:<6} {row['當前可借']:<4} "
              f"{row['總車柱']:<4} {row['觸發原因']}")

    # 統計
    print(f"\n📊 本時段調度摘要:")
    print(f"   需要補車: {(dispatch_list['動作'] == '補車').sum()} 站")
    print(f"   需要取車: {(dispatch_list['動作'] == '取車').sum()} 站")
    print(f"   總搬運量: {dispatch_list['數量'].sum()} 台")
    print(f"   最高優先站: {dispatch_list.iloc[0]['站名']}（{dispatch_list.iloc[0]['觸發原因']}）")

    # 儲存
    output_path = Path("output/rule_engine_demo.csv")
    dispatch_list.to_csv(output_path, index=False, encoding="utf-8-sig")
    print(f"\n💾 已儲存: {output_path}")

    print("\n✅ T4 規則引擎 Demo 完成！")


if __name__ == "__main__":
    demo()
