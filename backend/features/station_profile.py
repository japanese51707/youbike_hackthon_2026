"""
站點行為指紋（features.station_profile）— ADR-014
==================================================
從站點六個月歷史算「行為指紋」——量的是實際使用行為（本體），比人口資料（代理）更準、零外部成本。
用於：站型分群（可人話描述給交通局）+ 需求密度（規劃層柱位建議）。

★需求密度的分層界線（ADR-014，不可混）：
  - 規劃層（長期）：需求密度 = 日均活動量 ÷ 柱位數 → 記站點欄位 + 產出增/減柱位建議（簡報加分項）
  - 調度層（即時）：需求密度「不進」即時調度觸發。當下要不要調車仍由規則引擎吃預測區間（ADR-004）。
    現行不能改柱位，長期規劃指標不可當即時觸發依據。

六個行為指標（外部 AI 反饋，零外部成本）：
  - 日夜活動比：白天活動 ÷ 夜間活動 → 就業型 vs 住宅型
  - 平假日比：週末活動 ÷ 平日活動 → 通勤型 vs 休閒型
  - 早晚峰方向：早上淨流出 or 淨流入 → 住宅端 vs 辦公端
  - 峰型：單峰 / 雙峰 / 平坦 → 轉運 vs 一般 vs 觀光
  - 需求密度：日均活動量 ÷ 柱數 → 規劃是否吃緊
  - 空滿頻率：觸底/觸頂次數 → 值不值得調度

活動量定義：相鄰時段可借車數變化的絕對值（|Δ available_bikes|），代表借+還的總周轉。

對外暴露：
    compute_profile(series, total_docks) -> dict   # 站點行為指紋（需足夠歷史）
    classify_station_type(profile) -> str          # 由指紋分站型（人話標籤）
"""

from __future__ import annotations
from typing import Optional

# 白天/夜間切分（可 config）：白天 06:00~22:00
_DAY_START, _DAY_END = 6, 22


def compute_profile(series, total_docks: Optional[int] = None) -> dict:
    """從站點歷史序列算行為指紋。

    series：pandas DataFrame，含 timestamp、available_bikes、available_docks。
            應為足夠長度（如整段訓練期）；新站無足夠歷史時回 sparse=True，走冷啟動 fallback。
    total_docks：柱位數（算需求密度）；未給則從 series 推。

    回傳六指標。活動量 = |相鄰時段 available_bikes 變化| 的總和。

    ★★★ 資料洩漏警告（ADR-013/014 補記 F-01）★★★
    本函式對「傳入的整個 series」計算，不含任何窗口限制。
    呼叫者（特徵組裝 pipeline）**必須只傳訓練期資料**（如 1~5 月），
    絕不可傳含驗證/預測期（如 6 月）的資料，否則指紋會洩漏未來、驗證分數虛高且不報錯。
    站型分群的 fit 同樣只能用訓練期。此約束須在 pipeline 層級強制。
    """
    import pandas as pd

    if series is None or len(series) < 48:   # 不足一天
        return {"sparse": True, "reason": "歷史不足，走冷啟動 fallback（ADR-001/014）"}

    s = series.copy()
    s["ts"] = pd.to_datetime(s["timestamp"])
    s["hour"] = s["ts"].dt.hour
    s["weekday"] = s["ts"].dt.weekday
    s["activity"] = s["available_bikes"].diff().abs().fillna(0)

    total_activity = s["activity"].sum()
    n_days = max(1, len(s) / 48.0)
    daily_activity = total_activity / n_days

    # 日夜活動比
    day_act = s.loc[(s["hour"] >= _DAY_START) & (s["hour"] < _DAY_END), "activity"].sum()
    night_act = total_activity - day_act
    day_night_ratio = round(day_act / night_act, 2) if night_act > 0 else None

    # 平假日比
    weekend_act = s.loc[s["weekday"] >= 5, "activity"].sum()
    weekday_act = s.loc[s["weekday"] < 5, "activity"].sum()
    # 正規化到每日（週末2天、平日5天）
    we_daily = weekend_act / 2
    wd_daily = weekday_act / 5
    weekend_ratio = round(we_daily / wd_daily, 2) if wd_daily > 0 else None

    # 早晚峰方向：早上(07-09)淨流出(可借減少)為正=住宅端；晚上(17-19)
    morning = s[(s["hour"] >= 7) & (s["hour"] < 9)]["available_bikes"].diff().sum()
    evening = s[(s["hour"] >= 17) & (s["hour"] < 19)]["available_bikes"].diff().sum()
    # 早上可借減少(<0)→淨流出→住宅端（大家借車離開）
    peak_direction = "residential" if morning < 0 else ("office" if morning > 0 else "flat")

    # 峰型：看一天內活動量的小時分布有幾個峰
    hourly = s.groupby("hour")["activity"].sum()
    peak_shape = _classify_peak_shape(hourly)

    # 需求密度（規劃層指標）
    cap = total_docks or int(s["available_docks"].add(s["available_bikes"]).median())
    demand_density = round(daily_activity / cap, 2) if cap > 0 else None

    # 空滿頻率
    empty_freq = round((s["available_bikes"] <= 0).mean(), 4)
    full_freq = round((s["available_docks"] <= 0).mean(), 4)

    return {
        "sparse": False,
        "daily_activity": round(daily_activity, 1),
        "day_night_ratio": day_night_ratio,
        "weekend_ratio": weekend_ratio,
        "peak_direction": peak_direction,
        "peak_shape": peak_shape,
        "demand_density": demand_density,       # 規劃層：柱位建議用，不進即時調度
        "empty_freq": empty_freq,
        "full_freq": full_freq,
        "capacity": cap,
    }


def _classify_peak_shape(hourly) -> str:
    """由每小時活動量分布判峰型：單峰/雙峰/平坦。"""
    import numpy as np
    vals = hourly.reindex(range(24), fill_value=0).values.astype(float)
    if vals.sum() == 0:
        return "flat"
    norm = vals / vals.max()
    # 數「明顯高於鄰居」的峰（簡易法）：> 0.6 且為局部極大
    peaks = 0
    for h in range(24):
        v = norm[h]
        prev = norm[(h - 1) % 24]
        nxt = norm[(h + 1) % 24]
        if v > 0.6 and v >= prev and v >= nxt:
            peaks += 1
    # 變異係數低 → 平坦
    cv = vals.std() / vals.mean() if vals.mean() > 0 else 0
    if cv < 0.5:
        return "flat"
    return "double_peak" if peaks >= 2 else "single_peak"


def classify_station_type(profile: dict) -> str:
    """由行為指紋分站型（人話標籤），供與 POI 推導的地理類型對照（ADR-014）。"""
    if profile.get("sparse"):
        return "unknown_new_station"

    dn = profile.get("day_night_ratio") or 1.0
    we = profile.get("weekend_ratio") or 1.0
    shape = profile.get("peak_shape")
    direction = profile.get("peak_direction")

    # 規則式分型（可人話描述）
    if shape == "double_peak" and we < 0.8:
        return "commuter_residential" if direction == "residential" else "commuter_office"
    if we > 1.2:
        return "leisure_tourism"        # 週末明顯高 → 休閒觀光
    if shape == "flat" and dn > 1.5:
        return "transit_hub"            # 全天平均高、日間活躍 → 轉運
    if profile.get("daily_activity", 0) < 5:
        return "low_traffic"            # 低流量
    return "mixed"
