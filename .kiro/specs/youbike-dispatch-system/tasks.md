# YouBike 智慧調度系統 — 任務清單（TASKS）

> 承接 requirements / design / api_contract。把設計拆成 A/B/C 三人可各自認領的具體任務。
> 最後更新：2026-08-31｜黑客松：2026-09-12

---

## 分工總覽

| 角色 | 人 | 負責模組 | 對應 design §3 |
|------|-----|---------|---------------|
| **A** | PM | 後端骨架 api/ + core/ + data/ + params/（geo除外）+ 整合 + Git | A 主責 |
| **B** | 空間工程師 | prediction/（模型/緊急度/辨識/最適化/事件影響）+ params/geo_batch | B 主責 |
| **C** | 品質工程師 | frontend/（三頁面 + 元件 + api層 + hooks） | C 主責 |

**開發鐵則**：介面契約（api_contract.md）是共同語言。改模組內部不改介面，就不會互相破壞。

---

## 開發順序（解決「互相等」）

```
W1  A 先行：Schema + mock_data.json + FastAPI 骨架（回 mock）→ 解鎖 B、C
    ↓
W2  三線並行：A 補 core 邏輯 / B 訓練模型 / C 接 mock 畫前端
    ↓
W3  對接：A 把 data_source 從 mock 換真實源 + 串 B 模型；三方整合
    ↓
W4  收尾：模擬重放、KPI、資安檢查、Demo 演練
```

---

## A 的任務（PM — 後端骨架 + 整合）

### A0 — 環境與骨架（★最高優先，解鎖 B/C）✅
- [x] 建 `backend/` 專案結構（依 design §2）
- [x] 定義所有 Pydantic Schema（`models_schema/`，對應 api_contract §2；共 15 個 class = 12 契約 Schema + RouteStop/AlertSubscription/AffectedStation 子模型 + enum）
- [x] 產出 `frontend/src/mock/mock_data.json`（含所有 Schema 的假資料，10 站真實座標）
- [x] FastAPI 骨架：所有端點先回 mock 資料（10 個 api 檔、約 31 端點）
- **交付物**：`backend/` 可 `uvicorn main:app` 啟動、所有 API 回 mock、C 能接 ✅
- **驗收**：`GET /stations` 等端點回傳符合 Schema 的假資料 ✅ 已驗證
- **依賴**：無（第一個做）
- **狀態**：已完成並解鎖 B/C。含 config_loader、mock_store、auth（3 測試帳號）、Dockerfile、docker-compose.yml。權限閘門 401/403/200 驗證通過。**B、C 可基於此開工**（介面契約在 api_contract，mock 資料在 frontend/src/mock/mock_data.json）

### A1 — data_source 層 ✅
- [x] `data_source.py` 抽象介面 + `mock.py` / `historical.py`（讀 S3 Parquet）
- [x] `tdx.py` 骨架（正式源）、`youbike_official.py` 骨架（預留）
- [x] `degradation.py`（NFR-10 降級：過期資料/歷史同時段）
- **驗收**：切 config `data_source.mode` 能換源；API 掛掉走降級且標 `data_freshness` ✅ 已驗證
- **依賴**：A0
- **實作位置**：`backend/core/data/`（含 `__init__.py` 統一入口）
- **備註**：
  - S3 Parquet 為中文欄位，historical.py 做欄位對映到標準英文欄位
  - station_id：用新北市官方即時 API（data.ntpc.gov.tw dataset 010e5b15）建站名→sno 對照表 `station_id_lookup.json`（1600 站），站名比對命中率 99.9%（1575/1576，僅「輕軌淡水行政中心站」未對上，疑改名/停用）。歷史資料據此補上真實 station_id
  - API 端點已接上：`GET /stations`、`GET /stations/{id}` 走 data_source + 降級保護；heatmap/timeline/寫入端點仍暫用 mock（聚合/寫入類，A2 後處理）
  - ⚠️ SSL 憑證問題（待現場解決）：建 station_id 對照表時的資料源為**新北市 open data 平台**（data.ntpc.gov.tw），非 TDX。該平台憑證鏈缺 Subject Key Identifier，導致 `CERTIFICATE_VERIFY_FAILED`。此為**資料來源端問題**，非我方程式碼問題。現場 Demo 主辦會提供正式即時資料源（TDX 或官方源），屆時 tdx.py/youbike_official.py 接入時再依實際源處理憑證。正式代碼不可關閉 SSL 驗證

