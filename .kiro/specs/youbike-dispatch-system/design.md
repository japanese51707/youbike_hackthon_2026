# YouBike 智慧調度系統 — 設計文件（DESIGN）

> 承接 Spec 四份文件，把「需求」轉成「怎麼實作」。
> 最後更新：2026-08-31
> 前置：requirements.md / api_contract.md / model_architecture.md / parameter_groups.md 已定案

---

## 1. 系統總覽

### 1.1 三層 + 資料源（對應 api_contract 架構）

```
┌────────────────────────────────────────────────────────┐
│  資料源層  歷史Parquet(S3/Athena) │ TDX即時 │ 天氣/活動  │
│            └── data_source 介面（可抽換：hist/tdx/mock）│
└───────────────────────────┬────────────────────────────┘
                            ▼
┌────────────────────────────────────────────────────────┐
│  執行平面（無狀態、可平行）— B 主責                     │
│   predictor（LightGBM 預測+區間） urgency（緊急度）      │
│   rebalance_detector（調度辨識） param_optimizer(②AI)   │
└───────────────────────────┬────────────────────────────┘
                            ▼
┌────────────────────────────────────────────────────────┐
│  控制平面（有狀態、管決策）— A 主責                     │
│   rule_engine  dispatcher(排程+轉派)  task_manager      │
│   alert_service  override_service(③)  audit             │
│           └── 全部走「預覽→確認→執行→驗證」閘門         │
└───────────────────────────┬────────────────────────────┘
                            ▼
┌────────────────────────────────────────────────────────┐
│  API 層（FastAPI）— A 主責                              │
│   把控制平面結果轉成 HTTP+JSON，前端只碰這層            │
└───────────────────────────┬────────────────────────────┘
                            ▼
┌────────────────────────────────────────────────────────┐
│  前端層（React）— C 主責                                │
│   後台調派員儀表板 │ 調度員任務介面 │ 長官總覽           │
└────────────────────────────────────────────────────────┘
```

### 1.2 設計原則落地（對應 steering + Spec）
- 每個模組一個資料夾/檔案，職責單一（≤300 行拆分）
- 模組間只透過定義好的介面互動（api_contract 的 Schema + 函式簽名）
- 所有閾值權重在 `config.yaml`
- 失敗回傳明確狀態，不靜默

> **關於「AI」的正名**：本系統的「預測模型」是 **LightGBM（傳統機器學習）**，訓練與推論都在本機/EC2 上跑，**不是生成式 AI、不呼叫外部 API、推論免費且毫秒級**。系統裡只有「① 預測存量」和「② 每日參數微調」用到 ML，其餘（緊急度、規則引擎、排序、警示）全是確定性規則/演算法，無 ML。詳見 `docs/模型怎麼跑的（給隊友）.md`。

---

## 2. 專案檔案結構

