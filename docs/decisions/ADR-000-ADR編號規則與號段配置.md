---
status: accepted
date: 2026-09-04
decision-makers:
  - project-owner
approval-evidence: "owner 於 2026-09-04 核准分段編號制(1xx模型資料預測/2xx前端視覺UX/3xx平台部署資安API;001-010封存;000為規則本身),並要求本分支重編 011-020→101-110,前端 201-204 保留給 C 自行落實"
scope:
  - governance
  - collaboration
related-commits: []
retrospective: false
supersedes:
superseded-by:
---

# ADR-000：ADR 編號規則與號段配置

> 本 ADR 為 meta 決策（規範 ADR 本身怎麼編號），不屬任何領域號段。

## 背景與問題

本 repo 有多條分支平行新增 ADR，且互不知情地從 ADR-010 之後接續流水號，造成**編號撞號**：

| 編號 | 本分支（general-purpose-model） | feat/front-end-ver1 分支 |
|------|-------------------------------|--------------------------|
| ADR-101 | 預測特徵因子模組化與資料源 | React-Vite-Mock-first 前端架構 |
| ADR-102 | 擴充特徵時間POI事件特殊天氣 | MapLibre-DeckGL-OpenFreeMap 地圖架構 |
| ADR-103 | 時序自身鄰近連動營運面因子 | Past-Live-Predict 時序契約 |
| ADR-104 | 站點行為指紋與需求密度分層 | 數位孿生戰情室設計語言與暗色底圖 |

檔名（標題）不同，故 `git merge` **不會報衝突**，會兩份都留下——合併後 `docs/decisions/` 會同時
出現兩個 ADR-101、兩個 ADR-102…。decision_governance.md 要求「找出並讀取與任務相關的 accepted ADR」，
編號一撞，引用「ADR-103」時無法判斷是哪一份，**治理即失效**。

不做決策的後果：兩分支一合併，ADR 索引與所有交叉引用全部語意不明，治理形同虛設。

## 決策（proposed，待 owner 核准）

改用**分段編號制**（依模組領域分號段，各領域在自己號段內遞增），取代全隊共用流水號。

### 號段配置

| 號段 | 領域 | owner |
|------|------|-------|
| ADR-000 | 編號規則本身（meta，不屬任何號段） | — |
| ADR-001~010 | 已封存的基礎決策，**保留原號，此號段不再新增** | （legacy） |
| ADR-1xx | 模型／資料／預測 | A、B |
| ADR-2xx | 前端／視覺化／UX | C |
| ADR-3xx | 平台／部署／資安／API 契約 | A |

各號段從 x01 開始遞增。

### 已配發登記表

**ADR-1xx（本分支 general-purpose-model，本次重編）**：

| 新號 | 舊號 | 標題 | 狀態 |
|------|------|------|------|
| ADR-101 | ADR-011 | 預測特徵因子模組化與資料源 | accepted |
| ADR-102 | ADR-012 | 擴充特徵時間POI事件特殊天氣 | accepted |
| ADR-103 | ADR-013 | 時序自身鄰近連動營運面因子 | accepted |
| ADR-104 | ADR-014 | 站點行為指紋與需求密度分層 | accepted |
| ADR-105 | ADR-015 | 目標變數定義與截斷樣本處理 | accepted |
| ADR-106 | ADR-016 | 調度標註離線與線上分離 | superseded by ADR-122 |
| ADR-107 | ADR-017 | 多視野預測與累積分位數 | accepted |
| ADR-108 | ADR-018 | 資料品質與站點主檔處理 | accepted |
| ADR-109 | ADR-019 | 流量加權訓練與決策層信心 | accepted |
| ADR-110 | ADR-020 | 超參數優化與時序交叉驗證 | accepted |
| ADR-111 | （新增） | 規則引擎吃截斷訊號與到達存量三層判斷 | accepted |
| ADR-112 | （新增） | 緊急度分數計算公式 | accepted |
| ADR-113 | （新增） | 即時預測服務架構(特徵三層/滑動預測/模型序列化/即時源) | superseded by ADR-121 |
| ADR-114 | （新增） | 調度資源清單(人員/車輛)與行政區任務指派 | accepted |
| ADR-115 | （新增） | 動態目標水位與補／抽車量計算 | accepted |
| ADR-116 | （新增） | 調度角色與班別模型(三角色/三班/大夜跨區/工時) | accepted |
| ADR-117 | （新增） | 班別排程策略(尖峰折返/離峰效率最大化/大夜跨區) | accepted |
| ADR-118 | （新增） | 駐點預備車/車隊保留率/緊急救火警報/即時天氣 | superseded by ADR-303 |
| ADR-119 | （新增） | 互動式派工單組建(三入口以車/以站/緊急+預覽確認) | accepted |
| ADR-120 | （新增） | 每日參數最適化optimizer(站點調整係數自適應+分情境歸因) | accepted |
| ADR-121 | （新增） | 模型與特徵成套載入 | accepted |
| ADR-122 | （新增） | 時序評估協議與標籤完整性(逐fold擬合/目標時間切分/補值與介入遮罩/輸出語意) | accepted |
| ADR-123 | （新增） | 路線載量守恆與逐站到達可行性(車輛初始載量/逐站視野/工時重疊) | accepted |
| ADR-124 | （新增） | 最適化調整係數的生效接線(off/shadow/on三態+絕對護欄) | accepted |
| ADR-125 | （新增） | 預測區間的conformal校準(CQR+分組條件覆蓋率) | superseded by ADR-127 |
| ADR-126 | （新增） | 未受供給限制的需求估計(站內自比,獨立輸出不進決策) | accepted |
| ADR-127 | （新增） | 不採用conformal校準與覆蓋率判讀規則(反證紀錄;禁以標籤選子集判校準) | accepted |

