"""
規則引擎（T4, D8）— 動態觸發版
================================
2026-08-31 遷移：從「可借車數 ≤ 3」這類固定門檻，改為 design.md §7 的動態判斷。

判斷方式（唯一真實來源：config.yaml，對齊 design.md §7）
- 主判斷：吃 predictor 的**預測區間下界**當「預測到達存量」，比對 trigger.安全緩衝_台數
    調整後到達存量 = 當前存量 −（當前存量 − 區間下界）× 觸發靈敏度
  滿站側對稱：預測可還位下界 = 總車柱 − 區間上界（同樣放大後）比對安全緩衝
- 降級：沒有預測區間時，改用「該站歷史同星期同時段的淨流出」估到達存量，並在觸發原因裡標明
        （NFR-5 失敗可見：降級結果一定看得出來，不會假裝是預測值）
- 保底：低/高水位借用率百分比只是輔助門檻，不是主要依據

刻意不做的事（steering §5 / AGENTS.md）
- 不吃點估計 pred_point：規則引擎只吃區間下界，避免尖峰系統性漏觸發
- 不做預測、不排任務路線：預測在 predictor，排序後的派發在 dispatcher

用法：
    python rule_engine.py --demo
"""

import math
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import yaml

CONFIG_PATH = Path("config.yaml")
PARQUET_DIR = Path("output/youbike_parquet")
PRED_PATH = Path("output/model_results/prediction_sample.csv")

# config.yaml 必要區塊 → 缺了就明確報錯，不靜默使用預設值（NFR-5）
REQUIRED_KEYS = {
    "trigger": ["安全緩衝_台數", "觸發靈敏度", "低水位_借用率百分比", "高水位_借用率百分比"],
    "target": ["預設借用率百分比"],
    "fleet": ["調度車數量", "每車容量", "每趟最大站數", "每時段最大調度站數", "響應時間_分鐘"],
    "urgency_weights": ["預測到達存量", "容量級距"],
}
# urgency_weights 中尚未有資料可餵的因子（等 B 的特徵補齊後啟用）
UNUSED_WEIGHTS = ["站群緩衝", "影響人數", "調度到達時間", "時效敏感度"]


@dataclass
class DispatchRecommendation:
    """一條調度建議"""
    站名: str
    行政區: str
    動作: str            # "補車" 或 "取車"
    數量: int
    優先分數: float
    觸發原因: str         # 人看得懂的句子（NFR-1）
    判斷依據: str         # "區間下界" / "歷史同時段淨流出（降級）" / "保底門檻"
    當前可借: int
    總車柱: int
    預測到達存量: float
    預測可還位下界: float


