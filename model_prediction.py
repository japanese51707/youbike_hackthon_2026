"""
預測模型（T3, D2/D3/D5）
========================
D2: LightGBM 特徵化路線；乘法公式降級為可解釋 baseline 對照組
D3: 輸出不確定區間（quantile regression），不只點估計
D5: 時間切分：1~5月訓練、6月驗證。禁止隨機切分。

目標：預測每站下一個時段的「可借車數」
特徵：時間特徵、站點特徵、歷史統計特徵

輸出：
- output/model_results/model_comparison.csv（baseline vs LightGBM MAE 對比）
- output/model_results/feature_importance.csv
- output/model_results/prediction_sample.csv（含區間上下界的預測樣本）
"""

import pandas as pd
import numpy as np
import lightgbm as lgb
from pathlib import Path
import warnings
warnings.filterwarnings("ignore")

OUTPUT_DIR = Path("output")
PARQUET_DIR = OUTPUT_DIR / "youbike_parquet"
MODEL_DIR = OUTPUT_DIR / "model_results"
MODEL_DIR.mkdir(parents=True, exist_ok=True)


def load_and_prepare():
    """載入資料並建立特徵"""
    print("📂 載入資料...")
    dfs = []
    for partition in sorted(PARQUET_DIR.iterdir()):
        if partition.is_dir() and "year_month=" in partition.name:
            ym = partition.name.split("=")[1]
            df = pd.read_parquet(partition / "data.parquet")
            df["year_month"] = ym
            dfs.append(df)
    df = pd.concat(dfs, ignore_index=True)

    df["dt"] = pd.to_datetime(df["日期"])
    df = df.sort_values(["場站名稱", "dt"]).reset_index(drop=True)
    print(f"   總筆數: {len(df):,}")
    return df


def build_features(df):
    """
    建立預測特徵
    目標 y = 下一個時段的可借車數
    """
    print("\n🔧 建立特徵...")

    # === 時間特徵 ===
    df["hour"] = df["dt"].dt.hour
    df["dayofweek"] = df["dt"].dt.dayofweek
    df["is_weekday"] = (df["dayofweek"] < 5).astype(int)
    df["day_of_month"] = df["dt"].dt.day
    df["month"] = df["dt"].dt.month

    # 時段編碼（sin/cos 循環特徵）
    df["hour_sin"] = np.sin(2 * np.pi * df["hour"] / 24)
    df["hour_cos"] = np.cos(2 * np.pi * df["hour"] / 24)
    df["dow_sin"] = np.sin(2 * np.pi * df["dayofweek"] / 7)
    df["dow_cos"] = np.cos(2 * np.pi * df["dayofweek"] / 7)

    # === 站點特徵 ===
    # 站點容量分級
    df["capacity_bin"] = pd.cut(df["總車柱數"], bins=[0, 20, 40, 60, 100], labels=[0, 1, 2, 3]).astype(int)

    # === 當前狀態特徵 ===
    df["current_usage_rate"] = df["可借車數"] / df["總車柱數"]
    df["current_empty_rate"] = df["可還位數"] / df["總車柱數"]

    # === 歷史 lag 特徵（前 1~3 個時段） ===
    for lag in [1, 2, 3]:
        df[f"available_lag{lag}"] = df.groupby("場站名稱")["可借車數"].shift(lag)

    # 前一時段的變化量
    df["delta_lag1"] = df["可借車數"] - df["available_lag1"]

    # === 同站同時段歷史均值（用 station encoding 替代） ===
    # 每站 × 星期 × 小時 的歷史平均可借車數
    station_hour_mean = df.groupby(["場站名稱", "is_weekday", "hour"])["可借車數"].transform("mean")
    df["station_hour_avg"] = station_hour_mean

    # === 目標變數 ===
    # y = 下一個時段的可借車數
    df["y_next"] = df.groupby("場站名稱")["可借車數"].shift(-1)

    # 丟掉缺失值
    feature_cols = [
        "hour", "dayofweek", "is_weekday", "day_of_month", "month",
        "hour_sin", "hour_cos", "dow_sin", "dow_cos",
        "總車柱數", "capacity_bin",
        "可借車數", "可還位數", "current_usage_rate", "current_empty_rate",
        "available_lag1", "available_lag2", "available_lag3", "delta_lag1",
        "station_hour_avg",
    ]

    df_clean = df.dropna(subset=feature_cols + ["y_next"]).copy()
    # 確保所有特徵和目標都是 float（LightGBM 不接受 nullable Int）
    for col in feature_cols:
        df_clean[col] = pd.to_numeric(df_clean[col], errors="coerce").astype(np.float32)
    df_clean["y_next"] = pd.to_numeric(df_clean["y_next"], errors="coerce").astype(np.float32)
    df_clean = df_clean.dropna(subset=feature_cols + ["y_next"])
    print(f"   有效特徵筆數: {len(df_clean):,}")
    print(f"   特徵數: {len(feature_cols)}")

    return df_clean, feature_cols