```
youbike-dispatch/
├── README.md                      # 總入口（怎麼跑、架構、分工）
├── docker-compose.yml             # 一鍵啟動前後端
├── config.yaml                    # ★所有閾值/權重（D8 外部化）
│
├── backend/                       # ── A 主責 ──
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── main.py                    # FastAPI 啟動，只掛路由，掛 CORS/auth 中介層
│   ├── auth.py                    # C-08 最簡身分驗證：X-Operator-Id + 角色對照
│   ├── api/                       # API 路由層（薄，只轉發；靜態路徑先於動態路徑註冊）
│   │   ├── stations.py            # 3.1,3.2,3.9,3.10,3.19（heatmap/timeline 先於 /{id}）
│   │   ├── dispatch.py            # 3.3~3.6,3.13,3.17（overview 在此，不在 operators）
│   │   ├── operators.py           # 3.16
│   │   ├── alerts.py              # 3.11
│   │   ├── optimization.py        # 3.12（②AI 最適化）
│   │   ├── overrides.py           # 3.20（③即時覆寫，與②分開）
│   │   ├── kpi.py                 # 3.7,3.8
│   │   ├── events.py              # 3.15（呼叫 prediction/event_impact）
│   │   ├── audit.py               # 3.14
│   │   └── weather.py             # 3.18
│   ├── core/                      # 控制平面（決策邏輯）
│   │   ├── rule_engine.py         # 觸發判斷（吃區間下界）
│   │   ├── dispatcher.py          # 排程+優先級+位置導向+動態轉派（覆寫在此當最前綴）
│   │   ├── task_manager.py        # 任務狀態機+可續跑
│   │   ├── alert_service.py       # 警示產生+推播
│   │   ├── override_service.py    # ③即時覆寫+時效恢復
│   │   └── audit.py               # 稽核留痕
│   ├── models_schema/             # 資料格式（Pydantic，對應 api_contract 2.x）
│   │   ├── station.py             # StationStatus, StationParams, HistoryPoint
│   │   ├── prediction.py          # Prediction
│   │   ├── dispatch.py            # DispatchRecommendation, DispatchTask
│   │   ├── operator.py            # Operator, DispatchOverview
│   │   ├── alert.py               # Alert
│   │   ├── event.py               # Event
│   │   └── common.py              # AuditLog, Weather
│   ├── data/                      # 資料存取層
│   │   ├── data_source.py         # 抽象介面（get_current/get_history）
│   │   ├── historical.py          # 讀 Parquet/Athena
│   │   ├── tdx.py                 # 接 TDX 即時 API
│   │   ├── mock.py                # 假資料（給前端開發）
│   │   ├── weather_api.py         # 氣象 API
│   │   └── degradation.py         # NFR-10 降級策略
│   ├── prediction/                # ── B 主責（門內自由）──
│   │   ├── predictor.py           # 對外：predict() → Prediction
│   │   ├── urgency.py             # 對外：calc_urgency() → 0~100
│   │   ├── features.py            # 特徵工程
│   │   ├── rebalance_detector.py  # 調度介入辨識（MAD+時段+鄰近）→ 信心分數
│   │   ├── anomaly_tagger.py      # 異常標記（C-07）→ 寫回 Parquet 的 anomaly_tags
│   │   ├── event_impact.py        # 事件影響換算（C-07）→ compute_event_impact()
│   │   ├── param_optimizer.py     # ②AI 每日最適化
│   │   └── artifacts/             # 訓練好的模型檔
│   ├── params/                    # 參數管理（三層架構）
│   │   ├── station_params.py      # 讀寫站點參數
│   │   ├── param_layers.py        # ①②③ 覆寫邏輯
│   │   ├── geo_batch.py           # 群組1 地理批次換算（terrain/area_type）
│   │   └── versioning.py          # 參數版本+回溯
│   ├── simulation/
│   │   └── replay.py              # 模擬重放（Before/After）
│   └── tests/                     # 各模組單元測試（用假資料）
│
├── frontend/                      # ── C 主責 ──
│   ├── Dockerfile
│   ├── package.json               # React+Vite
│   ├── src/
│   │   ├── api/                    # API 呼叫層（分檔，對齊後端分組，非單一 client）
│   │   │   ├── http.js            # 底層 fetch 封裝：baseURL、錯誤處理、逾時（唯一設定點）
│   │   │   ├── stations.js        # 站點相關呼叫
│   │   │   ├── dispatch.js        # 調度相關呼叫
│   │   │   ├── operators.js       # 調度員相關呼叫
│   │   │   ├── alerts.js          # 警示（含 SSE 串流訂閱）
│   │   │   ├── optimization.js    # 每日最適化
│   │   │   └── misc.js            # kpi/weather/events/audit
│   │   ├── hooks/                 # React 狀態封裝（資料抓取+快取）
│   │   │   ├── useStations.js
│   │   │   ├── useAlerts.js       # 訂閱 SSE
│   │   │   └── useTasks.js
│   │   ├── pages/
│   │   │   ├── Dashboard.jsx      # 後台調派員（地圖+建議+KPI+警示）
│   │   │   ├── OperatorApp.jsx    # 調度員（任務佇列+導航+回報）
│   │   │   └── Overview.jsx       # 長官（全域總覽）
│   │   ├── components/
│   │   │   ├── HeatMap.jsx        # 熱點地圖（Leaflet）
│   │   │   ├── DimensionSwitch.jsx# 維度切換
│   │   │   ├── Timeline.jsx       # 時間軸播放
│   │   │   ├── TaskCard.jsx       # 任務框
│   │   │   ├── AlertPanel.jsx     # 警示
│   │   │   └── KpiBoard.jsx       # KPI
│   │   └── mock/mock_data.json    # A 提供的假資料
│
├── scripts/                       # 一次性/批次腳本
│   ├── merge_csv_to_parquet.py    # （已有）資料整合
│   ├── setup_aws.py               # （已有）部署
│   └── build_station_params.py    # 建置各站①基礎參數
│
└── data/                          # 本地資料（gitignore）
    └── output/                    # Parquet + 分析結果
```

---

## 3. 模組邊界與三人分工（每個模組：負責 / 不負責 / 對外介面）

> 模組化鐵則：每個模組能一句話說清「負責什麼、不負責什麼」。改一個模組的內部，不能改變它對外的介面（否則連累別人）。

### A（PM）— backend/api（薄層）+ backend/core（決策）+ backend/data

**api/ 路由層（薄層，但職責明確：驗證輸入 → 呼叫 core → 轉成 JSON）**

