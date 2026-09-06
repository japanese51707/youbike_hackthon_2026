"""
站點時序自身因子（features.station_timeseries）— ADR-103（最強特徵）
====================================================================
從站點的歷史存量序列衍生「站點自身」時序特徵。附件標「免費、優先級最高」。

★資料洩漏防範（ADR-103 不可違反約束）：
  預測 t+1 時，只能用 ≤ t 的已發生值。所有 lag/變化率/加速度都往「過去」取，
  絕不含 t+1 當下值（那是要預測的目標）。每個特徵標明相對 t 的時間位移，全部 ≤ 0。

特徵（對齊附件群組2）：
  - lag：前 30 分(lag1)、前 1 小時(lag2)、昨日同時段(lag48)、上週同日同時段(lag336)
    （資料每 30 分一筆：1 小時=2 格、1 天=48 格、1 週=336 格）
  - 近 1~2 小時變化率與方向（動能）
  - 變化加速度（變化率的變化 → 正在加速掏空/填滿的早期訊號）
  - 歷史空滿頻率（用「訓練期之前」的統計，避免洩漏）
  - 波動度（P90-P10 帶寬）
  - 日均周轉量
  - 故障車柱缺口（總柱數 − 可借 − 可還，間接推）

輸入：站點的歷史序列 DataFrame（含 timestamp、可借車數、可還位數、總車柱數），
      以及要計算特徵的目標時間 t。輸出「用 ≤ t 資料算出」的特徵。

對外暴露：
    compute_lag_features(series, t)      # 給定序列與時間 t，回 lag/變化率/加速度（只用 ≤t）
    compute_station_stats(series_before) # 歷史空滿頻率/波動度/周轉量（用訓練期前資料）
    broken_dock_gap(total, avail, dock)  # 故障車柱缺口
"""

from __future__ import annotations
from typing import Optional

# 每 30 分一格：lag 對應的格數
_LAG_SLOTS = {"lag_30min": 1, "lag_1hr": 2, "lag_1day": 48, "lag_1week": 336}


def broken_dock_gap(total: int, available_bikes: int, available_docks: int) -> int:
    """故障/離線車柱缺口 = 總柱數 − 可借 − 可還（間接推，非官方故障數）。"""
    return max(0, int(total) - int(available_bikes) - int(available_docks))


def compute_lag_features(series, t) -> dict:
    """給定站點存量序列與目標時間 t，計算 lag/變化率/加速度。

    series：pandas DataFrame，需含 'timestamp'(可排序) 與 'available_bikes'，
            且已按時間升序排列。
    t：目標時間點（字串或可比較），特徵只用 series 中 timestamp <= t 的資料（防洩漏）。

    回傳的特徵全部基於「≤ t 的已發生值」。找不到對應 lag 時該欄為 None。
    """
    import pandas as pd

    # 只取 ≤ t 的資料（防洩漏核心）
    past = series[series["timestamp"] <= t].reset_index(drop=True)
    if past.empty:
        return {k: None for k in
                ["current", *_LAG_SLOTS.keys(),
                 "change_rate_1hr", "change_rate_2hr", "acceleration"]}

    avail = past["available_bikes"].tolist()
    n = len(avail)
    cur = avail[-1]   # t 時刻的值（已發生，可用）

    feat = {"current": cur}
    # lag：往回數 k 格
    for name, k in _LAG_SLOTS.items():
        feat[name] = avail[-1 - k] if n > k else None

    # 近 1 小時變化率（t 與 t-2格 的差；每格30分，2格=1小時）
    feat["change_rate_1hr"] = (cur - avail[-3]) if n > 2 else None
    # 近 2 小時變化率
    feat["change_rate_2hr"] = (cur - avail[-5]) if n > 4 else None
    # 加速度：近1小時變化率 − 前1小時變化率
    if n > 4:
        rate_now = cur - avail[-3]
        rate_prev = avail[-3] - avail[-5]
        feat["acceleration"] = rate_now - rate_prev
    else:
        feat["acceleration"] = None

    return feat


def compute_station_stats(series_before) -> dict:
    """用「目標期之前」的歷史序列算站點體質統計（防洩漏：不含驗證/預測期）。

    series_before：pandas DataFrame，含 available_bikes/available_docks/total_docks。
    回傳：歷史空站頻率、滿站頻率、波動度(P90-P10)、日均周轉量。

    ★★★ 資料洩漏警告（ADR-103 補記 F-01）★★★
    參數名 series_before 表示「應只含目標期之前的資料」，但本函式**不強制檢查**。
    呼叫者（特徵組裝 pipeline）必須確保傳入的是訓練期/expanding window 資料，
    絕不可含驗證/預測期，否則統計量洩漏未來、驗證虛高且不報錯。
    此約束須在 pipeline 層級強制（見 ADR-103 補記待辦）。
    另：缺失值填補只能 forward fill，禁止 interpolate（會用到未來值）。
    """
    import pandas as pd

    if series_before is None or len(series_before) == 0:
        return {"empty_freq": None, "full_freq": None,
                "volatility_p90_p10": None, "avg_daily_turnover": None}

    s = series_before
    n = len(s)
    empty_freq = round((s["available_bikes"] <= 0).mean(), 4)
    full_freq = round((s["available_docks"] <= 0).mean(), 4)
    # 波動度：可借車數的 P90 - P10
    p90 = s["available_bikes"].quantile(0.9)
    p10 = s["available_bikes"].quantile(0.1)
    volatility = round(float(p90 - p10), 2)
    # 日均周轉量：相鄰時段可借車數變化的絕對值總和 / 天數（粗估流量）
    diffs = s["available_bikes"].diff().abs().sum()
    days = max(1, n / 48.0)   # 每天 48 格
    turnover = round(float(diffs / days), 1)

    return {
        "empty_freq": empty_freq,
        "full_freq": full_freq,
        "volatility_p90_p10": volatility,
        "avg_daily_turnover": turnover,
    }