**ADR-2xx（保留給 C，前端分支自行落實，本次不建立檔案）**：

| 新號 | 原號 | 標題 |
|------|------|------|
| ADR-201 | ADR-101（前端） | React-Vite-Mock-first 前端架構 |
| ADR-202 | ADR-102（前端） | MapLibre-DeckGL-OpenFreeMap 地圖架構 |
| ADR-203 | ADR-103（前端） | Past-Live-Predict 時序契約 |
| ADR-204 | ADR-104（前端） | 數位孿生戰情室設計語言與暗色底圖 |
| ADR-205 | （新增） | 四頁角色導向資訊架構與無捲動版面 |
| ADR-206 | （新增） | 調度面板決策流資訊架構（三入口組單＋執行追蹤） |
| ADR-207 | （新增） | 前端實際派工服務整合（原編 ADR-206，2026-08-19 撞號讓號至 207） |
| ADR-208 | （新增） | YouBike 品牌識別與日夜主題 |

**ADR-3xx（平台／部署／資安／API 契約）**：

| 新號 | 標題 | 狀態 |
|------|------|------|
| ADR-301 | AI 營運助理定位與 LLM 接入決策（advisory-only） | proposed（LLM 接入待後端決定） |
| ADR-302 | 派工確認與任務結案一致性 | accepted |
| ADR-303 | 觀測時間與資料可用性契約 | accepted |
| ADR-304 | 派工可行性閘門與最適化套用一致性 | accepted |
| ADR-305 | 開發模式資料源降級與逐筆新鮮度標記（正式模式不變，僅開發情境可降 mock 且不可派工） | accepted |
| ADR-306 | 即時預測以同時段歷史代理 lag 特徵（比賽階段資料時間錯配的權宜；前端誠實標示代理） | accepted |
| ADR-307 | 競賽現場雲端部署與 S3 遷移（us-east-1 / ECS Fargate / 金鑰雲端化 / SageMaker 批次推論示範） | accepted |
| ADR-309 | 緊急調度案件的升級追蹤與關案條件（30/45 分升級；關案只認派工或站況恢復，已讀只靜音） | accepted |
| ADR-310 | 自動偵測調度完成（免人工回報，達目標水位即自動標記完成/結案；config 開關+僅真實源） | accepted |
| ADR-311 | 戰情室 Bedrock 顧問代理（advisory-only，後端代理；原 307 讓號） | accepted |
| ADR-312 | 班別人力配置（三班×行政區）與雲端固定位址（NLB+Elastic IP） | accepted |
| ADR-313 | 需調度清單背景預算快取（顯示端點讀快取秒回，派工端口維持即時） | accepted |
| ADR-314 | 前端與後端同源上雲（ECS 出 SPA，單一 NLB 網址） | accepted |
| ADR-317 | 出車載量自動預設（取消人工回報並重算；非總部車=0、總部車=補車需求量，僅未知時套用） | accepted |
| ADR-318 | 任務地圖真實道路路線（後端 /routing/road 代理 + 直線降級，前端沿道路畫） | accepted |
| ADR-319 | 系統為主的自動配單（依緊急度逐張配對鄰近人車，過濾已認領/手動草稿站，與自動偵測共用鎖） | accepted |
| ADR-311 | 戰情室 Bedrock 顧問代理（advisory-only，後端代理） | accepted |