| 檔案 | 負責 | 不負責 | 對外 |
|------|------|--------|------|
| `main.py` | 啟動 FastAPI、掛載路由、CORS/auth 中介層 | 任何業務邏輯 | — |
| `auth.py` | 身分驗證（X-Operator-Id → 角色）、閘門權限（C-08） | 不含業務邏輯 | `require_role(...)` |
| `api/stations.py` | 站點端點（靜態路徑 heatmap/timeline 先於 `/{id}` 註冊，避免被吃掉） | 不算緊急度、不判斷調度 | HTTP 3.1,3.2,3.9,3.10,3.19 |
| `api/dispatch.py` | 調度端點 + 全域總覽 overview | 不做排程演算法本身 | HTTP 3.3~3.6,3.13,3.17 |
| `api/operators.py` | 調度員清單/詳情 | 不算任務分配、不含 overview | HTTP 3.16 |
| `api/alerts.py` | 警示端點 + SSE 串流 | 不判斷警示條件 | HTTP 3.11 |
| `api/optimization.py` | ②AI 最適化審核端點 | 不跑最適化演算法、不含③覆寫 | HTTP 3.12 |
| `api/overrides.py` | ③即時覆寫端點 | 不含②最適化 | HTTP 3.20 |
| `api/kpi.py` | KPI + 模擬重放端點 | 不算 KPI 本身 | HTTP 3.7,3.8 |
| `api/events.py` | 活動端點 → 呼叫 prediction/event_impact | 不算影響度本身 | HTTP 3.15 |
| `api/audit.py` / `weather.py` | 對應端點的轉發 | — | HTTP 3.14,3.18 |

> 薄層的價值：API 只做「驗證輸入格式 + 呼叫對應 core 函式 + 統一錯誤處理 + 轉 JSON」。所有決策邏輯在 core，所以改 API 不會動到決策，改決策不會動到 API。
> 路由順序（小不一致修正）：靜態路徑（`/stations/heatmap`、`/stations/timeline`）必須先於動態路徑（`/stations/{station_id}`）註冊，否則會被當成 station_id 吃掉。

**core/ 控制平面（決策邏輯）**

| 檔案 | 負責 | 不負責 | 對外介面 |
|------|------|--------|---------|
| `rule_engine.py` | 吃預測區間下界，判斷是否觸發調度、產觸發原因 | 不排序（交 dispatcher）、不算預測 | `evaluate(station, prediction, params) → 觸發?+原因` |
| `dispatcher.py` | 優先級排序、位置導向分配、動態轉派、路線組合 | 不判斷單站是否該調度 | `build_recommendations(triggers) → list`、`assign_next(operator) → task` |
| `task_manager.py` | 任務狀態機、可續跑、逐站回報 | 不決定派給誰 | `create/update/report/get_status` |
| `alert_service.py` | 警示產生、分級、推播、webhook | 不算緊急度 | `check_and_emit(states) → alerts` |
| `override_service.py` | ③ 即時覆寫、時效/完成恢復 | 不動模型參數 | `apply/cancel/list_active` |
| `audit.py` | 稽核留痕（誰/何時/做什麼） | — | `log(event)`、`query(filter)` |

**data/ 資料存取層**

| 檔案 | 負責 | 不負責 | 對外介面 |
|------|------|--------|---------|
| `data_source.py` | 抽象介面（可抽換） | 不管實際來源 | `get_current_status()`、`get_history()` |
| `historical.py` / `tdx.py` / `mock.py` / `youbike_official.py` | 各自實作介面 | 不加工資料 | 同上介面 |
| `degradation.py` | NFR-10 降級（過期資料/歷史同時段） | 不決定何時降級（由呼叫方判斷 API 掛） | `fallback(reason) → data + 過期標記` |

> **資料源預留彈性（重要）**：現場的即時資料源不確定是 TDX 還是 **YouBike 公司自己的即時源**。因為所有資料源都實作同一個 `data_source.py` 介面，新增一個來源只要：
> 1. 新增一個檔案（如 `youbike_official.py`）實作 `get_current_status()` / `get_history()`
> 2. 在檔案內做「YouBike 官方欄位 → 我們的 StationStatus 格式」的對映
> 3. config.yaml 的 `data_source.mode` 改成 `youbike_official`
>
> 系統其他部分（模型、規則引擎、前端）**完全不用改**。這就是介面抽換的價值——現場給什麼源，接一個 adapter 就好。

**params/ 參數管理（歸 A，geo_batch 除外歸 B）**

| 檔案 | 負責 | 歸屬 |
|------|------|------|
| `station_params.py` | 讀寫站點參數（三層讀取、對外提供當前生效參數） | A |
| `param_layers.py` | ①②③ 覆寫優先序邏輯 | A |
| `versioning.py` | 參數版本存檔 + 回溯（在 approve 之後才存版本） | A |
| `geo_batch.py` | 群組1 地理批次換算（terrain/area_type/鄰近站） | **B** |

### B（空間工程師）— backend/prediction（門內自由）+ params/geo_batch

