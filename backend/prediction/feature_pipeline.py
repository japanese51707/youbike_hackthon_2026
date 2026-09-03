"""
特徵組裝 pipeline（prediction.feature_pipeline）— P1
=====================================================
把 backend/features/ 的因子 + 站點歷史存量，組裝成可訓練/推論的特徵表。
這一層是**防洩漏約束的強制執行點**（ADR-013~016）。

★強制約束（不可繞過）：
  1. 計算窗口（ADR-013/014）：歷史統計/行為指紋/站點識別特徵，只用「目標時點之前」的資料。
     訓練時用訓練期；每列的站點識別特徵用「該列時點之前」的歷史（避免用到未來）。
  2. 缺失值（§5-1）：只 forward fill，禁 interpolate。
  3. 截斷標記（ADR-015）：目標 Δ=0 且同時空站(可借=0)或滿站(可還=0) → 標 is_censored。
     正常站的 Δ=0 不標（是真實低需求）。
  4. lag（ADR-013）：只往過去取。

目標變數：淨變化量 Δ = available_bikes(t+1) − available_bikes(t)（下一時段，30分）。
  規則引擎吃「到達存量」，等同 available(t) + 預測Δ；預測Δ的區間下界/上界即防空/防滿。

本模組先做「單站時序特徵 + 站點識別特徵 + 時間特徵」的最小可行組裝，
先拿到第一個誠實數字；環境類因子（天氣/POI等）待 baseline 出來後以消融決定加不加（F-08）。

對外暴露：
    build_training_frame(df, train_end, ...) -> (X, y, meta)
"""

from __future__ import annotations
import numpy as np
import pandas as pd

# 每 30 分一格
LAG_SLOTS = {"lag_30min": 1, "lag_1hr": 2, "lag_2hr": 4, "lag_1day": 48, "lag_1week": 336}

# 多視野（ADR-017）：格數 → 分鐘數。每 30 分一格，故 h 格 = h*30 分。
HORIZON_STEPS = {1: 30, 2: 60, 3: 90, 4: 120}


def _forward_fill_grid(g: pd.DataFrame) -> pd.DataFrame:
    """單站：補齊 30 分鐘時間格，缺值只 forward fill（禁 interpolate，防洩漏）。"""
    g = g.sort_values("dt").set_index("dt")
    full = pd.date_range(g.index.min(), g.index.max(), freq="30min")
    g = g.reindex(full)
    # 只 forward fill（用過去值補，不用未來）
    for col in ["available_bikes", "available_docks", "total_docks"]:
        g[col] = g[col].ffill()
    g["場站名稱"] = g["場站名稱"].ffill()
    return g.reset_index(names="dt")


def _add_lag_and_target(g: pd.DataFrame) -> pd.DataFrame:
    """單站：加 lag（過去）、變化率、目標 Δ(t→t+1)、截斷標記。"""
    g = g.sort_values("dt").reset_index(drop=True)
    ab = g["available_bikes"]

    for name, k in LAG_SLOTS.items():
        g[name] = ab.shift(k)              # 過去值
    g["change_1hr"] = ab - ab.shift(2)     # 近1小時變化（過去）
    g["change_2hr"] = ab - ab.shift(4)

    # 多視野目標（ADR-017）：h 格後的「累積淨變化」= available(t+h) − available(t)
    #   每 30 分一格：h=1/2/3/4 對應 30/60/90/120 分鐘。直接對累積 Δ 訓練（分位數不可加）。
    for h, mins in HORIZON_STEPS.items():
        g[f"target_delta_{mins}"] = ab.shift(-h) - ab

    # 截斷標記（ADR-015）：以「30分視野目標」判定（可借=0 或 可還=0 且 Δ=0）
    # 注意 target_delta_30 末格為 NaN（shift(-1)），fillna(False) 讓其不算截斷（之後 dropna 會移除）
    at_empty = (g["available_bikes"] <= 0)
    at_full = (g["available_docks"] <= 0)
    censored = (g["target_delta_30"] == 0) & (at_empty | at_full)
    g["is_censored"] = censored.fillna(False).astype(int)

    return g


def build_training_frame(
    df: pd.DataFrame,
    train_end: str,
    profile_by_station: dict | None = None,
):
    """組裝訓練特徵表。

    df：長格式，欄位含 場站名稱、日期(timestamp)、available_bikes/docks、total_docks。
    train_end：訓練期結束日（如 '2026-05-31'），用於分割 + 算站點識別特徵的窗口界線。
    profile_by_station：（可選）站點識別特徵，只能用訓練期算好的（防洩漏）。

    回傳 (frame, feature_cols)：frame 含特徵 + target_delta + is_censored + is_train。
    """
    df = df.copy()
    df["dt"] = pd.to_datetime(df["日期"] if "日期" in df.columns else df["timestamp"])
    if "available_bikes" not in df.columns:
        df = df.rename(columns={"可借車數": "available_bikes",
                                "可還位數": "available_docks",
                                "總車柱數": "total_docks"})

    frames = []
    for name, g in df.groupby("場站名稱"):
        g = _forward_fill_grid(g)
        g = _add_lag_and_target(g)
        frames.append(g)
    frame = pd.concat(frames, ignore_index=True)

    # 時間特徵（衍生，無洩漏）
    frame["hour"] = frame["dt"].dt.hour
    frame["weekday"] = frame["dt"].dt.weekday
    frame["is_weekend"] = (frame["weekday"] >= 5).astype(int)
    frame["month"] = frame["dt"].dt.month
    frame["time_slot"] = frame["hour"] * 2 + (frame["dt"].dt.minute >= 30).astype(int)

    # 訓練/驗證切分（時間切分，ADR-002）
    train_end_ts = pd.to_datetime(train_end) + pd.Timedelta(days=1)
    frame["is_train"] = (frame["dt"] < train_end_ts).astype(int)

    # 站點識別特徵（F-06）：該站 × day_type × time_slot 的「訓練期」歷史 P50 淨流量
    # ★只用訓練期算，避免洩漏（ADR-013/014 窗口約束）
    train_part = frame[frame["is_train"] == 1].copy()
    train_part["dtype"] = train_part["is_weekend"]
    profile = (train_part.groupby(["場站名稱", "dtype", "time_slot"])["target_delta_30"]
               .median().rename("station_slot_p50").reset_index())
    frame["dtype"] = frame["is_weekend"]
    frame = frame.merge(profile, on=["場站名稱", "dtype", "time_slot"], how="left")

    feature_cols = [
        *LAG_SLOTS.keys(), "change_1hr", "change_2hr",
        "available_bikes", "available_docks", "total_docks",
        "hour", "weekday", "is_weekend", "month", "time_slot",
        "station_slot_p50",   # F-06 站點識別特徵（最強）
    ]
    return frame, feature_cols
