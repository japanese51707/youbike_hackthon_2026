"""
Seasonal naive baseline（prediction.baseline）— P1 / 審查 F-02
=============================================================
審查指出原 baseline(4.29) 定義不明、可能過弱。正確 baseline 是 seasonal naive：
「該站 × day_type × 時段 的訓練期歷史中位數」。零成本查表，這類問題通常強得驚人。

評審最可能問「你的模型比單純查歷史平均好多少」——這個 baseline 就是答案。

多視野（ADR-017）：target_col 指定要預測哪個視野的累積 Δ 欄位。
"""

from __future__ import annotations
import pandas as pd


def fit_seasonal_naive(train_frame: pd.DataFrame, target_col: str = "target_delta"):
    """用訓練期資料算查找表：站 × day_type × time_slot → 該視野目標的中位數。"""
    t = train_frame.dropna(subset=[target_col]).copy()
    t["dtype"] = t["is_weekend"]
    table = (t.groupby(["場站名稱", "dtype", "time_slot"])[target_col]
             .median().rename("pred").reset_index())
    global_median = float(t[target_col].median())
    return table, global_median


def predict_seasonal_naive(frame: pd.DataFrame, table, global_median) -> pd.Series:
    """對任意 frame 用查找表預測。查不到用全域中位數。"""
    f = frame.copy()
    f["dtype"] = f["is_weekend"]
    merged = f.merge(table, on=["場站名稱", "dtype", "time_slot"], how="left")
    return merged["pred"].fillna(global_median)