| 檔案 | 負責 | 不負責 | 對外介面（契約，不可變） |
|------|------|--------|------------------------|
| `predictor.py` | 預測模型（演算法/特徵/訓練皆自由） | 不做調度決策 | `predict(...) → Prediction（含區間）` |
| `urgency.py` | 緊急度計算，校準吻合歷史後續 | 不排序任務 | `calc_urgency(...) → 0~100` |
| `features.py` | 特徵工程 | — | 內部用 |
| `rebalance_detector.py` | 調度介入辨識（MAD+時段+鄰近） | — | `detect(history) → 信心分數` |
| `param_optimizer.py` | ②AI 每日最適化，產調整摘要 | 不直接套用（要人工確認） | `optimize(lookback) → 調整摘要` |
| `params/geo_batch.py` | 群組1 地理批次換算（terrain/area_type/鄰近站） | — | `compute_geo_params(stations) → params` |

### C（品質工程師）— frontend/

| 層 | 檔案 | 負責 | 不負責 |
|----|------|------|--------|
| API 層 | `api/http.js` | fetch 封裝、baseURL、錯誤處理 | 不含畫面邏輯 |
| API 層 | `api/*.js` | 各分組的 API 呼叫 | 不直接渲染 |
| 狀態層 | `hooks/*.js` | 資料抓取、快取、SSE 訂閱 | 不含樣式 |
| 頁面 | `pages/Dashboard.jsx` | 後台調派員儀表板組裝 | 不寫 API 細節（用 hooks） |
| 頁面 | `pages/OperatorApp.jsx` | 調度員任務介面 | 同上 |
| 頁面 | `pages/Overview.jsx` | 長官總覽 | 同上 |
| 元件 | `components/*.jsx` | 單一 UI 元件（地圖/時間軸/任務框...） | 不管資料來源（吃 props） |

**介面契約 = 三人的共用語言。** B 保證 `predict()`/`calc_urgency()` 格式；C 依賴 API 回傳格式（先用 mock_data.json）；A 定義並維護契約 + 整合。**改內部不改介面，就不會互相破壞。**

---

## 4. 資料流（三條主要路徑）

### 4.1 即時監控 → 警示 → 調度建議
```
data_source 取最新站況
  → predictor 預測（含區間）
  → urgency 算緊急度
  → alert_service 判斷是否警示 → 推前端
  → rule_engine 判斷是否觸發調度
  → dispatcher 排序產生建議
  → API /dispatch/recommendations → 前端顯示
  → 【人工確認閘門】POST /dispatch/confirm
  → task_manager 建立任務 → 派發
```

### 4.2 調度員任務循環
```
調度員接任務（task_queue）
  → 導航執行 → 逐站回報
  → POST /dispatch/tasks/{task_id}/report（含位置，統一路徑）
  → task_manager 更新狀態 + 驗證
  → dispatcher 依位置重算下一個任務
  → 若有更適合的人接未執行緊急任務 → 動態轉派 + 通知
```