def load_config(path: Path = CONFIG_PATH) -> dict:
    """載入外部化設定，並檢查必要 key（缺了就直接失敗，指回 spec）"""
    with open(path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    missing = []
    for section, keys in REQUIRED_KEYS.items():
        if section not in config:
            missing.append(section)
            continue
        missing += [f"{section}.{k}" for k in keys if k not in config[section]]
    if missing:
        raise KeyError(
            "config.yaml 缺少必要設定：" + "、".join(missing) +
            "\n請對齊 .kiro/specs/youbike-dispatch-system/design.md §7。"
            "\n（若要跑舊的 PoC 死數字版，請改用 config.poc_v1.yaml + rule_engine.poc_v1.py）"
        )
    return config


def _is_num(v) -> bool:
    return v is not None and not (isinstance(v, float) and math.isnan(v))


def estimate_arrival_stock(row, sensitivity: float):
    """
    估「調度車到達時」的存量與可還位，回傳 (到達存量, 可還位下界, 依據來源)。
    優先用預測區間；沒有區間才降級用歷史同時段淨流出；都沒有回 (None, None, None)。
    """
    available = float(row["可借車數"])
    total = float(row["總車柱數"])
    lower = row.get("pred_lower_10")
    upper = row.get("pred_upper_90")

    if _is_num(lower) and _is_num(upper):
        net_out = available - float(lower)          # 正 = 預期淨流出
        net_in = float(upper) - available           # 正 = 預期淨流入
        arrival = available - net_out * sensitivity
        returnable_lower = (total - available) - net_in * sensitivity
        return arrival, returnable_lower, "區間下界"

    hist_net = row.get("hist_net_outflow")
    if _is_num(hist_net):
        arrival = available - float(hist_net) * sensitivity
        returnable_lower = (total - available) + float(hist_net) * sensitivity
        return arrival, returnable_lower, "歷史同時段淨流出（降級）"

    return None, None, None


def evaluate_station(row, config):
    """評估單一站點是否需要調度，回傳 DispatchRecommendation 或 None"""
    trigger = config["trigger"]
    target = config["target"]
    fleet = config["fleet"]
    weights = config["urgency_weights"]

    total = float(row["總車柱數"])
    if total <= 0:
        return None

    available = float(row["可借車數"])
    buffer_bikes = float(trigger["安全緩衝_台數"])
    sensitivity = float(trigger["觸發靈敏度"])
    horizon = fleet["響應時間_分鐘"]

    arrival, returnable_lower, source = estimate_arrival_stock(row, sensitivity)
    usage_rate = available / total * 100

    action = None
    reason = None

    if arrival is None:
        # 既沒有預測也沒有歷史 → 只能用保底門檻，且必須標明（NFR-5）
        source = "保底門檻（無預測、無歷史）"
        arrival = available
        returnable_lower = total - available

    if arrival <= buffer_bikes:
        action = "補車"
        reason = (f"{horizon} 分鐘後預測到達存量 {arrival:.1f} 台，"
                  f"低於安全緩衝 {buffer_bikes:.0f} 台，即將空站")
    elif returnable_lower <= buffer_bikes:
        action = "取車"
        reason = (f"{horizon} 分鐘後預測可還位僅 {returnable_lower:.1f} 個，"
                  f"低於安全緩衝 {buffer_bikes:.0f} 個，即將滿站")
    elif usage_rate < trigger["低水位_借用率百分比"]:
        action, source = "補車", "保底門檻"
        reason = (f"借用率 {usage_rate:.0f}% 低於保底門檻 "
                  f"{trigger['低水位_借用率百分比']}%（動態判斷未觸發）")
    elif usage_rate > trigger["高水位_借用率百分比"]:
        action, source = "取車", "保底門檻"
        reason = (f"借用率 {usage_rate:.0f}% 高於保底門檻 "
                  f"{trigger['高水位_借用率百分比']}%（動態判斷未觸發）")

    if action is None:
        return None

    # === 數量：補到 / 取到預設目標水位，單站不超過一車容量 ===
    target_available = total * float(target["預設借用率百分比"]) / 100
    if action == "補車":
        quantity = max(1, round(target_available - available))
    else:
        quantity = max(1, round(available - target_available))
    quantity = int(min(quantity, fleet["每車容量"]))

    # === 優先分數（0~100）===
    # 目前只啟用「預測到達存量」與「容量級距」兩個因子，其餘權重等 B 的特徵補齊
    deficit = max(0.0, buffer_bikes - (arrival if action == "補車" else returnable_lower))
    norm_deficit = min(1.0, deficit / max(buffer_bikes + 3.0, 1.0))
    small_station = 1.0 - min(1.0, total / 60.0)
    w_stock = float(weights["預測到達存量"])
    w_cap = float(weights["容量級距"])
    priority = 100.0 * (w_stock * norm_deficit + w_cap * small_station) / max(w_stock + w_cap, 1e-6)

    return DispatchRecommendation(
        站名=row["場站名稱"],
        行政區=row["行政區"],
        動作=action,
        數量=quantity,
        優先分數=round(priority, 1),
        觸發原因=reason,
        判斷依據=source,
        當前可借=int(available),
        總車柱=int(total),
        預測到達存量=round(float(arrival), 1),
        預測可還位下界=round(float(returnable_lower), 1),
    )


def generate_dispatch_list(station_states: pd.DataFrame, config: dict) -> pd.DataFrame:
    """給定一個時間點的所有站點狀態，產出排序後的調度建議清單"""
    recs = [r for r in (evaluate_station(row, config) for _, row in station_states.iterrows())
            if r is not None]
    if not recs:
        return pd.DataFrame()

    df = pd.DataFrame([vars(r) for r in recs]).sort_values(
        "優先分數", ascending=False).reset_index(drop=True)

    # 現實容量約束：時段上限，且不超過「調度車數量 × 每趟最大站數」
    fleet = config["fleet"]
    cap = min(int(fleet["每時段最大調度站數"]),
              int(fleet["調度車數量"]) * int(fleet["每趟最大站數"]))
    return df.head(cap)


def compute_hist_net_outflow(df: pd.DataFrame) -> pd.Series:
    """各站「星期 × 半小時時段」的平均淨流出（正 = 車在減少），供降級估算用"""
    d = df.sort_values(["場站名稱", "日期"]).copy()
    d["next_avail"] = d.groupby("場站名稱")["可借車數"].shift(-1)
    d["net_out"] = d["可借車數"] - d["next_avail"]
    d["weekday"] = d["dt"].dt.weekday
    d["slot"] = d["dt"].dt.hour * 2 + (d["dt"].dt.minute >= 30).astype(int)
    return d.groupby(["場站名稱", "weekday", "slot"])["net_out"].mean()


def demo():
    print("=" * 74)
    print("規則引擎 Demo（T4）— 動態觸發版")
    print("=" * 74)

    config = load_config()
    t, f = config["trigger"], config["fleet"]
    print(f"\n[設定] {CONFIG_PATH}（對齊 design.md §7）")
    print(f"   安全緩衝: {t['安全緩衝_台數']} 台　觸發靈敏度: {t['觸發靈敏度']}")
    print(f"   保底門檻: 借用率 < {t['低水位_借用率百分比']}% 或 > {t['高水位_借用率百分比']}%")
    print(f"   前瞻窗口: 響應時間 {f['響應時間_分鐘']} 分鐘")
    print(f"   時段上限: {f['每時段最大調度站數']} 站 / 車隊 {f['調度車數量']} 車 × {f['每趟最大站數']} 站")
    print(f"   [未啟用權重] {'、'.join(UNUSED_WEIGHTS)}（等預測特徵補齊）")

    df = pd.read_parquet(PARQUET_DIR / "year_month=2026-06" / "data.parquet")
    df["dt"] = pd.to_datetime(df["日期"])

    target_time = "2026-06-02 08:00:00"
    snapshot = df[df["日期"] == target_time].copy()
    if len(snapshot) == 0:
        target_time = df[df["dt"].dt.hour == 8]["日期"].iloc[0]
        snapshot = df[df["日期"] == target_time].copy()
    print(f"\n[資料] {target_time}　{len(snapshot)} 站")

    # 優先接 T3 模型的預測區間；沒有才降級用歷史同時段淨流出
    if PRED_PATH.exists():
        pred = pd.read_csv(PRED_PATH)
        pred.columns = [c.lstrip("﻿") for c in pred.columns]
        pred = pred[pred["日期"] == target_time][["場站名稱", "pred_lower_10", "pred_upper_90"]]
        snapshot = snapshot.merge(pred, on="場站名稱", how="left")
        hit = snapshot["pred_lower_10"].notna().sum() if "pred_lower_10" in snapshot else 0
        print(f"[預測] 接上區間預測 {hit}/{len(snapshot)} 站")
    else:
        print("[預測] 找不到預測檔，全部走降級路徑")

    stats = compute_hist_net_outflow(df)
    ts = pd.to_datetime(target_time)
    key_wd, key_slot = ts.weekday(), ts.hour * 2 + (ts.minute >= 30)
    snapshot["hist_net_outflow"] = snapshot["場站名稱"].map(
        lambda s: stats.get((s, key_wd, key_slot), float("nan")))

    dispatch_list = generate_dispatch_list(snapshot, config)
    if len(dispatch_list) == 0:
        print("\n   此時段無站點需要調度")
        return

    print(f"\n[調度建議] 前 {min(15, len(dispatch_list))} 站")
    print(f"{'#':<3} {'站名':<22} {'區':<5} {'動作':<4} {'量':<4} {'優先':<6} "
          f"{'到達存量':<8} {'依據':<20} 原因")
    print("-" * 130)
    for i, r in dispatch_list.head(15).iterrows():
        print(f"{i+1:<3} {r['站名']:<22} {r['行政區']:<5} {r['動作']:<4} {r['數量']:<4} "
              f"{r['優先分數']:<6} {r['預測到達存量']:<8} {r['判斷依據']:<20} {r['觸發原因']}")

    print(f"\n[摘要] 補車 {(dispatch_list['動作']=='補車').sum()} 站　"
          f"取車 {(dispatch_list['動作']=='取車').sum()} 站　"
          f"總搬運 {dispatch_list['數量'].sum()} 台")
    print("[依據分布] " + "　".join(
        f"{k}: {v}" for k, v in dispatch_list["判斷依據"].value_counts().items()))

    out = Path("output/rule_engine_demo.csv")
    dispatch_list.to_csv(out, index=False, encoding="utf-8-sig")
    print(f"\n[已儲存] {out}")


if __name__ == "__main__":
    demo()
