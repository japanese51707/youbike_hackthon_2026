---
status: accepted
date: 2026-09-12
decision-makers:
  - project-owner
approval-evidence: "owner 於 2026-09-12 對話中定調：比賽階段只有 1–6 月歷史、即時是 9 月，選項 A（用同站同星期幾同時段的歷史中位數代理 lag 特徵），讓即時站況帶入模型仍能出完整預測，並要求前端誠實標示為代理近似"
scope:
  - prediction
  - data
related-commits: []
retrospective: true
supersedes:
superseded-by:
---

# ADR-306：即時預測以「同時段歷史」代理 lag 特徵

## 背景與問題

LightGBM 多視野預測需要 lag 特徵（lag_30min / lag_1hr / lag_2hr / lag_1day / lag_1week），
定義為「相對觀測時間絕對往前推 N 分鐘」的該站存量（訓練管線 `feature_pipeline.py` 用 shift(48)=1天、
shift(336)=1週）。

競賽現場的資料時間錯配造成問題：
- 即時資料源（youbike_official）的觀測時間是「現在」（2026-09）。
- 官方歷史只有 2026-01～06。lag_1day/lag_1week 要的「昨天/上週此刻」落在 2026-09，歷史沒有這些日期。
- 即時源本身的觀測 buffer（記憶體、約一週）冷啟動時是空的，重啟即歸零。

結果：即時預測缺 lag 特徵 → `status=degraded`，區間偏寬、資訊價值降低。不決策的後果：
展示時預測長期停在降級狀態，無法呈現模型完整能力。

## 決策

採「**同站 × 同 weekday × 同 time_slot 的歷史中位數**」作為 lag 特徵的代理值（週期性近似）：
- 對每個 lag 目標時刻，換算其 weekday 與 time_slot，查該站在 1–6 月歷史同時段的
  `available_bikes` 中位數，造一個時間戳＝目標時刻的合成觀測點，餵入既有 `transform` 的 lag 迴圈。
- 即時 buffer 有真值時優先用真值；長周期（1天/1週）靠此代理補。
- 後端在預測回應標 `lag_source=historical_proxy`；**前端必須誠實標示為「歷史同時段代理」**，
  不得呈現為絕對前一天/前一週的真值。
- 此代理**只用於預測特徵**，不改站況、不進派工 payload、不改觸發判斷。

## 理由與判準

- **正確性 vs 可用性的權衡**：YouBike 借還有強週期性（同星期同時段行為相近），同時段中位數是
  合理的一階近似；比起長期 degraded，代理能讓模型輸出更完整、區間更收斂。
- **誠實原則**：以 `lag_source` 明示為代理，不宣稱是真值，符合專案「不假裝」的一貫界線。
- **可逆**：代理為獨立建構器 + 一個來源標記，取得真即時序列（未來累積或補完整歷史）後可直接切回。
- **交付時間**：比賽現場只有 1–6 月資料，這是能立即讓即時預測不降級的唯一途徑。

## 考慮過的替代方案

### 方案 B：靠即時 buffer 自然累積
- 優點：語意最正確（真絕對 lag）。
- 缺點：需服務連續運行滿一週且不重啟；冷啟動後長期 degraded。
- 未採用原因：比賽時程與展示需求不允許等一週累積。

### 方案 C：維持 degraded 現狀
- 優點：零改動、語意最保守。
- 缺點：無法展示模型完整能力，區間偏寬。
- 未採用原因：owner 要求即時站況能出完整預測。

### 把 asof 設在歷史範圍內（歷史回放）
- 優點：lag 可取真值。
- 缺點：站況變成歷史某月快照，非即時。
- 未採用原因：與「即時站況預測」的產品目標衝突。

## 影響與後果

### 正面
- 即時預測由 degraded 轉為 ready，四視野 P10/P50/P90 皆可用、區間收斂。
- 建構器與查表可重用於批次推論。

### 負面與代價
- 代理值與真絕對 lag 有分布偏移（尤其節假日、活動日等非典型日）。
- 首次建同時段查表需讀 S3 1–6 月（約 12 秒），以模組級 lru_cache + 啟動背景預熱緩解。

### 尚未解決
- 非典型日（颱風/活動）的代理誤差較大，未特別處理。
- 取得完整即時序列後應切回真 lag（見回復方式）。

## 介面與相容性

- 新增 `HistoricalDataSource.slot_median()` 與模組級查表 `_slot_table()`（historical.py）。
- 新增 `serving_features.build_proxy_lag_observations()` 與 `resolve_asof/recent_observations` helper。
- `LightGBMPredictor.predict_multi` 合併即時 buffer + 代理點傳入 `transform`，並回 `lag_source`。
- `MultiHorizonPrediction` 與 `Prediction`（Pydantic schema）新增 `lag_source` 欄位；
  前端 `StationForecastChart` 讀此欄位標示。
- `main.py` lifespan 於非 mock 資料源背景預熱查表。

## 資安與隱私

- 僅使用公開站點歷史統計（無個資）。讀 S3 走既有憑證/角色，不新增外部依賴。

## 回復或取代方式

- 移除 `predict_multi` 傳入的代理點即回到方案 B（只用即時 buffer）。
- 未來取得完整即時序列或完整歷史時，以新 ADR supersede，切回絕對 lag。

## 驗證方式

- 實測：即時 live 站 `GET /stations/{id}` 回 `source=lightgbm, status=ready, lag_source=historical_proxy`，
  四視野齊全；空站 raw_lower_bound < 0 呈現被壓抑需求（見前端預測圖虛線）。
- 快取：首次建表約 12 秒，之後 O(1)；啟動背景預熱後首個請求 < 0.1 秒。

## 追溯

- 相關 commit：（實作先行，追溯補記）
- 相關檔案：backend/core/data/historical.py、backend/prediction/serving_features.py、
  backend/core/interfaces.py、backend/api/stations.py、backend/models_schema/prediction.py、
  backend/main.py、frontend/src/components/dashboard/StationForecastChart.jsx
- 相關 ADR：ADR-107（多視野預測）、ADR-121（模型與特徵成套載入）、ADR-303（資料可用性契約）、
  ADR-004（AI 只估計）