### A2 — 規則引擎 + 調度 ✅
- [x] `core/rule_engine.py`：吃預測區間**雙向**觸發（下界防空/上界防滿，已重構原型）
- [x] `core/dispatcher.py`：優先級排序、緊急度分級、③覆寫當最前綴
- [x] `core/task_manager.py`：任務狀態機（含 assigned 狀態）、動態轉派、可續跑
- [x] `core/interfaces.py`：B 的 predict/calc_urgency 介面契約 + mock 實作（讓 A 獨立開發）
- **驗收**：給站點狀態 → 輸出排序調度建議（含人話觸發原因）；覆寫站排最前 ✅ 已驗證
- **依賴**：A0、B 的 predict/calc_urgency 介面（先用 mock 值）
- **實作重點**：
  - 觸發雙向：補車看預測**下界**、取車看預測**上界**（取最悲觀側，避免點估計漏觸發）
  - ③覆寫用排序「最前綴」實現（不改 urgency 分數，只強制置頂）
  - 狀態機：pending→assigned→in_progress→completed，emergency 型在 assigned 可轉派、in_progress 鎖定
  - API：`GET /dispatch/recommendations` 已接規則引擎（data_source 站點 → rule_engine → dispatcher）
  - 驗證：mock 10 站 → 7 筆建議（補4取3），權限閘門正常

### A3 — 警示 + 覆寫 + 稽核 ✅
- [x] `core/alert_service.py`：警示產生/分級/SSE 佇列/webhook（含出向 SSRF 驗證）+ 去重
- [x] `core/override_service.py`：③即時覆寫 + 時效自動恢復（惰性過期）
- [x] `core/audit.py`：稽核留痕（append-only，型別驗證）
- **驗收**：站點達門檻自動產警示；覆寫到期自動恢復；動作留稽核 ✅ 已驗證
- **依賴**：A0、A2
- **實作重點**：
  - 警示分級：空/滿站或建議 high→critical、建議 medium→warning、其餘 info；同站同級去重不重複產生
  - 覆寫接上 dispatcher：`GET /dispatch/recommendations` 吃 override 的 active_station_ids 當最前綴（分數不變）
  - 出向資安（steering §11）：webhook callback 須 https 且非內網/本機（SSRF 防護），不安全訂閱被擋
  - 覆寫/取消/自動恢復全寫稽核；audit 為三模組共用底層單例
  - API 已接：`/alerts`、`/alerts/{id}/acknowledge`、`/alerts/subscribe`、`/alerts/stream`、`/stations/{id}/emergency-override`(POST/DELETE)、`/overrides/active`、`/audit/logs`
  - 待現場/正式：webhook 實際 httpx.post 送出（現場才有真 URL）、SSE 改真正 EventSource（骨架先回佇列）

### A4 — 身分驗證 + 資安（不含帳號 DB，那併入 A5）✅
- [x] `auth.py`：X-Operator-Id → 角色驗證改宣告式 Depends（C-08）
- [x] main.py CORS 收斂 + rate limit + 統一錯誤格式（不外洩內部）
- **驗收**：confirm/override 端點驗權限；rate limit 生效；輸入驗證 ✅ 已驗證
- **依賴**：A0

**資安盤點結果（A3 後執行，逐條邊界驗證）**

已驗證無破口 ✅：
- 入向權限：6 個敏感端點（confirm/override×2/optimization×3）全部 無身分=401、越權=403、偽造身分=401
- 出向 SSRF：webhook callback 擋掉 非https / localhost / loopback / AWS metadata(169.254.169.254) / 內網(10.x/192.168.x/172.16.x) / 非http scheme，放行合法 gov https
- 唯讀端點（stations/alerts/health）正常放行；404/500 錯誤不外洩內部細節