### 取號流程（新增 ADR 前必做）

1. 判斷新 ADR 屬哪個領域號段（模型/資料/預測→1xx；前端/視覺→2xx；平台/部署/資安/API→3xx）。
2. 查本 ADR-000 的「已配發登記表」，取該號段目前最大號 +1。
3. **在同一次變更中**把新號登記進本表（避免同號段內部再撞號）。
4. 依 decision_governance 建立 proposed ADR，走核准流程。

## 理由與判準

- **正確性**：分段編號讓不同分支在不同號段取號，各自新增也不撞號；合併後索引語意明確。
- **可追溯**：ADR-001~010 保留原號不動，既有 commit message／文件引用不變成死連結。
- **可維護**：取號前查登記表，是最低成本的防撞機制，不需中央協調服務。
- **不改歷史**：重編只改本分支 011~020 的檔名與內文編號，不動 git 歷史（見回復方式）。

## 考慮過的替代方案

### 方案 A：續用全隊共用流水號
- 優點：最直覺。
- 缺點：多分支平行新增必然撞號（現況即是）。
- 未採用原因：正是本 ADR 要解的問題。

### 方案 B：合併後依先後順序補號
- 優點：合併前各自不用管。
- 缺點：補號的人必須讀懂別人 ADR 的決策語意才能正確排序，成本高且易錯；且合併前無法引用穩定編號。
- 未採用原因：治理要求「引用穩定可追溯」，事後補號破壞這點。

## 影響與後果

### 正面
- 兩分支合併後 ADR 不撞號、索引語意明確、交叉引用可信。
- 未來新增 ADR 有明確號段歸屬，多人協作不需即時溝通即可避撞。

### 負面與代價
- 本分支需一次性重編 011~020（10 個檔）+ 更新約 217 處交叉引用（36 個檔，見受影響清單）。
- 已推 commit message 內的舊編號無法改（不改 git 歷史），改以 commit-decision-map.md 補「舊號→新號」對照維持可追溯。

### 尚未解決
- 前端分支（ADR-201~204）由 C 自行重編，本次不處理，僅預留號段。
- ADR-000 進 main 後 C 需 merge 取得規則再對齊（屬 C 分支工作）。

## 介面與相容性

- 改 `docs/decisions/` 下 011~020 的檔名（`git mv` 保留歷史）與內文編號。
- 更新所有交叉引用（README、commit-decision-map、CHANGELOG、.kiro/specs、decision_governance、
  backend/**/*.py docstring、review_model_pretraining_v1.md）。
- **不改** ADR-001~010（封存區）、**不改** git 歷史、**不碰** feat/front-end-ver1 分支。

## 資安與隱私

- 無（純文件編號與交叉引用整理）。

## 回復或取代方式

- 若編號規則需調整，以新 meta ADR supersede 本 ADR，不改寫本檔歷史。
- 重編為檔案改名+內文編輯，可用 git 還原；不涉及 git 歷史改寫。

## 驗證方式

閘門 2 執行後必須實際跑過（不得只宣稱通過）：

```bash
# 應回傳空（commit-decision-map.md 故意保留舊號做對照，排除）
grep -rn "ADR-0\(1[1-9]\|20\)" \
  --include="*.md" --include="*.py" --include="*.js" \
  --include="*.jsx" --include="*.yaml" --include="*.yml" . \
  | grep -v "docs/decisions/commit-decision-map.md"

# 確認新檔名都在
ls docs/decisions/ADR-1*.md

# 確認 001~010 完全沒被動到
git diff --name-only | grep "ADR-0[01][0-9]" && echo "錯誤：動到封存區" || echo "OK"

git diff --check
```

## 追溯

- 相關 commit：（提案階段，尚無）
- 相關文件：prompt_ADR編號規則與重編.md（owner 指令）、decision_governance.md（治理規範）
- 相關 ADR：規範全體 ADR 編號；ADR-001~010 封存不動