def train_test_split_temporal(df):
    """
    D5: 時間切分 — 1~5月訓練、6月驗證
    為了訓練效率，訓練集抽樣 200 萬筆（保持時間和站點分佈）
    """
    print("\n📅 時間切分（D5）...")
    train_full = df[df["year_month"] != "2026-06"]
    test = df[df["year_month"] == "2026-06"]

    # 訓練集抽樣（保持分佈）
    sample_size = min(2_000_000, len(train_full))
    train = train_full.sample(n=sample_size, random_state=42)

    print(f"   訓練集: {len(train):,}（從 {len(train_full):,} 筆抽樣）")
    print(f"   驗證集: {len(test):,}（2026-06 全量）")
    return train, test


def baseline_model(train, test, feature_cols):
    """
    Baseline：乘法公式的簡化版（可解釋 baseline）
    預測 = 同站同時段歷史平均（station_hour_avg）
    """
    print("\n📊 Baseline 模型（歷史平均）...")
    predictions = test["station_hour_avg"].values
    actual = test["y_next"].values

    mae = np.abs(actual - predictions).mean()
    rmse = np.sqrt(((actual - predictions) ** 2).mean())
    print(f"   MAE: {mae:.2f} 台")
    print(f"   RMSE: {rmse:.2f} 台")

    return mae, rmse, predictions


def lightgbm_model(train, test, feature_cols):
    """
    LightGBM 模型（D2）
    - 點估計 + quantile regression（D3: 10%, 90% 區間）
    """
    print("\n🌳 LightGBM 模型...")

    X_train = train[feature_cols].values.astype(np.float32)
    y_train = train["y_next"].to_numpy(dtype=np.float32, na_value=np.nan)
    X_test = test[feature_cols].values.astype(np.float32)
    y_test = test["y_next"].to_numpy(dtype=np.float32, na_value=np.nan)

    # === 點估計（MAE objective）===
    params_point = {
        "objective": "regression",
        "metric": "mae",
        "learning_rate": 0.05,
        "num_leaves": 63,
        "max_depth": 8,
        "min_data_in_leaf": 100,
        "feature_fraction": 0.8,
        "bagging_fraction": 0.8,
        "bagging_freq": 5,
        "verbose": -1,
        "n_jobs": -1,
    }

    print("   訓練點估計模型...")
    train_data = lgb.Dataset(X_train, label=y_train)
    model_point = lgb.train(
        params_point,
        train_data,
        num_boost_round=300,
        valid_sets=[lgb.Dataset(X_test, label=y_test)],
        callbacks=[lgb.log_evaluation(0)],  # 靜默
    )

    pred_point = model_point.predict(X_test)
    mae = np.abs(y_test - pred_point).mean()
    rmse = np.sqrt(((y_test - pred_point) ** 2).mean())
    print(f"   點估計 MAE: {mae:.2f} 台")
    print(f"   點估計 RMSE: {rmse:.2f} 台")

    # === D3: Quantile regression（不確定區間）===
    print("   訓練下界模型（10% quantile）...")
    params_lower = params_point.copy()
    params_lower["objective"] = "quantile"
    params_lower["alpha"] = 0.10

    model_lower = lgb.train(
        params_lower,
        train_data,
        num_boost_round=200,
        callbacks=[lgb.log_evaluation(0)],
    )
    pred_lower = model_lower.predict(X_test)

    print("   訓練上界模型（90% quantile）...")
    params_upper = params_point.copy()
    params_upper["objective"] = "quantile"
    params_upper["alpha"] = 0.90

    model_upper = lgb.train(
        params_upper,
        train_data,
        num_boost_round=200,
        callbacks=[lgb.log_evaluation(0)],
    )
    pred_upper = model_upper.predict(X_test)

    # 區間覆蓋率（理想應接近 80%）
    in_interval = ((y_test >= pred_lower) & (y_test <= pred_upper)).mean()
    avg_interval_width = (pred_upper - pred_lower).mean()
    print(f"   區間覆蓋率: {in_interval*100:.1f}%（目標 ~80%）")
    print(f"   平均區間寬度: {avg_interval_width:.1f} 台")

    # Feature importance
    importance = pd.DataFrame({
        "feature": feature_cols,
        "importance": model_point.feature_importance(importance_type="gain"),
    }).sort_values("importance", ascending=False)

    print(f"\n   === Feature Importance (Top 10) ===")
    for _, row in importance.head(10).iterrows():
        bar = "█" * int(row["importance"] / importance["importance"].max() * 30)
        print(f"   {row['feature']:<25} {row['importance']:>10.0f} {bar}")

    return mae, rmse, pred_point, pred_lower, pred_upper, importance, model_point


