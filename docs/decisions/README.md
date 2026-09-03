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
| [ADR-001](ADR-001-單一模型分層參數.md) | 單一模型＋分層參數 | accepted | prediction, params | 三層參數已實作；真實模型尚未接入後端 |
| [ADR-002](ADR-002-LightGBM選型.md) | 預測模型採 LightGBM | accepted | prediction | 選型已定；backend 目前仍使用 MockPredictor |
| [ADR-003](ADR-003-運算層EC2資料層Serverless.md) | 運算層 EC2、資料層 Serverless | accepted | infra, data | S3／Athena 已規劃；Git 歷史尚無 EC2 部署證據 |
| [ADR-004](ADR-004-AI只估計規則引擎決策.md) | AI 只估計、規則引擎決策 | accepted | core, prediction | 規則與人工閘門為不可違反約束 |
| [ADR-005](ADR-005-契約先行與Mock並行開發.md) | 契約先行＋符合 Schema 的 Mock 解鎖並行 | accepted（追溯） | api, schemas, collaboration | 後端契約與 Mock 已建立；前端尚未完成 |
| [ADR-006](ADR-006-可抽換資料源與明確降級.md) | 可抽換資料源＋明確 freshness／降級 | accepted（追溯） | data, reliability | Mock／Historical 可用；即時 adapter 未實作，雙重失敗回空與 freshness 枚舉仍有缺口 |
| [ADR-007](ADR-007-API雙向邊界防護.md) | API 入向與出向都視為信任邊界 | accepted（追溯） | api, security | 應用層防護已建；正式 webhook／TLS 尚待部署 |
| [ADR-008](ADR-008-依賴釘選與關鍵行為測試.md) | 精確釘選依賴＋優先測決策關鍵行為 | accepted（追溯） | backend, testing, dependencies | Python 3.12 為容器基線；CI 尚未建立 |
| [ADR-009](ADR-009-SQLite持久化與Repository分層.md) | 黑客松階段使用 SQLite＋Repository | accepted（追溯） | database, backend | 單實例適用；多實例前需重評估 |
| [ADR-010](ADR-010-Demo帳號與後端角色驗證.md) | Demo 本地帳號＋後端角色驗證 | accepted（追溯） | authentication, authorization, security | 無 token/session，只限受控 Demo |
| [ADR-011](ADR-011-預測特徵因子模組化與資料源.md) | 預測特徵四因子模組化＋公開資料源 | accepted | prediction, features, data | 假日/天氣/地形/學生數各一模組；單因子先行，交叉影響待後續；天氣訓練用歷史、現況預測才接即時 |
| [ADR-012](ADR-012-擴充特徵時間POI事件特殊天氣.md) | 擴充特徵：時間衍生/POI距離/事件/特殊天氣 | accepted | prediction, features, data | 承接 ADR-011；POI 用 OSM、區域類型自動推導、事件介面先行、特殊天氣異常日標籤 |
| [ADR-013](ADR-013-時序自身鄰近連動營運面因子.md) | 站點時序自身/鄰近連動/營運面因子 | accepted | prediction, features, data | lag/歷史空滿頻率/波動度/鄰近連動(距離指數衰減)/日出日落/溫度倒U/故障缺口/level shift；含資料洩漏防範約束 |

## 新決策流程

1. 先查本索引，確認是否已有適用決策。
2. 複製 [ADR-template.md](ADR-template.md)，給下一個編號並設為 `proposed`。
3. 寫清楚選項、取捨、介面／資安影響、回復與驗證方式。
4. 更新本索引，等待 owner 明確核准；此時不需要虛構實作 commit。
5. 核准後記錄 `approval-evidence`、改為 `accepted`，再開始實作。
6. 實作 commit 產生後才更新 [commit-decision-map.md](commit-decision-map.md)。

## 歷史追溯

- [Commit → Decision 時序追溯](commit-decision-map.md)：涵蓋目前完整 15 筆 Git 歷史，逐筆分類並映射至 ADR。
- ADR-005～010 是依 commit、Spec 與現存程式補記的歷史決策，均標示 `retrospective: true`；沒有證據的當時動機不視為事實。

## 編號規則

- 檔名：`ADR-NNN-簡短標題.md`
- 編號只遞增、不重用；被取代或否決的 ADR 仍保留。
- 一份 ADR 只記一個核心決策；同一時期多個 commit 可以共同對應一份 ADR。
