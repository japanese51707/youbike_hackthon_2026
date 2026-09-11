# 第二批：真實資料與服務整合

日期：2026-09-11。依 owner「第二批也可以開始做了」及後續「繼續跑完」核准，承接第一批派工安全。未 commit／push，未修改既有營運 SQLite。

## 已完成

| 項目 | 修正後行為 |
|---|---|
| 官方來源 | 驗證 HTTPS、主機、大小、數值與時間；觀測與接收時間分開。停用、過期或品質異常不進派工池。 |
| 降級 | 同源最後成功快照標 stale；無快照回 503。歷史獨立查詢、跨月且限制範圍；缺歷史不使當前站況詳情失敗。 |
| 特徵 | 移除「歷史末尾＋30 分」改寫現況日期；以實際時間取同源 lag，缺資料留 NaN 並列出。推論不重新 fit 訓練統計。 |
| 模型包 | 12 個既有 booster 配對 45 個特徵順序、雜湊及凍結統計；從本機一至六月 Parquet 重建 1,579 站、13,340,606 列，與原 meta 列數一致。衍生包約 2.8 MB，未加入原始資料。 |
| 模型失敗 | 缺失／不匹配 artifact、非有限輸出或交叉分位數顯示 unavailable，不用別站 Mock 替代。缺 lag／天氣的真模型結果標 degraded。 |
| CWA | 快取設期限、保留觀測時間、驗證 TLS，缺測保留缺失。只有不晚於站點觀測且期限內的 CWA 值可進特徵；Mock 天氣不冒充真實特徵。 |
| 派工確認 | 來源模式／觀測／存量更新、資料失效時要求重新預覽；外部讀取不占 SQLite 寫入交易。已確認草稿重送仍回原收據。 |
| 前端 | 預設 API；明確選 Demo 身分、司機簽到、選人車、取得草稿、確認、司機開始及實際存量回報、結案釋放。API 失敗不自動切 Mock。 |
| 呈現 | 來源／時間／降級可見，四視野接模型回應，總覽讀後端任務。孿生頁維持明確 Mock；未接成效不顯示假改善率；外部站名做 HTML 跳脫；靜態地形只讀既有快取，不觸發外部查詢或寫檔。 |
| 部署檔 | 固定 LightGBM／NumPy／certifi，容器補 OpenMP；SQLite 使用 named volume，Docker context 排除 runtime DB／環境檔。 |

新增 accepted ADR-121、206、303。ADR-121 取代 ADR-113 的 serving 決策；ADR-303 承接 ADR-118 資源決策並修訂天氣 TLS／快取。角色入口沿用 ADR-205，受控 Demo 身分限制沿用 ADR-010。

## 驗證

```bash
.venv/bin/python -m pytest backend/tests -o addopts='' -q
.venv/bin/python -m pip check
.venv/bin/python tools/validate_live_api.py
```

前端目錄：

```bash
npm run build
node --test src/api/httpClient.test.js src/utils/escapeHtml.test.js
```

另檢查 Compose SQLite 路徑與 volume 對應及 `git diff --check`。測試包含第一批回歸、freshness／503、跨月歷史、frozen feature parity、真 booster 載入、分位數異常、司機值勤及派工交易。最終：後端 218 tests passed（6.78 秒）；前端 5 tests passed，Vite build 通過；pip check、Compose volume 對應、ADR 索引連結與 git diff --check 通過。

實際公開資料驗證：2026-09-11 09:29:02+08:00 觀測，09:35:10+08:00 接收；1,606 站，其中 1,587 站符合資料派工條件。載入 12 個 booster，回傳 LightGBM degraded 預測及 15 筆資源限制後建議。讀取、預測、草稿確認、開始、逐站回報及结案釋放全部通過，約 5.12 秒。派工測試只寫臨時 SQLite，**不向外部系統派工**；這是接線／交易驗證，不是精度或長時間效能評估。

## 本機使用

`config.yaml` 預設資料模式保留 mock；前端預設 api，因此會明確顯示後端目前使用的 Mock 來源。以下方式用獨立 Demo DB 啟動官方資料並補示範人車，不需改原設定：

```bash
# 專案根目錄；使用獨立 Demo SQLite
.venv/bin/python tools/run_demo_backend.py --db /tmp/youbike-demo-phase2.db --data-mode youbike_official
```

另一個 terminal：

```bash
cd frontend
npm ci
npm run dev
```

瀏覽 `http://localhost:5173`：選 OP-004～006 其中一位，進司機頁簽到；改選 OP-002 調度身分，從建議開預覽，選司機／車輛、產生草稿並確認；切回受指派司機，開始並輸入逐站實際存量。未簽到不列為可用人力，有任務不得下班。

完全獨立的前端展示使用 `VITE_DATA_MODE=mock`；範例見 `frontend/.env.example`。實際環境仍可啟動原有 `backend/main.py`；Docker 使用 `/data/runtime/youbike.db` named volume。

舊模型缺特徵包时，可由原始一至六月資料離線重建：

```bash
PYTHONPATH=backend .venv/bin/python -m prediction.export_serving --data-dir output/youbike_parquet
```

本次已產出 `backend/prediction/_models/serving_features.json`，不用每次啟動重建。日後 train_save 直接從同一訓練 frame 匯出特徵；部署模型與特徵包後重啟服務。

## 限制

- Docker daemon 未啟動，已實際確認無法連線；**未執行容器 build/run**。Python 3.12 容器維持原基線，本機測試使用既有 Python 3.14。
- 未執行瀏覽器自動點擊測試；前端驗證為建置、transport／HTML 跳脫測試，派工另由實際 API 整合驗證。
- 本機沒有九月 archive，近一週歷史明確 unavailable。記憶體觀測從服務收到資料後累積，重啟需重新累積，最多約一週；冷啟動缺 lag 必須標 degraded。
- 真實 CWA 需另設 `CWA_WEATHER_API_KEY`；本次官方整合測試沒有使用此金鑰，天氣特徵列為缺失，未宣稱 CWA 連線實測。
- 官方鏈在 Python 3.14 嚴格 X.509 格式檢查下缺 Subject Key Identifier；只對固定主機採 Python 3.12 基線相容旗標，仍驗證 CA／簽章／期限及 hostname。取捨及移除條件記在 ADR-303，測試確認沒有 verify=False。
- Vite 有大型 bundle 提示（約 3.9 MB minified）；Starlette TestClient 提示未來改用 httpx2，現有檢查仍可執行。
- 模型精度、時序 CV 洩漏、標籤／截斷定義、逐站載量守恆、ETA／路線策略與 optimizer 為第三批。正式認證、多實例及雲端常駐未在本批新增。

## 主要檔案

資料：`backend/core/data/{observations,degradation,youbike_official,historical,weather_source}.py`。
模型：`backend/prediction/{serving_features,export_serving}.py`、`backend/core/interfaces.py`。
流程：`backend/api/{stations,dispatch,operators}.py`、`backend/core/dispatch_confirmation.py`。
前端：`frontend/src/api/httpClient.js`、`taskApi.js`、`RecommendationPanel.jsx`、`BackendDriverPage.jsx`、`BackendOverviewPage.jsx`。

既有使用者文件與工作中新增的 `docs/dispatch_frontend_flow.*` 均保留，未 stage／revert／刪除。