### 4.3 每日 AI 最適化
```
排程每日觸發 param_optimizer（產生一筆 review_id）
  → 讀近 N 天資料（排除異常標記日）
  → 逐站微調參數（幅度上限）→ 算出「建議新參數」（尚未套用、尚未存版本）
  → 產出格式化摘要 → GET /optimization/daily-review（帶 review_id）
  → 【人工確認】approve / reject / 逐站二次定義
  → approve 後才：versioning 存舊版 → 套用新參數
  → reject 則：丟棄建議，維持原參數（不留版本）
```
> 防堆積（釐清項）：`daily-review` 帶 `review_id`；若上一筆尚未審批，新排程 skip（不重複產生待審）。versioning 一定在 approve **之後**，避免未採用的建議污染版本歷史。
```

---

## 5. 儲存設計（對應 FR-12 熱溫冷）

| 資料 | 儲存 | 保留 | 用途 |
|------|------|------|------|
| 即時站況（熱） | 記憶體/快取 | 近 1~2 週 | 即時推論、現場調度 |
| 歷史快照（溫） | S3 Parquet + Athena | 近 1~3 個月 | 重訓練、時間軸、趨勢 |
| 歷史（冷） | S3 歸檔 or 刪除 | >3 個月 | 歸檔 |
| 站點參數 | JSON/SQLite | 持久 + 版本 | 三層參數、回溯 |
| 任務/稽核 | SQLite | 持久 | 任務狀態、稽核留痕 |
| 設定 | config.yaml | 持久 | 閾值權重 |

> 黑客松規模：SQLite 足夠，不需要 PostgreSQL/Redis。時間軸讀預存歷史（NFR-9）。

---

## 6. 資安設計（對應 NFR-8 + 知識庫「系統設計的分層模型」的安全柱）

前後端分離部署時，前端與後端之間有反向代理（Nginx）。這層必須主動處理下列風險，不能預設安全。

### 6.1 反向代理 / API 邊界

| 風險 | 對策 | 負責 |
|------|------|------|
| CORS 過寬（任何來源可呼叫） | 只允許我們的前端網域，不用 `*` | A（main.py 中介層） |
| API 被繞過前端直接打 | 敏感端點驗證權限（見下表） | A |
| 反向代理洩漏內部資訊 | 統一錯誤格式，不外洩框架版本/內部路徑/DB 錯誤 | A |
| 明文傳輸 | 強制 HTTPS（反向代理層） | A（部署） |
| 請求洪水 | Rate limiting（反向代理或 API 層） | A |
| 注入攻擊 | 輸入驗證（Pydantic）+ 參數化查詢 | A + B |

### 6.2 存取控制（誰能做什麼）

| 動作 | 誰能做 | 保護方式 |
|------|--------|---------|
| 確認派發（閘門） | 調派員/主管 | 需權限，前端隱藏按鈕不算保護 |
| 緊急覆寫 ③ | 調派員/主管 | 需權限 |
| 每日最適化 approve | 維護人員 | 需權限 |
| 回報任務 | 該任務的調度員本人 | 驗證身分 |
| 讀取站況/KPI | 一般唯讀 | 可較寬鬆 |

> 原則（知識庫「邊界、限制」）：**權限一定在後端驗，前端不可信。** 前端不顯示按鈕 ≠ 功能被保護，任何人都能直接對後端發請求。

### 6.3 機關 webhook（/alerts/subscribe）
- callback URL 需驗證來源（token 或簽章），避免任意端點被塞資料
- 推播失敗要重試但有上限，不無限重放

### 6.4 資料保護
- 前端只透過 API 存取，不直接連資料庫（見 §1 架構）
- 不在前端存放敏感設定（API 金鑰等放後端）
- 稽核記錄本身也要保護（不可被前端竄改）

### 6.5 出向資安（我方主動發出的請求 — 雙向考量）

> 資安是雙向的：不只防「別人打我」，也要防「我去打別人 / 別人回我」。詳見知識庫〈資安是雙向的〉。

| 出向情境 | 風險 | 對策 | 負責 |
|---------|------|------|------|
| 接 TDX / 氣象 API | 對方回傳異常或被入侵的資料 | 回應當「不可信輸入」驗證，異常值不直接進模型/DB | A + B |
| 推 webhook 到機關 | 送到偽造端點、SSRF | 驗證目標 token/簽章、限制可達範圍 | A |
| 對外請求帶憑證 | API key 外洩 | 憑證只在後端、不進版控、不寫 log | A |
| 對外請求超時 | 對方掛掉拖垮自己 | 設超時 + 重試上限 | A |
| 資料外流 | 不該外流的資料被送出 | 不把 PII/內部狀態透過對外請求送出 | A |

**設計檢查法**：資料流圖上**每一條進出系統邊界的箭頭**都要問——進來的問「他能不能騙我」，出去的問「我會不會被帶壞或洩漏」。

---

## 6.6 工程化規範（吸收「接住」專案的成熟做法）

「接住」專案（benefits-navigation-agent）已驗證的工程化配置，我們沿用：

| 項目 | 檔案 | 作用 |
|------|------|------|
| Repo 層 AI 指令 | `AGENTS.md` | 給 AI agent 的 repo 規則（核准閘門、安全、commit） |
| 開發規範 | `.kiro/steering/development_principles.md` | 12 條原則（模組化、資安雙向、Git 嚴謹規範） |
| 貢獻規範 | `CONTRIBUTING.md` | Conventional Commits + scope 清單 |
| 環境變數範本 | `.env.example` | 標明不 commit 真值，列出所有需要的 key |
| 架構決策 | `docs/decisions/*.md` | ADR：團隊選定架構時記錄 |
| Secrets 掃描 | push 前執行（steering §12.1） | 防止密鑰進 public repo |

**核心紀律（對應知識庫「做出來很便宜、做得扎實一樣貴」）：**
- 這些「不好玩但重要」的工程化，變成**流程**（固定檢查點）而非靠記憶
- LLM/AI 只估計、規則引擎決策——這條約束寫進 AGENTS.md 和 steering，不可違反

---

## 7. config.yaml 完整定義

這是系統的「控制面板」——所有數字集中在這，改這裡就能調整系統行為，不用改程式碼。交通局的人未來也能自己調。

```yaml
# ── 資料源（NFR-7 可抽換）──
data_source:
  mode: "mock"              # mock / historical / tdx / youbike_official（現場改這裡切換）
  tdx_api_key: ""           # 若用 TDX，正式環境填
  youbike_official_url: ""  # 若現場用 YouBike 公司自己的即時源，填這裡
  refresh_interval_sec: 60  # 多久抓一次即時資料

# ── 資料保留（FR-12 熱溫冷）──
retention:
  hot_days: 14              # 熱資料（即時推論）
  warm_days: 90             # 溫資料（重訓練/趨勢）
  # 超過 warm_days 歸檔或刪除

# ── 觸發規則（rule_engine 用）──
# 注意：空/滿危險「不是死數字」，而是動態的。
# 依各站「歷史同星期同時段」接下來 30 分鐘的淨流出/流入來判斷：
#   預測到達時存量 = 當前存量 - 該站該時段的歷史淨流出
#   若預測到達時存量會觸底（≤ 安全緩衝）→ 觸發
# 下面只設「安全緩衝」與「觸發靈敏度」這種通用參數，實際門檻由模型動態算。
trigger:
  安全緩衝_台數: 2           # 預測到達存量低於此視為危險（各站共用的最低緩衝）
  觸發靈敏度: 1.0           # 對淨流出速率的放大係數（越大越早觸發）
  低水位_借用率百分比: 10    # 輔助門檻（動態判斷之外的保底）
  高水位_借用率百分比: 90
  連續惡化時段數: 2
  # 動態核心：predictor 用「歷史同星期同時段的淨流出/流入」等特徵，產出預測「區間」；
  # rule_engine 一律吃區間下界 lower_bound 當「預測到達存量」，再比對安全緩衝，
  # 而非用固定的「可借車數 ≤ 3」死判斷，也不吃點估計（steering §5 / NFR-1 可解釋性）。
  # 觸發靈敏度的作用：調整後到達存量 = 當前存量 −（當前存量 − 下界）× 觸發靈敏度。
  # 滿站側對稱：預測可還位下界 = 總車柱 − 區間上界 upper_bound，同樣比對安全緩衝。

# ── 目標水位（可被②AI 動態調整覆寫）──
target:
  預設借用率百分比: 50       # 合理預設

# ── 緊急度權重（urgency 用）──
# 規則：所有權重範圍 [0, 1]，最大 1、最小 0。初始值待 B 優化。
urgency_weights:                    # 值域 0~1
  預測到達存量: 1.0
  站群緩衝: 0.5
  影響人數: 0.5
  調度到達時間: 0.3
  容量級距: 0.3
  時效敏感度: 0.3

# ── 環境係數（群組3，全體共用）──
# 規則：值域 [0, 3]，1.0 = 無影響、<1 = 需求下降、>1 = 需求上升。初始值待 B 優化。
weather_factor:                     # 值域 0~3（1.0=無影響）
  sunny: 1.1
  cloudy: 1.0
  rain: 0.7                 # 雨天需求打 7 折
  heavy_rain: 0.4
  typhoon: 0.1
holiday_factor:                     # 值域 0~3（1.0=無影響）
  weekday: 1.0
  weekend: 1.1
  long_holiday: 1.2
season_factor:                      # 值域 0~3（1.0=無影響）
  school_term: 1.0
  vacation: 0.85

# ── 調度資源限制（dispatcher 用）──
# 數字自洽（C-12）：一趟總載運 ≤ 每車容量；單趟時間 ≤ 響應時間。
fleet:
  調度車數量: 20            # 全市可用的調度車數（dispatcher 排程的資源上限）
  每車容量: 25              # 台/車（一趟總載運不得超過此值）
  每趟最大站數: 3           # 由 每車容量 ÷ 平均每站 quantity 推導（原本 5 會超載）
  每時段最大調度站數: 15     # 時段 = 30 分鐘（對齊資料解析度）
  響應時間_分鐘: 30          # 從派發到到達的平均時間，規劃與 KPI 用的基準值
  彈性緩衝分鐘: 10          # 調度到達時間的緩衝

# ── 疲勞管理（dispatcher 用）──
fatigue:
  單班最大搬運量: 150       # 「單次」=單一輪班的累積上限（非單趟）
  法定休息間隔小時: 4
  休息時間分鐘: 30

# ── ③即時覆寫（override_service 用）──
override:
  預設時效分鐘: 120         # 緊急覆寫多久後自動恢復

# ── ②AI 每日最適化（param_optimizer 用）──
optimization:
  回看天數: 3               # 可在後台調
  單次最大調幅百分比: 10     # 幅度上限，避免暴衝
  自動套用: false           # false = 需人工確認

# ── 事件影響（群組4，events 用）──
# 半徑基於「人願意走多遠」，不是活動規模本身。最遠 1~2 公里。
event_radius:
  基礎半徑_km: 0.5           # 借車集水區（80% 使用在 300~500m）
  最大半徑_km: 2.0           # 上限，再遠人不會走
# 影響程度 = 活動人數 vs 該半徑內站點總容納量 的比例
event_impact:
  # 影響比 = 預估活動人數 / 半徑內所有站點總車柱數
  # 例：1萬人湧入、周圍站點總容量 500 → 影響比 20，代表嚴重供需失衡
  # 比例越高 → 該區站點受影響越大 → 需求參數上調越多
  影響比上限: 10.0           # 影響比超過此值視為滿載影響（避免爆表）

# ── 地形分類門檻（geo_batch 用，坡度%）──
terrain_thresholds:
  flat_max: 3
  gentle_max: 5
  moderate_max: 8
  # >8 為 steep

# ── 警示（alert_service 用）──
alert:
  warning_urgency: 60       # 緊急度 ≥ 此 → warning
  critical_urgency: 85      # ≥ 此 → critical

# ── 成本模型（estimated_fuel_cost + ROI 試算用）──
cost:
  油耗_元每公里: 5
  人力_元每小時: 300

# ── 交通估算（dispatcher 交通時間換算）──
travel:
  平均車速_公里每小時: 20
  每站搬運_分鐘: 5

# ── 資安（main.py + middleware 用，A4）──
security:
  allowed_origins: ["http://localhost:5173"]  # CORS 白名單（正式改前端網域）
  allowed_methods: ["GET", "POST", "PUT", "DELETE", "OPTIONS"]  # CORS 收斂，不用 *
  allowed_headers: ["Content-Type", "X-Operator-Id"]           # CORS 收斂，不用 *
  rate_limit_per_min: 120         # 每 IP 每分鐘請求上限（入向 DoS 防護）
  rate_limit_exempt_paths: ["/health"]  # 健康檢查不限流
```

> **A1~A4 新增設定（實作階段補入，此處與 config.yaml 同步）**
>
> - **`data_source`（A1 資料源層）**：`mode`（mock/historical/tdx/youbike_official，換源只改這裡）、`stale_after_sec: 180`（即時資料超過幾秒視為過期，觸發降級標記）、`s3_bucket`/`s3_prefix`（historical 讀 S3 Parquet 分區位置）、`historical_default_month: "2026-06"`（未指定月份時的預設分區）、`tdx_api_key`/`youbike_official_url`（即時源憑證，勿進版控）、`refresh_interval_sec: 60`。
> - **`priority_band`（A2 dispatcher 分級）**：`high_min: 70` / `medium_min: 40`，把緊急度分數 0~100 對照成 high/medium/low。**與 `alert` 段的 `warning_urgency`/`critical_urgency` 用途不同**：`priority_band` 用於調度建議清單分級，`alert` 門檻用於警示分級；兩者未來若要一致化由 A3/A2 協調。
> - **`security` 收斂（A4）**：`allowed_methods` / `allowed_headers` 從 `*` 收斂為明確白名單；`rate_limit_exempt_paths` 讓健康檢查豁免限流。

---

## 8. SQLite Table Schema

黑客松規模用 SQLite（一個檔案就是資料庫，免安裝伺服器）。七張表：

### tasks（任務）
| 欄位 | 型別 | 說明 |
|------|------|------|
| task_id | TEXT PK | 任務 ID |
| task_type | TEXT | normal / emergency |
| task_status | TEXT | pending/assigned/in_progress/completed/retryable/manual_required |
| assigned_operator | TEXT | 指派的調度員 |
| route_json | TEXT | 路線（JSON 陣列，含 stop_status） |
| estimated_travel_minutes | INTEGER | 預估交通時間 |
| estimated_work_minutes | INTEGER | 預估搬運工時 |
| estimated_total_minutes | INTEGER | 預估總時間 |
| estimated_distance_km | REAL | 預估行駛距離 |
| estimated_fuel_cost | REAL | 預估油錢 |
| route_map_url | TEXT | Google Maps 導航連結 |
| assigned_at | TEXT | 指派時間 |
| created_at | TEXT | 建立時間 |
| updated_at | TEXT | 更新時間 |

### audit_logs（稽核）
| 欄位 | 型別 | 說明 |
|------|------|------|
| log_id | TEXT PK | 稽核 ID |
| type | TEXT | emergency_override / task_transfer / optimization ... |
| station_id | TEXT | 相關站點 |
| operator | TEXT | 操作人 |
| action | TEXT | 做了什麼 |
| reason | TEXT | 原因 |
| timestamp | TEXT | 時間 |
| expired_at | TEXT | 覆寫到期時間（可空） |
| task_duration_minutes | INTEGER | 任務花費（可空） |

### station_params（站點參數 + 版本）
| 欄位 | 型別 | 說明 |
|------|------|------|
| station_id | TEXT | 站點 ID |
| version | TEXT | 版本（時間戳） |
| params_json | TEXT | 參數（JSON） |
| param_source | TEXT | base / ai_optimized（③覆寫不寫參數，不在此列） |
| override_active | INTEGER | 1=該站目前有生效中的③即時覆寫 |
| conditions_json | TEXT | 參數背後條件說明 |
| reason | TEXT | 調整原因 |
| created_at | TEXT | 建立時間 |
| is_active | INTEGER | 1=當前生效版本 |

> 主鍵 (station_id, version)，保留所有版本供回溯（FR-7 ②）。

### alerts（警示狀態，對應 Schema 2.5）
| 欄位 | 型別 | 說明 |
|------|------|------|
| alert_id | TEXT PK | 警示 ID |
| level | TEXT | info/warning/critical |
| station_id | TEXT | 站點 |
| message | TEXT | 警示內容 |
| suggested_action | TEXT | 建議動作 |
| triggered_at | TEXT | 觸發時間 |
| acknowledged | INTEGER | 0/1 是否已讀（重啟後保留，避免已讀變未讀） |

### alert_subscriptions（機關 webhook 訂閱，對應 3.11）
| 欄位 | 型別 | 說明 |
|------|------|------|
| subscription_id | TEXT PK | 訂閱 ID |
| callback_url | TEXT | 機關接收網址 |
| levels | TEXT | 訂閱的警示等級（JSON） |
| districts | TEXT | 訂閱的行政區（JSON） |
| token | TEXT | 驗證用 token（出向資安） |

### events（活動事件，對應 Schema 2.7）
| 欄位 | 型別 | 說明 |
|------|------|------|
| event_id | TEXT PK | 活動 ID |
| event_name | TEXT | 名稱 |
| lat / lng | REAL | 位置 |
| expected_attendance | INTEGER | 預估人數 |
| event_type | TEXT | 類型 |
| start_time / end_time | TEXT | 起訖時間 |
| affected_stations_json | TEXT | 影響站點+影響度（event_impact 算出） |

### operators（調度員，對應 Schema 2.8）
| 欄位 | 型別 | 說明 |
|------|------|------|
| operator_id | TEXT PK | 調度員 ID |
| name | TEXT | 姓名 |
| role | TEXT | operator/dispatcher/maintainer（C-08 權限用） |
| password_hash | TEXT | bcrypt 密碼雜湊（絕不存原文；NULL=未設密碼）（A5） |
| is_active | INTEGER | 1=啟用 0=停用（停用取代刪除，保留稽核關聯）（A5） |
| status | TEXT | on_duty/busy/resting/off_duty |
| current_lat / current_lng | REAL | 當前位置 |
| current_task_id | TEXT | 當前任務 |
| task_queue_json | TEXT | 任務佇列（有序） |
| today_completed_tasks | INTEGER | 今日完成數 |
| today_bikes_moved | INTEGER | 今日搬運總量 |
| today_work_minutes | INTEGER | 今日工時（fatigue 判斷用，重啟不歸零） |
| on_duty_since | TEXT | 上班時間 |

> 即時站況（熱資料）不進 SQLite，放記憶體/快取；歷史（溫資料）在 S3 Parquet。SQLite 只放「需要持久 + 需要查詢」的狀態資料。

---

## 9. 資料流圖（.drawio）

**以 `design_dataflow_v2.drawio` 為準**（v1 `design_dataflow.drawio` 保留對照，不再更新）。

v2 圖相對 v1 的修正（審查 v2 第 4 節）：
- 五層架構（資料源 → 執行平面 → 控制平面 → API → 前端），箭頭連到模組而非只連分區框
- **參數三層子系統**拉成獨立區塊：①基礎(geo_batch)→②AI→人工確認閘門→③覆寫→生效參數
- **降級路徑**（degradation，NFR-10）畫在資料源層底部
- **回流路徑**：KPI→自適應修正→預測模型；調度介入辨識→乾淨訓練資料
- 補 `simulation/replay`（FR-5）與站點動態管理（FR-13）模組
- 儲存層移到右側橫切欄（避免與「前端不碰 DB」視覺矛盾）
- 三條資料流路徑（監控警示、任務循環、每日最適化）
- 三人分工的模組歸屬（顏色區分 A/B/C）
- 入向 + 出向資安邊界標示
- 顏色修正：分區底色與模組方塊不同色、指定 fontColor（深色模式可見）、webhook 線不超出內容區

---

## 10. 部署設計

```
開發：各自本機（backend: uvicorn / frontend: vite dev）
整合：docker-compose up（backend + frontend 兩個 container）
Demo：AWS EC2 跑 docker-compose（主）+ 本機（備案）
資料源：config.yaml 切 mock / historical / tdx
```

---

## 11. 開發順序（W1~W4 對應里程碑）

1. **A 先行**：定 Pydantic Schema + 產 mock_data.json + FastAPI 骨架（回傳 mock）→ 解鎖 B、C
2. **並行**：
   - B：predictor / urgency（先跑通介面，再優化）
   - C：前端接 mock 資料把三個頁面畫出來
3. **對接**：A 把 data_source 從 mock 換 historical / tdx，串 B 的模型
4. **收尾**：模擬重放、KPI、資安檢查、Demo 演練
