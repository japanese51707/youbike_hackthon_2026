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
| [ADR-001](ADR-001-單一模型分層參數.md) | 單一模型＋分層參數 | accepted | prediction, params | 三層參數已實作；真實模型尚未接入後端 |
| [ADR-002](ADR-002-LightGBM選型.md) | 預測模型採 LightGBM | accepted | prediction | 選型已定；backend 目前仍使用 MockPredictor |
| [ADR-003](ADR-003-運算層EC2資料層Serverless.md) | 運算層 EC2、資料層 Serverless | accepted | infra, data | S3／Athena 已規劃；Git 歷史尚無 EC2 部署證據 |
| [ADR-004](ADR-004-AI只估計規則引擎決策.md) | AI 只估計、規則引擎決策 | accepted | core, prediction | 規則與人工閘門為不可違反約束 |
| [ADR-005](ADR-005-契約先行與Mock並行開發.md) | 契約先行＋符合 Schema 的 Mock 解鎖並行 | accepted（追溯） | api, schemas, collaboration | 後端契約與 Mock 已建立；Mock-only 前端已完成，FastAPI 整合尚未完成 |
| [ADR-006](ADR-006-可抽換資料源與明確降級.md) | 可抽換資料源＋明確 freshness／降級 | accepted（追溯） | data, reliability | Mock／Historical 可用；即時 adapter 未實作，雙重失敗回空與 freshness 枚舉仍有缺口 |
| [ADR-007](ADR-007-API雙向邊界防護.md) | API 入向與出向都視為信任邊界 | accepted（追溯） | api, security | 應用層防護已建；正式 webhook／TLS 尚待部署 |
| [ADR-008](ADR-008-依賴釘選與關鍵行為測試.md) | 精確釘選依賴＋優先測決策關鍵行為 | accepted（追溯） | backend, testing, dependencies | Python 3.12 為容器基線；CI 尚未建立 |
| [ADR-009](ADR-009-SQLite持久化與Repository分層.md) | 黑客松階段使用 SQLite＋Repository | accepted（追溯） | database, backend | 單實例適用；多實例前需重評估 |
| [ADR-010](ADR-010-Demo帳號與後端角色驗證.md) | Demo 本地帳號＋後端角色驗證 | accepted（追溯） | authentication, authorization, security | 無 token/session，只限受控 Demo |
| [ADR-101](ADR-101-預測特徵因子模組化與資料源.md) | 預測特徵四因子模組化＋公開資料源 | accepted | prediction, features, data | 假日/天氣/地形/學生數各一模組；單因子先行，交叉影響待後續；天氣訓練用歷史、現況預測才接即時 |
| [ADR-102](ADR-102-擴充特徵時間POI事件特殊天氣.md) | 擴充特徵：時間衍生/POI距離/事件/特殊天氣 | accepted | prediction, features, data | 承接 ADR-101；POI 用 OSM、區域類型自動推導、事件介面先行、特殊天氣異常日標籤 |
| [ADR-103](ADR-103-時序自身鄰近連動營運面因子.md) | 站點時序自身/鄰近連動/營運面因子 | accepted | prediction, features, data | lag/歷史空滿頻率/波動度/鄰近連動(距離指數衰減)/日出日落/溫度倒U/故障缺口/level shift；含資料洩漏防範約束 |
| [ADR-104](ADR-104-站點行為指紋與需求密度分層.md) | 站點行為指紋/需求密度分層/外部因子降級 | accepted | prediction, features, data | 六個月行為指紋(日夜比/平假日比/峰型/需求密度)；需求密度分規劃層(柱位建議)與調度層(不進即時觸發)；站型分群行為vsPOI兩套對照；外部人口因子降為冷啟動fallback |
| [ADR-105](ADR-105-目標變數定義與截斷樣本處理.md) | 目標變數定義與截斷(censored)樣本處理 | accepted | prediction, features, data | 進訓練前審查F-03；截斷=「Δ=0 且同時空/滿站」才排除/降權(正常站Δ=0保留為真實訊號)+分區間評估；需求插補選配 |
| [ADR-106](ADR-106-調度標註離線與線上分離.md) | 調度介入辨識：離線清訓練資料/上線只事後標註 | accepted | prediction, features, data | 進訓練前審查§5-2；辨識調度僅為清訓練資料(離線用全期合法)；上線不做即時調度偵測,只做事後異常標註供回查 |
| [ADR-107](ADR-107-多視野預測與累積分位數.md) | 多視野預測(30/60/90/120分)+累積分位數 | accepted | prediction, api, core | 進訓練前審查F-04/F-05；直接多視野非遞迴、分位數對累積Δ訓練;horizon用分鐘定義(粒度落差解法);Prediction改horizons[]陣列(改api_contract,通知B/C) |
| [ADR-108](ADR-108-資料品質與站點主檔處理.md) | 資料品質與站點主檔處理 | accepted | data, features, prediction | 站數1521→1576(聯集1583);時間戳floor統一;經緯度為主鍵歸併亂碼站(1583→1579);新舊站分報 |
| [ADR-109](ADR-109-流量加權訓練與決策層信心.md) | 流量加權訓練與決策層信心 | accepted | prediction, features, rules | A樣本權重實測否決(LightGBM已內建);B周轉量保留;C決策層信心分級接dispatcher排序(守ADR-104不進觸發) |
| [ADR-110](ADR-110-超參數優化與時序交叉驗證.md) | 超參數優化與時序交叉驗證 | accepted | prediction | 時序CV選參(6月不參與防洩漏);選參目標正常區間MAE;調參後模型正常區間全視野贏baseline |
| [ADR-201](ADR-201-React-Vite-Mock-first前端架構.md) | React／Vite Mock-first 前端＋Leaflet 歷史基線 | superseded（由 ADR-202） | frontend, dependencies, data-adapter | `98d3e8e` 已完成 Mock-only 三頁與 Leaflet 基線；保留歷史，不再作為現行地圖選型 |
| [ADR-202](ADR-202-MapLibre-DeckGL-OpenFreeMap地圖架構.md) | MapLibre／Deck.gl／OpenFreeMap 三頁地圖架構 | superseded（由 ADR-204） | frontend, map-architecture, outbound-security | 地圖遷移、OpenFreeMap 與 no-basemap 已於 `d1fdb16` 實作；底圖 style 來源條款由 ADR-204 取代，其餘決策由 ADR-204 承接 |
| [ADR-203](ADR-203-Past-Live-Predict時序契約.md) | Past／Live／Predict 前端呈現與 Mock-first | accepted | frontend, temporal-presentation, mock-data | 前端 UI／Mock 決策已定；API／Schema／prediction／Alert／fallback／dispatch 契約仍待 owner／團隊決策，不可作為 A／B 實作依據 |
| [ADR-204](ADR-204-數位孿生戰情室設計語言與暗色底圖.md) | 數位孿生戰情室設計語言＋自帶暗色底圖 | superseded（由 ADR-205） | frontend, map-architecture, design-language, dependencies | 暗色主題與地圖視覺已實作；資訊架構（三頁）由 ADR-205 取代為四頁，設計語言/地圖決策由 ADR-205 承接 |
| [ADR-205](ADR-205-四頁角色導向資訊架構與無捲動版面.md) | 四頁角色導向資訊架構＋無捲動固定視窗版面 | accepted | frontend, information-architecture, ux | 調度/司機手機端/長官/戰情室；預設落地調度面板、炫技集中戰情室；2026-09-05 修訂：移除桌機司機頁（與調度面板重疊），司機僅手機端 |
| [ADR-301](ADR-301-AI營運助理定位與LLM接入決策.md) | AI 營運助理定位與 LLM 接入決策（advisory-only） | proposed | platform, ai-advisory, security, api-contract | 助理僅輔助理解與建議、不自行決策（守 ADR-004）；是否接 LLM 及接法留給後端/owner 決定，尚不可作為實作依據 |

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
