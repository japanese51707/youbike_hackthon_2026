# 架構決策紀錄（ADR）

本目錄是專案長期決策的單一紀錄庫。開始實作前，先讀本索引與相關 `accepted` ADR；完整強制流程見 `.kiro/steering/decision_governance.md`。

## 狀態

- `proposed`：候選方案，尚不可當成實作依據
- `accepted`：owner／授權決策者已核准，必須遵守
- `rejected`：已否決，保留原因避免重複討論
- `superseded`：已被新 ADR 取代，新舊文件必須互相連結
- `deprecated`：不再建議，但尚無單一取代決策

只有 owner／授權決策者能將 ADR 改為 `accepted`。改變 accepted 決策時新增 superseding ADR，不改寫歷史。

> **Legacy 過渡**：ADR-001～004 在本治理規則建立前已標為「已定案」，繼續視為 legacy `accepted`。它們不因缺少新 frontmatter 失效，也不得由 Agent 補猜核准者或當時未記錄的理由；核心方向若改變，一律用新 ADR supersede。

## 有效決策索引

| 編號 | 決策 | 狀態 | 範圍 | 實作狀態／限制 |
|---|---|---|---|---|
| [ADR-000](ADR-000-ADR編號規則與號段配置.md) | ADR 編號規則與號段配置（分段編號制） | accepted | governance, collaboration | 1xx模型/2xx前端/3xx平台;001-010封存;取號前查登記表 |
| [ADR-001](ADR-001-單一模型分層參數.md) | 單一模型＋分層參數 | accepted | prediction, params | 三層參數已實作；線上模型與特徵包見 ADR-121 |
| [ADR-002](ADR-002-LightGBM選型.md) | 預測模型採 LightGBM | accepted | prediction | 官方模式已接 LightGBM；明確 Mock 模式使用 MockPredictor |
| [ADR-003](ADR-003-運算層EC2資料層Serverless.md) | 運算層 EC2、資料層 Serverless | accepted | infra, data | S3／Athena 已規劃；Git 歷史尚無 EC2 部署證據 |
| [ADR-004](ADR-004-AI只估計規則引擎決策.md) | AI 只估計、規則引擎決策 | accepted | core, prediction | 規則與人工閘門為不可違反約束 |
| [ADR-005](ADR-005-契約先行與Mock並行開發.md) | 契約先行＋符合 Schema 的 Mock 解鎖並行 | accepted（追溯） | api, schemas, collaboration | 後端契約與 Mock 已建立；FastAPI 派工整合已實作，見 ADR-207／302／303 |
| [ADR-006](ADR-006-可抽換資料源與明確降級.md) | 可抽換資料源＋明確 freshness／降級 | accepted（追溯） | data, reliability | 官方 adapter／同源最後快照／503 已實作，見 ADR-303 |
| [ADR-007](ADR-007-API雙向邊界防護.md) | API 入向與出向都視為信任邊界 | accepted（追溯） | api, security | 應用層防護已建；官方與 CWA 即時資料驗證 TLS；正式 webhook 部署仍待後續 |
| [ADR-008](ADR-008-依賴釘選與關鍵行為測試.md) | 精確釘選依賴＋優先測決策關鍵行為 | accepted（追溯） | backend, testing, dependencies | Python 3.12 為容器基線；CI 尚未建立 |
| [ADR-009](ADR-009-SQLite持久化與Repository分層.md) | 黑客松階段使用 SQLite＋Repository | accepted（追溯） | database, backend | 單實例適用；多實例前需重評估 |
| [ADR-010](ADR-010-Demo帳號與後端角色驗證.md) | Demo 本地帳號＋後端角色驗證 | accepted（追溯） | authentication, authorization, security | 無 token/session，只限受控 Demo |
| [ADR-101](ADR-101-預測特徵因子模組化與資料源.md) | 預測特徵四因子模組化＋公開資料源 | accepted | prediction, features, data | 假日/天氣/地形/學生數各一模組；單因子先行，交叉影響待後續；天氣訓練用歷史、現況預測才接即時 |
| [ADR-102](ADR-102-擴充特徵時間POI事件特殊天氣.md) | 擴充特徵：時間衍生/POI距離/事件/特殊天氣 | accepted | prediction, features, data | 承接 ADR-101；POI 用 OSM、區域類型自動推導、事件介面先行、特殊天氣異常日標籤 |
| [ADR-103](ADR-103-時序自身鄰近連動營運面因子.md) | 站點時序自身/鄰近連動/營運面因子 | accepted | prediction, features, data | lag/歷史空滿頻率/波動度/鄰近連動(距離指數衰減)/日出日落/溫度倒U/故障缺口/level shift；含資料洩漏防範約束 |
| [ADR-104](ADR-104-站點行為指紋與需求密度分層.md) | 站點行為指紋/需求密度分層/外部因子降級 | accepted | prediction, features, data | 六個月行為指紋(日夜比/平假日比/峰型/需求密度)；需求密度分規劃層(柱位建議)與調度層(不進即時觸發)；站型分群行為vsPOI兩套對照；外部人口因子降為冷啟動fallback |
| [ADR-105](ADR-105-目標變數定義與截斷樣本處理.md) | 目標變數定義與截斷(censored)樣本處理 | accepted | prediction, features, data | 進訓練前審查F-03；截斷=「Δ=0 且同時空/滿站」才排除/降權(正常站Δ=0保留為真實訊號)+分區間評估；需求插補選配 |
| [ADR-106](ADR-106-調度標註離線與線上分離.md) | 調度介入辨識：離線清訓練資料/上線只事後標註 | superseded（由 ADR-122） | prediction, features, data | 進訓練前審查§5-2；辨識調度僅為清訓練資料(離線用全期合法)；上線不做即時調度偵測,只做事後異常標註供回查 |
| [ADR-107](ADR-107-多視野預測與累積分位數.md) | 多視野預測(30/60/90/120分)+累積分位數 | accepted | prediction, api, core | 進訓練前審查F-04/F-05；直接多視野非遞迴、分位數對累積Δ訓練;horizon用分鐘定義(粒度落差解法);Prediction改horizons[]陣列(改api_contract,通知B/C) |
| [ADR-108](ADR-108-資料品質與站點主檔處理.md) | 資料品質與站點主檔處理 | accepted | data, features, prediction | 站數1521→1576(聯集1583);時間戳floor統一;經緯度為主鍵歸併亂碼站(1583→1579);新舊站分報 |
| [ADR-109](ADR-109-流量加權訓練與決策層信心.md) | 流量加權訓練與決策層信心 | accepted | prediction, features, rules | A樣本權重實測否決(LightGBM已內建);B周轉量保留;C決策層信心分級接dispatcher排序(守ADR-104不進觸發) |
| [ADR-110](ADR-110-超參數優化與時序交叉驗證.md) | 超參數優化與時序交叉驗證 | accepted | prediction | 時序CV選參(6月不參與防洩漏);選參目標正常區間MAE;調參後模型正常區間全視野贏baseline |
| [ADR-113](ADR-113-即時預測服務架構.md) | 即時預測服務架構 | superseded（由 ADR-121） | prediction, data | 保留歷史，serving 特徵改成套凍結載入 |
| [ADR-118](ADR-118-駐點預備車與緊急救火警報.md) | 駐點預備車／緊急警報／即時天氣 | superseded（由 ADR-303） | dispatch, weather | 資源決策由 ADR-303 承接，修訂 TLS／快取及時間處理 |
| [ADR-201](ADR-201-React-Vite-Mock-first前端架構.md) | React／Vite Mock-first 前端＋Leaflet 歷史基線 | superseded（由 ADR-202） | frontend, dependencies, data-adapter | `98d3e8e` 已完成 Mock-only 三頁與 Leaflet 基線；保留歷史，不再作為現行地圖選型 |
| [ADR-202](ADR-202-MapLibre-DeckGL-OpenFreeMap地圖架構.md) | MapLibre／Deck.gl／OpenFreeMap 三頁地圖架構 | superseded（由 ADR-204） | frontend, map-architecture, outbound-security | 地圖遷移、OpenFreeMap 與 no-basemap 已於 `d1fdb16` 實作；底圖 style 來源條款由 ADR-204 取代，其餘決策由 ADR-204 承接 |
| [ADR-203](ADR-203-Past-Live-Predict時序契約.md) | Past／Live／Predict 前端呈現與 Mock-first | accepted | frontend, temporal-presentation, mock-data | 保留孿生 Mock 時序展示；實際站況／預測及派工 API 契約由 ADR-121／207／303 補齊 |
| [ADR-204](ADR-204-數位孿生戰情室設計語言與暗色底圖.md) | 數位孿生戰情室設計語言＋自帶暗色底圖 | superseded（由 ADR-205） | frontend, map-architecture, design-language, dependencies | 暗色主題與地圖視覺已實作；資訊架構（三頁）由 ADR-205 取代為四頁，設計語言/地圖決策由 ADR-205 承接 |
| [ADR-205](ADR-205-四頁角色導向資訊架構與無捲動版面.md) | 四頁角色導向資訊架構＋無捲動固定視窗版面 | superseded（由 ADR-208 承接） | frontend, information-architecture, ux | 調度/司機手機端/長官/戰情室；預設落地調度面板、炫技集中戰情室；2026-09-05 修訂：移除桌機司機頁（與調度面板重疊），司機僅手機端；調度面板資訊架構由 ADR-206 細化 |
| [ADR-206](ADR-206-調度面板決策流資訊架構.md) | 調度面板決策流資訊架構（三入口組單＋執行追蹤） | accepted | frontend, information-architecture, ux | 地圖舞台＋右欄狀態機（待命態/組單態）；對齊 ADR-119 三入口與預覽確認；缺口榜併入緊急站排行；執行追蹤含狀態生命週期；站數動態；owner 2026-09-11 核准，實作中 |
| [ADR-208](ADR-208-YouBike品牌識別與日夜主題.md) | YouBike 品牌識別＋日式柔和日夜主題 | accepted | frontend, design-language, map-presentation | owner 核准；承接 ADR-205 頁面架構，電輔車數未接入時不顯示站點閃電 |
| [ADR-209](ADR-209-服務水準看板盯盤.md) | `/overview` 改為服務水準看板 | accepted | frontend, information-architecture, ux | 名稱不用長官導覽；值班處長盯盤；只留頭條＋行政區壓力＋今日調度結果；不派工、不造 Before/After |
| [ADR-301](ADR-301-AI營運助理定位與LLM接入決策.md) | AI 營運助理定位與 LLM 接入決策（advisory-only） | proposed | platform, ai-advisory, security, api-contract | 助理僅輔助理解與建議、不自行決策（守 ADR-004）；長官頁是否接 LLM 仍待定。戰情室接法由 ADR-311 定案 |
| [ADR-311](ADR-311-戰情室Bedrock顧問代理.md) | 戰情室 Bedrock 顧問代理 | accepted | platform, ai-advisory, security, api-contract, frontend | owner 2026-09-12 核准；後端代理 Converse、失敗降級規則型、不派工；原編 ADR-307，2026-09-11 與競賽現場雲端部署撞號讓號至 311 |
| [ADR-302](ADR-302-派工確認與任務結案一致性.md) | 後端草稿、原子派工、授權回報與結案釋放 | accepted | api, security, database, dispatch | 第一批派工安全修正；沿用 SQLite／Demo 身分限制 |
| [ADR-121](ADR-121-模型與特徵成套載入.md) | 模型與特徵成套載入 | accepted | prediction, data | 第二批整合 |
| [ADR-207](ADR-207-前端實際派工服務整合.md) | 前端實際派工服務整合 | accepted | frontend, api | 第二批整合；原編 ADR-206，2026-08-19 與前端 ADR-206 撞號讓號至 207 |
| [ADR-303](ADR-303-觀測時間與資料可用性契約.md) | 觀測時間與資料可用性契約 | accepted | api, data, security, deployment | 第二批整合 |
| [ADR-122](ADR-122-時序評估協議與標籤完整性.md) | 時序評估協議與標籤完整性 | accepted | prediction, evaluation, data | 第三批A；supersedes ADR-106；逐fold擬合／依目標時間切分／補值與整段介入遮罩／輸出語意為淨變化非需求；不覆蓋現行上線模型 |
| [ADR-123](ADR-123-路線載量守恆與逐站到達可行性.md) | 路線載量守恆與逐站到達可行性 | accepted | dispatch, database, prediction | 第三批B；車輛初始載量可追溯（未知擋確認）／逐站載量守恆／各站對應預測視野／班別工時與任務重疊；預覽與確認共用驗證 |
| [ADR-304](ADR-304-派工可行性閘門與最適化套用一致性.md) | 派工可行性閘門與最適化套用一致性 | accepted | api, dispatch, optimization, database | 第三批B4+C；預覽回 blocking_reasons／optimizer 四種狀態語意／approve 綁 review_id 冪等且全成或全退／回滾驗證；係數仍不生效（ADR-120 做法Y） |
| [ADR-124](ADR-124-最適化調整係數的生效接線.md) | 最適化調整係數的生效接線 | accepted | dispatch, optimization, prediction | 第四批；係數乘在 ADR-115 動態目標水位的預期流量項；off/shadow/on 三態預設 off；累積絕對護欄 0.8~1.25；建議帶生效版本與係數 |
| [ADR-125](ADR-125-預測區間的conformal校準.md) | 預測區間的 conformal 校準 | superseded（由 ADR-127） | prediction, dispatch | 第四批；實測反證：偏移全為 0，原判斷「條件覆蓋率不足」係以標籤選子集造成；保留歷史，不得作為現行依據 |
| [ADR-126](ADR-126-未受供給限制的需求估計.md) | 未受供給限制的需求估計 | accepted | prediction, data | 第四批；站內自比（不跨站外推）；獨立欄位輸出、不進觸發與派工量；凍結統計進模型包；預設關 |
| [ADR-127](ADR-127-不採用conformal校準與覆蓋率判讀規則.md) | 不採用 conformal 校準，並訂定覆蓋率判讀規則 | accepted | prediction, evaluation | 第四批；supersedes ADR-125；430 萬列實測偏移全為 0、七種可觀測分組覆蓋率皆 79.5~83.0%；訂定「不得以標籤本身選出的子集判斷校準」；conformal.py 僅留為離線量測庫、無開關 |
| [ADR-305](ADR-305-開發模式資料源降級與逐筆新鮮度標記.md) | 開發模式資料源降級與逐筆新鮮度標記 | accepted | data, api, reliability | 正式模式維持 ADR-303（失敗→同源 stale→503，不碰 mock）；新增開發專用開關 dev_fallback_to_mock（預設 false，正式模式不生效）；降級 mock 標記 data_freshness=mock、dispatch_eligible=false，不進調度；逐筆新鮮度標記明文化 |
| [ADR-306](ADR-306-即時預測以同時段歷史代理lag特徵.md) | 即時預測以同時段歷史代理 lag 特徵 | accepted | prediction, data | 比賽階段只有 1–6 月歷史、即時是 9 月，lag 絕對往前推取不到值；改用同站同星期同時段歷史中位數代理，讓即時預測不再 degraded；lag_source=historical_proxy 前端誠實標示；只餵預測特徵不進派工；取得真序列後可切回 |
| [ADR-307](ADR-307-競賽現場雲端部署與S3遷移.md) | 競賽現場雲端部署與 S3 遷移 | accepted | platform, deployment, data, security | us-east-1 建專屬 bucket 遷歷史資料；後端 ECS Fargate（App Runner 被 SCP 擋）；金鑰環境變數注入雲端、讀 S3 走最小權限 task role；前端走 Vite proxy 免改 CORS；SageMaker 批次推論示範+未來每日重訓管線；public IP 臨時、賽後關閉 |
| [ADR-308](ADR-308-人力依歷史分派與雙人派工.md) | 人力依歷史分派與雙人派工（司機＋隨車） | proposed | dispatch, data, database, frontend | 離線分析 S3 1–6 月（周轉量主導+空/滿站絕對次數，最大餘數法）算各行政區人力配額，啟動時 seed 預設分派；派工單保留單一司機、新增可選隨車 assigned_escort（不動既有單人全鏈路）；待 owner 核准 |
| [ADR-309](ADR-309-緊急調度案件的升級追蹤與關案條件.md) | 緊急調度案件的升級追蹤與關案條件 | accepted | dispatch, database, api, frontend | 升級時鐘掛在案件不掛警示（警示會重建、按已讀會重算 triggered_at）；關案只認「未結案任務涵蓋該站」或「站況恢復」，已讀只靜音不關案、不重置；階段 30/45 分可設定；L1 常駐橫幅、L2 強制彈窗且三個出口皆留稽核；不接外部推播 |
| [ADR-313](ADR-313-需調度清單背景預算快取.md) | 需調度清單背景預算快取（顯示讀快取，派工維持即時） | accepted | dispatch, api, performance | 背景每60秒預算全量build_dispatch_list進TTL快取,recommendations/alerts/escalations讀快取(14-32s→1s),派工端口維持即時;config開關+僅真實源 |
| [ADR-312](ADR-312-班別人力配置與雲端固定位址.md) | 班別人力配置（三班×行政區）與雲端固定位址 | accepted | dispatch, data, database, deployment | 人力分早40/晚35/夜25三班,班內依行政區工作量配額;operators加shift欄;seed依行政區×班別分派;雲端 NLB+Elastic IP 固定位址(task重啟不變),workforce json 進 image 讓雲端分派生效 |
| [ADR-314](ADR-314-前端同源上雲.md) | 前端與後端同源上雲 | accepted | deployment, frontend, api, security | ECS 同一 image 出 SPA；`http://54.227.205.77:8000/` 畫面、`/api/v1` API；不另開公開 S3／CloudFront |
| [ADR-317](ADR-317-git-push自動部署ECS.md) | push main 自動部署同源前後端 | accepted | deployment, security | GitHub Actions 建同一 image → ECR → ECS；觸發僅 `main` 與手動按鈕；憑證走 GitHub Secrets |
| [ADR-318](ADR-318-空滿站緊急時計與今日排除時間.md) | 空滿站緊急時計與今日排除時間 | accepted | database, api, frontend | 空／滿一出現開時計；派工不關、恢復才算排除；看板第五張燈為各區平均排除時間 |
| [ADR-310](ADR-310-自動偵測調度完成.md) | 自動偵測調度完成（免人工回報，達標即結） | accepted | dispatch, data, backend | 背景輪詢即時站況，進行中任務待處理站達派工目標（補車升/取車降逼近 target+最小變化量濾波動）即自動標記完成、推進、結案，複用 report_station(auto=True)；不論車誰移動達目標即需求消化；config 開關+僅真實源啟用；待 owner 核准 |