A4 加固清單（已完成 ✅ 已驗證）：
- [x] **rate limit**：`backend/middleware.py` RateLimitMiddleware 記憶體滑動視窗，每 IP 每分鐘上限（config.security.rate_limit_per_min），超過回 429 + Retry-After；`/health` 豁免。驗證：上限5時第6次起429
- [x] **CORS 收斂**：methods/headers 改明確白名單（config.security.allowed_methods/allowed_headers），不再用 `*`
- [x] **require_role 宣告式**：改為 `Depends(require_role(...))` 寫在端點簽名，內部自動先驗身分再驗角色，權限檢查無法被遺漏。全端點（confirm/override×2/optimization×4）已改。驗證：401/403/200 全正確
- [x] **統一錯誤格式加固**：StarletteHTTPException(4xx)→request_error、RequestValidationError(422)→validation_error（欄位層級）、Exception(500)→internal_error 通用訊息，皆不外洩堆疊/路徑
- [x] **輸入驗證**：覆寫端點改 Pydantic `OverrideRequest`（reason 必填、expire_minutes 1~1440）取代 raw dict，缺失/超範圍回 422
- [ ] **webhook 實際送出的出向加固**（現場串接時）：httpx.post 帶 token、超時、重試上限、payload 不含內部細節
- 帳號系統（前端加帳號/DB/密碼雜湊）→ 併入 A5（operators 表建立後）
- 註：optimization/dispatch report 等吃 raw dict 的端點，正式接 SQLite/邏輯時再補 Pydantic（目前回 mock，非資安破口）

**警示 API 出入向確認**：
- 入向 `GET /alerts`、`acknowledge`：唯讀/標記，無敏感權限問題（正式上線可加「誰能看警示」的認證，屬 A5 帳號範疇）
- 入向 `POST /alerts/subscribe`：吃 callback_url，已做出向 SSRF 檢查（登記時就擋）
- 出向 webhook（推給機關）：SSRF 檢查到位；實際送出加固待現場
- SSE `/alerts/stream`：現為佇列骨架；正式改 EventSource 時，串流連線要驗證訂閱者身分（A5 帳號後）

### A5 — params 三層 + SQLite
- [ ] `params/station_params.py`、`param_layers.py`（①②③覆寫序）、`versioning.py`
- [ ] 建 SQLite 七張表（design §8）
- **驗收**：讀當前生效參數；②最適化 approve 後才存版本；可回溯
- **依賴**：A0

### A6 — 整合 + 模擬重放
- [ ] `simulation/replay.py`（重構原型，對接正式模組）
- [ ] 串接 B 的模型 + 三方整合測試
- **驗收**：Before/After 數字產出；三頁面串真實後端可跑
- **依賴**：全部

---

## B 的任務（空間工程師 — 模型 + 參數）

> 門內自由：演算法/特徵/權重都是 B 的 know-how，只要守住 `predict()`/`calc_urgency()` 介面。

### B1 — geo_batch 地理參數（可獨立先做）
- [ ] `params/geo_batch.py`：批次算 terrain（高程API→7分類）、area_type（政府分區+POI）、nearby_stations
- **交付物**：1583 站的地理參數（一次算好存檔）
- **驗收**：每站有 terrain/area_type/鄰近站；用真實高程與 POI
- **依賴**：無（可用本地/S3 資料先做）

### B2 — 預測模型 predictor（核心）
- [ ] `prediction/features.py`：特徵工程（時段/lag/潮汐/天氣/地形/區域...）
- [ ] `prediction/predictor.py`：LightGBM 訓練 + `predict()`（輸出含區間）
- **交付物**：訓練好的模型檔（artifacts/）+ predict() 介面
- **驗收**：時間切分驗證（1~5月訓、6月驗）；MAE < 2 台；區間覆蓋 ~80%；輸出符合 Prediction 格式
- **依賴**：B1（地理參數當特徵）

### B3 — 緊急度 calc_urgency
- [ ] `prediction/urgency.py`：緊急度 0~100（校準吻合歷史後續）
- **驗收**：算出的緊急度高的站，歷史上後續確實惡化（校準驗證）；不含③覆寫
- **依賴**：B2

