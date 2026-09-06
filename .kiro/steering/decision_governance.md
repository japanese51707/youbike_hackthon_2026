# 架構決策治理（每次必讀）

本檔沒有條件式 inclusion，Kiro 在此 workspace 的每次互動都必須套用。它定義「何時需要 ADR、誰能定案、如何追溯」，完整決策存放於 `docs/decisions/`。

## 一、開始任何任務前的強制流程

凡可能修改程式、設定、架構、API、Schema、資料、模型、資安或部署的任務，Agent 必須依序：

1. 執行 `git status`，保留使用者與其他人的既有變更。
2. 讀取 `docs/decisions/README.md`。
3. 找出並讀取與任務相關、狀態為 `accepted` 的 ADR。
4. 在實作計畫中明確寫出以下其中一種判斷：
   - `ADR：沿用 ADR-XXX，不需新增。`
   - `ADR：不需要；原因是……`
   - `ADR：需要新增／取代，先提出 proposed ADR，尚不實作。`
5. 若需求與 accepted ADR 衝突、文件仍標示「待決策」，或缺少 owner 決定，停止鎖定方案並向使用者說明選項與影響。
6. 遵守核准閘門；未經明確要求，不 stage、commit 或 push。

純資訊查詢可以不逐份讀 ADR；但只要準備提出會影響專案的方案，就必須先查索引。

## 二、必須建立或更新 ADR 的情況

以下任一變更成立時，必須建立 ADR：

- 系統架構、模組邊界、控制平面／執行平面的責任分配
- API、Schema、事件格式、模組介面等跨人契約
- 資料庫、持久化方式、資料生命週期或資料源選擇
- ML 模型、特徵責任、訓練平台、模型部署或推論方式
- AWS 服務、部署平台、網路拓撲或重大成本模型
- 認證、授權、金鑰、信任邊界或資安策略
- 重要第三方依賴、框架或會限制後續選項的工具
- 跨模組共用慣例、不可逆或高成本回復的決策
- Spec／設計文件中標示「待決策／待團隊定義」的選項
- 新實作與既有 accepted ADR 不相容

## 三、不需要 ADR 的情況

以下通常不另立 ADR，但仍須在計畫中說明理由：

- 完全依 accepted ADR 實作，沒有新增限制或改變介面
- 不改外部行為的局部 bug fix 或重構
- 格式化、拼字、連結與純文件同步
- 已由設定契約允許的參數調整
- 測試、範例、預覽工具或可立即回復的局部修改

若不確定，先視為需要討論，不得以「趕時間」為由靜默決定。

## 四、ADR 狀態與核准權

允許的狀態：

- `proposed`：候選決策，尚不可視為實作依據
- `accepted`：owner／團隊已明確核准，Agent 必須遵守
- `rejected`：已否決，保留原因避免重複討論
- `superseded`：被新 ADR 取代；新舊文件必須互相連結
- `deprecated`：不再建議，但尚未有單一取代決策

只有專案 owner 或被授權的決策者能把 `proposed` 改成 `accepted`。Agent 可以起草、分析與補證據，不得自行假定沉默等於核准。每份 `accepted` ADR 必須在 `approval-evidence` 記錄可追溯的核准依據（例如 PR、會議紀錄或 owner 明確要求的日期與管道）。

## 五、決策的記錄順序

### 新決策

0. **取號前先查 ADR-000（分段編號制）**：依領域選號段（模型/資料/預測→1xx；前端/視覺→2xx；平台/部署/資安/API→3xx），取該號段登記表最大號 +1，並在同一次變更登記進 ADR-000。ADR-001~010 為封存區不再新增。此制用於多分支協作避免撞號。
1. 先用 `docs/decisions/ADR-template.md` 建立 `proposed` ADR。
2. 列出背景、選項、取捨、影響、風險、回復方式與驗證方式。
3. 更新 `docs/decisions/README.md` 索引；提案階段不需建立尚不存在的實作 commit 對應。
4. 等 owner 明確核准，並記錄 `approval-evidence`。
5. 將狀態改為 `accepted` 後再實作。
6. 實作 commit 產生後，才更新 `docs/decisions/commit-decision-map.md`；純 ADR 文件 commit 可不視為實作證據。

### 歷史補記

若實作已存在但 ADR 缺漏，可以建立 `retrospective: true` 的追溯 ADR，但必須：

- 以 commit、Spec、程式與測試作證據，區分事實與推論
- 不捏造當時沒有留下的理由；替代方案若為事後分析，明確標示
- 寫明目前限制、尚未完成項目與生產環境缺口
- 由 owner 明確核准追溯邊界，並記錄 `approval-evidence`
- 在 `docs/decisions/commit-decision-map.md` 建立既有 commit 對應

## 六、變更與取代規則

- 不得直接改寫 accepted ADR 的核心決策，讓歷史看似從未改變。
- 要改方向時建立新 ADR，設定 `supersedes`；舊 ADR 改為 `superseded` 並填入 `superseded-by`。
- 實作、Spec、README 與設定若和 ADR 不一致，Agent 必須指出，不可自行選一份當真相。
- ADR 只記通用決策；逐次工作紀錄與驗證結果放 PR、CHANGELOG 或任務文件。

## 七、每份 ADR 的最低內容

本規則生效後新增或追溯補記的 ADR，至少包含：狀態、日期、決策者、`approval-evidence`、範圍、背景、決策、理由、替代方案、正負後果、介面／相容性影響、資安／隱私影響、回復方式、驗證方式與相關 commit。

### Legacy ADR 過渡

ADR-001～004 建立於本治理規則之前，沿用原本「已定案」狀態，視為 legacy `accepted`，不因缺少新 frontmatter 而失效。Agent 必須遵守以下限制：

- 不得自行補猜當時的 decision-maker、核准紀錄或未記載的替代方案。
- `docs/decisions/README.md` 與 `commit-decision-map.md` 只補現況與 Git 證據，不改寫原決策。
- 若核心決策改變，必須建立符合新模板的 superseding ADR，不直接重寫 legacy 歷史。
- 若未來只做格式正規化，需由 owner 核准，且不得趁機改變決策內容。

## 八、目前有效決策索引

以下索引是本規則的一部分；每次新增、接受或取代 ADR 都要同步更新：

#[[file:../../docs/decisions/README.md]]
