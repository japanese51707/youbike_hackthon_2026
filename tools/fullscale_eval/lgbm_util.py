"""選參與最終訓練共用同一組參數轉換與訓練方式，避免「調出來的參數在正式訓練行為不同」。

注意：sklearn 版 LGBMRegressor 的 subsample 只有在 subsample_freq>0 時才生效，
預設 0 等於沒有 bagging。這裡一律走 native API 並在 subsample<1 時設 bagging_freq=1，
讓搜尋到的參數在最終訓練確實照同樣方式作用。
"""
from __future__ import annotations


def to_native(params: dict, alpha: float, seed: int = 42) -> tuple[dict, int]:
    p = {
        "objective": "quantile",
        "alpha": alpha,
        "learning_rate": params.get("learning_rate", 0.05),
        "num_leaves": params.get("num_leaves", 31),
        "min_data_in_leaf": params.get("min_child_samples", 50),
        "feature_fraction": params.get("colsample_bytree", 1.0),
        "lambda_l2": params.get("reg_lambda", 0.0),
        "verbosity": -1,
        "num_threads": 2,
        "seed": seed,
        "deterministic": True,
        "force_row_wise": True,
    }
    subsample = params.get("subsample", 1.0)
    if subsample < 1.0:
        p["bagging_fraction"] = subsample
        p["bagging_freq"] = 1
        p["bagging_seed"] = seed
    return p, int(params.get("n_estimators", 300))


def fit(dataset, params: dict, alpha: float):
    import lightgbm as lgb
    native, rounds = to_native(params, alpha)
    return lgb.train(native, dataset, num_boost_round=rounds)