### B4 — 調度介入辨識（有原型）
- [ ] `prediction/rebalance_detector.py`：重構 analysis_rebalancing_detection_v2.py，輸出信心分數
- [ ] `prediction/anomaly_tagger.py`：異常標記寫回 Parquet
- **驗收**：辨識調度痕跡；訓練資料排除異常時段
- **依賴**：無（有原型）

### B5 — 每日最適化 + 事件影響
- [ ] `prediction/param_optimizer.py`：②每日微調（排除異常/幅度上限/產摘要）
- [ ] `prediction/event_impact.py`：`compute_event_impact()`（半徑+供需比）
- **驗收**：產出格式化調整摘要供人工審核；事件影響算出 affected_stations
- **依賴**：B2

---

## C 的任務（品質工程師 — 前端）

> 用 A 提供的 mock_data.json 先開發，不等後端。React + Vite + Leaflet + ECharts + Ant Design。

### C0 — 前端骨架 + API 層
- [ ] `frontend/` Vite 專案、`api/http.js`（fetch 封裝）+ 各 `api/*.js`
- [ ] `hooks/`（useStations/useAlerts/useTasks）
- **交付物**：能呼叫（mock）後端、拿到資料
- **依賴**：A0 的 mock_data.json + api_contract

### C1 — 後台調派員儀表板（Dashboard）
- [ ] 即時熱點地圖（Leaflet，顏色分級）
- [ ] 多維度切換（status/area_type/terrain/district）
- [ ] 調度建議清單 + 確認按鈕（走閘門）
- [ ] KPI 看板、警示面板（SSE）
- **驗收**：地圖顯示 1583 站狀態；切維度變色；按確認派發呼叫 API
- **依賴**：C0

### C2 — 調度員任務介面（OperatorApp）
- [ ] 任務佇列（獨立任務框）、路線圖 + Google Maps 導航連結
- [ ] 逐站完成回報、工時顯示
- **驗收**：顯示任務佇列；點導航開 Google Maps；回報更新狀態
- **依賴**：C0

### C3 — 長官總覽 + 時間軸
- [ ] Overview 全域總覽（人力/成效/站點壓力）
- [ ] 時間軸播放（拖曳看歷史熱點流動）
- **驗收**：總覽數字正確；時間軸拖曳顯示各時間點狀態
- **依賴**：C0

---

## 依賴關係圖

```
A0（骨架+Schema+mock）★
├──→ B 全部（拿到介面契約就能開工）
├──→ C 全部（拿到 mock_data 就能開工）
└──→ A1~A5（後端各模組）
              ↓
        A6 整合（串 B 模型 + C 前端）→ Demo
```

**關鍵**：A0 完成前，B、C 只能先讀文件；A0 一完成，三線並行。所以 A0 是最高優先。

---

## 里程碑對應

| 週 | A | B | C |
|----|---|---|---|
| W1 | A0 骨架 | B1 geo + B4 辨識（有原型） | C0 骨架 |
| W2 | A1 data + A2 規則引擎 | B2 predictor + B3 urgency | C1 儀表板 |
| W3 | A3 警示 + A4 資安 + A5 params | B5 最適化+事件 | C2 調度員 + C3 總覽 |
| W4 | A6 整合 + 模擬重放 | 模型校準收尾 | 前端串真實後端 + 打磨 |

共同 W4：資安檢查、Demo 演練、簡報。

---

## 驗收總表（Demo 要能展示的）

| 項目 | 負責 | 驗收 |
|------|------|------|
| 即時熱點地圖 | C | 1583 站顏色分級 + 維度切換 |
| 預測 + 區間 | B | MAE < 2、區間覆蓋 ~80% |
| 調度建議 | A | 排序 + 人話原因 + 確認閘門 |
| 警示通知 | A | 達門檻自動推（★題目要求） |
| 模擬重放 | A | Before/After 數字 |
| 三層參數 | A+B | ①基礎/②每日微調/③覆寫 |
