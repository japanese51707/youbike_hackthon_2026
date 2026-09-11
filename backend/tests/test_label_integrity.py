"""第三批 A（ADR-122）：用小型固定資料證明標籤與擬合窗口的修正。

這些測試刻意植入四種問題——跨界標籤、補值答案、視野中段的調度介入、跨折統計洩漏——
在修正前會失敗，修正後才會通過。不讀 S3、不訓練模型，只驗證特徵表本身。
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from prediction.feature_pipeline import HORIZON_STEPS, build_training_frame  # noqa: E402

TRAIN_END = "2026-01-20"   # 資料跨過這個界，長視野標籤才會踩到邊界
STEP = pd.Timedelta(minutes=30)


def _rows(station, start, n, values, lat, lng, total=20):
    """造一站的連續 30 分鐘格。values 中的 None 代表該格缺觀測（之後會被補值）。"""
    out = []
    for i in range(n):
        v = values[i % len(values)] if not isinstance(values, dict) else values.get(i)
        if v is None:
            continue          # 缺格：不放進來，由 _forward_fill_grid 補
        out.append({"場站名稱": station, "日期": start + STEP * i,
                    "可借車數": v, "可還位數": total - v, "總車柱數": total,
                    "緯度": lat, "經度": lng})
    return out


def _frame(rows, train_end=TRAIN_END, **kwargs):
    df = pd.DataFrame(rows)
    frame, _ = build_training_frame(df, train_end, **kwargs)
    return frame


@pytest.fixture
def steady():
    """兩站、2026-01-01 起連續 1400 格（約 29 天），跨過 TRAIN_END。

    乙站的波幅隨時間變大（非定常），這樣「換擬合窗口統計量就該改變」才驗得出來。
    """
    start = pd.Timestamp("2026-01-01 00:00")
    pattern = [10, 12, 14, 12, 10, 8, 6, 8]
    rows = _rows("甲站", start, 1400, pattern, 25.010, 121.460)
    growing = []
    for i in range(1400):
        swing = 1 + i // 400                      # 每約 8 天波幅加大一級
        growing.append(10 + (swing if i % 2 == 0 else -swing))
    rows += [{"場站名稱": "乙站", "日期": start + STEP * i,
              "可借車數": v, "可還位數": 20 - v, "總車柱數": 20,
              "緯度": 25.050, "經度": 121.500}
             for i, v in enumerate(growing)]
    return rows


# ── ADR-122 B：跨界標籤 ──

def test_label_crossing_the_split_is_excluded_from_training(steady):
    frame = _frame(steady)
    boundary = pd.Timestamp(TRAIN_END) + pd.Timedelta(days=1)
    for mins in HORIZON_STEPS.values():
        train = frame[frame[f"is_train_{mins}"] == 1]
        target_time = train["dt"] + pd.Timedelta(minutes=mins)
        assert (target_time < boundary).all(), (
            f"{mins} 分視野的訓練列有標籤跨進驗證期")


def test_legacy_input_time_split_would_have_leaked(steady):
    """對照組：舊的 is_train（依輸入時間）確實會讓長視野標籤跨界。"""
    frame = _frame(steady)
    boundary = pd.Timestamp(TRAIN_END) + pd.Timedelta(days=1)
    legacy = frame[frame["is_train"] == 1]
    crossed = (legacy["dt"] + pd.Timedelta(minutes=120)) >= boundary
    assert crossed.any(), "固定資料應該要有跨界列，否則這個測試沒有守到東西"
    fixed = frame[frame["is_train_120"] == 1]
    assert not ((fixed["dt"] + pd.Timedelta(minutes=120)) >= boundary).any()


# ── ADR-122 C：補值 ──

def test_imputed_rows_are_flagged_and_labels_marked():
    start = pd.Timestamp("2026-01-01 00:00")
    rows = _rows("甲站", start, 400, [10, 12, 14, 12], 25.010, 121.460)
    # 挖掉第 100~103 格（4 格＝2 小時），製造需要 forward fill 的缺口
    rows = [r for r in rows if not (start + STEP * 100 <= r["日期"] <= start + STEP * 103)]
    frame = _frame(rows)
    assert frame["is_imputed"].sum() == 4, "補出來的格子必須被標記"
    # 補值格前 4 格（120 分視野）的標籤答案落在補值上 → 必須被標為 target_imputed
    marked = frame[frame["target_imputed_120"] == 1]
    assert len(marked) >= 4
    assert (frame.loc[frame["is_imputed"] == 1, "target_imputed_30"] == 1).all()


# ── ADR-122 D：介入遮罩涵蓋整個視野 ──

def test_intervention_inside_horizon_is_masked_not_only_start_row():
    start = pd.Timestamp("2026-01-01 00:00")
    values = [10, 11, 10, 11] * 350
    rows = _rows("甲站", start, 1400, values, 25.010, 121.460)
    # 在第 200 格灌入一次「調度介入」：一次搬走大半個站
    for r in rows:
        if r["日期"] == start + STEP * 200:
            r["可借車數"] = 0
            r["可還位數"] = 20
    frame = _frame(rows).sort_values("dt").reset_index(drop=True)
    hit = frame.index[frame["dt"] == start + STEP * 200]
    assert len(hit) == 1
    i = int(hit[0])
    assert frame.loc[i, "is_rebalancing"] == 1, "第 200 格本身應被判為調度介入"
    # 120 分視野＝4 格：第 196~200 格的標籤都涵蓋這次介入，都要被遮掉
    assert (frame.loc[i - 4:i, "is_rebalancing_120"] == 1).all()
    # 30 分視野只涵蓋 1 格：第 195 格不該被遮
    assert frame.loc[i - 4, "is_rebalancing_30"] == 0


# ── ADR-122 A：擬合窗口以 fold 為單位 ──

def test_fit_mask_confines_statistics_to_the_fold(steady):
    """把擬合窗口限定在前半段，後半段獨有的站不得出現在統計量裡。"""
    start = pd.Timestamp("2026-01-01 00:00")
    rows = list(steady)
    # 只在後半段（1/20 之後）出現的新站
    rows += _rows("丙站", pd.Timestamp("2026-01-18 00:00"), 500, [4, 6, 8, 6],
                  25.090, 121.540)
    cut = pd.Timestamp("2026-01-12")
    frame = _frame(rows, fit_mask=lambda f: f["dt"] < cut)
    late = frame[frame["station_key"].isin(
        frame.loc[frame["dt"] >= pd.Timestamp("2026-01-18"), "station_key"].unique())]
    only_late = late[~late["station_key"].isin(
        frame.loc[frame["dt"] < cut, "station_key"].unique())]
    assert len(only_late) > 0, "固定資料應包含擬合窗口外才出現的站"
    # 擬合窗口外才出現的站：周轉量統計為 0、站點識別特徵為 NaN（沒有被偷看）
    assert (only_late["station_turnover"] == 0).all()
    assert only_late["station_slot_p50"].isna().all()


def test_fit_mask_changes_fitted_statistics(steady):
    """同一份資料、不同擬合窗口，統計量必須不同——證明它真的只吃窗口內的列。"""
    early = _frame(steady, fit_mask=lambda f: f["dt"] < pd.Timestamp("2026-01-08"))
    late = _frame(steady, fit_mask=lambda f: f["dt"] < pd.Timestamp("2026-01-28"))
    key = "25.05_121.5"          # 乙站：波幅隨時間變大
    a = early.loc[early["station_key"] == key, "station_turnover"].iloc[0]
    b = late.loc[late["station_key"] == key, "station_turnover"].iloc[0]
    assert not np.isclose(a, b), (
        f"換了擬合窗口，周轉量統計卻沒變（{a} vs {b}）＝仍在吃全段資料")


def test_default_fit_mask_is_strictest_horizon(steady):
    """未指定 fit_mask 時，預設用 is_train_120（所有視野的標籤都在訓練期內）。"""
    frame = _frame(steady)
    assert (frame["is_fit"] == frame["is_train_120"]).all()