def save_results(test, feature_cols, baseline_mae, baseline_rmse,
                 lgb_mae, lgb_rmse, pred_point, pred_lower, pred_upper, importance):
    """儲存所有結果"""
    print("\n💾 儲存結果...")

    # 1. 模型對比表
    comparison = pd.DataFrame({
        "模型": ["Baseline（歷史平均）", "LightGBM（點估計）"],
        "MAE（台）": [f"{baseline_mae:.2f}", f"{lgb_mae:.2f}"],
        "RMSE（台）": [f"{baseline_rmse:.2f}", f"{lgb_rmse:.2f}"],
        "改善幅度": ["—", f"{(baseline_mae - lgb_mae) / baseline_mae * 100:.1f}%"],
    })
    comparison.to_csv(MODEL_DIR / "model_comparison.csv", index=False, encoding="utf-8-sig")
    print(f"   {MODEL_DIR / 'model_comparison.csv'}")
    print(comparison.to_string(index=False))

    # 2. Feature importance
    importance.to_csv(MODEL_DIR / "feature_importance.csv", index=False, encoding="utf-8-sig")
    print(f"   {MODEL_DIR / 'feature_importance.csv'}")

    # 3. 預測樣本（含區間）— 取前 1000 筆展示
    sample = test.head(1000).copy()
    sample["pred_point"] = pred_point[:1000]
    sample["pred_lower_10"] = pred_lower[:1000]
    sample["pred_upper_90"] = pred_upper[:1000]
    sample["actual_next"] = sample["y_next"]
    sample["error"] = sample["actual_next"] - sample["pred_point"]

    sample_cols = [
        "日期", "場站名稱", "行政區", "可借車數", "總車柱數",
        "pred_lower_10", "pred_point", "pred_upper_90", "actual_next", "error"
    ]
    sample[sample_cols].to_csv(MODEL_DIR / "prediction_sample.csv", index=False, encoding="utf-8-sig")
    print(f"   {MODEL_DIR / 'prediction_sample.csv'}")


def main():
    print("=" * 60)
    print("預測模型（T3: D2 + D3 + D5）")
    print("=" * 60)

    df = load_and_prepare()
    df, feature_cols = build_features(df)
    train, test = train_test_split_temporal(df)

    # Baseline
    baseline_mae, baseline_rmse, baseline_pred = baseline_model(train, test, feature_cols)

    # LightGBM
    lgb_mae, lgb_rmse, pred_point, pred_lower, pred_upper, importance, model = lightgbm_model(
        train, test, feature_cols
    )

    # 儲存
    save_results(
        test, feature_cols,
        baseline_mae, baseline_rmse,
        lgb_mae, lgb_rmse,
        pred_point, pred_lower, pred_upper, importance
    )

    print("\n" + "=" * 60)
    print("✅ T3 預測模型完成！")
    print("=" * 60)
    print(f"\n  摘要:")
    print(f"  - Baseline MAE: {baseline_mae:.2f} 台")
    print(f"  - LightGBM MAE: {lgb_mae:.2f} 台（改善 {(baseline_mae-lgb_mae)/baseline_mae*100:.1f}%）")
    print(f"  - 區間覆蓋率: {((test['y_next'].values >= pred_lower) & (test['y_next'].values <= pred_upper)).mean()*100:.1f}%")
    print(f"  - 驗證方式: 時間切分（1~5月訓→6月驗）")


if __name__ == "__main__":
    main()
