# 全量離線評估管線（ADR-122 §7）

13.3M 列 × 45 特徵在 7 GB 記憶體跑不動（單次 `build_training_frame` 200 站就會 OOM），
所以拆成四個階段，中間結果落地。站級統計（station_slot_p50／周轉量／行為指紋／POI／地形／
天氣／介入基準）本來就每站獨立計算，**按站分塊不改變任何數字**。

```bash
# 0) 準備：把 6 個月 Parquet 放在 output/youbike_parquet/year_month=*/data.parquet
#    並確保 backend/features 下有 _weather_cache、_elevation_cache.json、poi_data.json

# 1) 按站重切成 10 塊，只留 7 個必要欄位（約 90 秒）
python3 repartition.py 10

# 2) 每塊建特徵矩陣 + 評估 meta（每塊約 70 秒、峰值 5.5 GB；10 塊約 12 分）
for c in $(seq 0 9); do python3 build_chunk.py $c; done

# 3) 修正後協定的時序 CV 選參（單塊 159 站，12 組隨機搜尋，約 15 分）
python3 tune.py 0 12

# 4) 全量全站訓練 12 個 booster + 評估（每視野約 15 分，共約 60 分）
python3 train_eval.py

# 5) 補充分析：把驗證列拆成截斷／未截斷分開比（約 5 分）
python3 censor_split.py
```

輸出：`tuned_params.json`、`full_eval.{json,md}`、`censor_split.json`、
`candidate_models/`（評估用候選 booster，只用 1～5 月訓練，**不是可上線版本**）。

注意：`lgbm_util.py` 讓選參與最終訓練共用同一組參數轉換並一律走 native API——
sklearn 版 `LGBMRegressor` 的 `subsample` 在 `subsample_freq=0`（預設）時其實不生效，
若兩邊用不同 API，搜出來的參數在正式訓練不會是同一個模型。