## 新決策流程

1. 先查本索引，確認是否已有適用決策。
2. 複製 [ADR-template.md](ADR-template.md)，給下一個編號並設為 `proposed`。
3. 寫清楚選項、取捨、介面／資安影響、回復與驗證方式。
4. 更新本索引，等待 owner 明確核准；此時不需要虛構實作 commit。
5. 核准後記錄 `approval-evidence`、改為 `accepted`，再開始實作。
6. 實作 commit 產生後才更新 [commit-decision-map.md](commit-decision-map.md)。

## 歷史追溯

- [Commit → Decision 時序追溯](commit-decision-map.md)：涵蓋至 `98d3e8e` 的 18 筆 Git 歷史，逐筆分類並映射至 ADR。
- ADR-005～010 是依 commit、Spec 與現存程式補記的歷史決策，均標示 `retrospective: true`；沒有證據的當時動機不視為事實。

## 編號規則（分段編號制，見 ADR-000）

- 檔名：`ADR-NNN-簡短標題.md`
- **分段編號**（多分支協作防撞號）：
  - ADR-000 = 編號規則本身
  - ADR-001~010 = 已封存基礎決策，保留原號、不再新增
  - **ADR-1xx** = 模型／資料／預測（owner A、B）
  - **ADR-2xx** = 前端／視覺化／UX（owner C）
  - **ADR-3xx** = 平台／部署／資安／API 契約（owner A）
- **取號前先查 [ADR-000](ADR-000-ADR編號規則與號段配置.md) 的登記表**，取該號段最大號 +1，並在同一次變更登記。
- 各號段內只遞增、不重用；被取代或否決的 ADR 仍保留。
- 一份 ADR 只記一個核心決策；同一時期多個 commit 可以共同對應一份 ADR。
