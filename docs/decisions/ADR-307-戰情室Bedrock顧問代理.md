---
status: accepted
date: 2026-09-12
decision-makers:
  - project-owner
approval-evidence: "2026-09-12 Cursor session：owner 明確回覆「核准」，於數位孿生戰情室／twin 頁接入 AWS Bedrock LLM 顧問"
scope:
  - platform
  - ai-advisory
  - security
  - api-contract
  - frontend
related-commits: []
retrospective: false
supersedes:
superseded-by:
---

# ADR-307：戰情室 Bedrock 顧問代理

## 背景與問題

戰情室 `/twin` 已有確定性洞察（指標、結論、覆蓋閘門），但評審與規劃者仍需要用自然語言快速總結現況、追問分析方法與研究當前圖層。ADR-301 已把助理定位成 advisory-only，並建議若接 LLM 必須走後端代理；供應商與端點當時未定。前端直連付費 API 會把金鑰放到瀏覽器，也違反 ADR-202／208 的無金鑰地圖原則。

## 決策

- 戰情室新增 **AI 總結詢問助手**：只做摘要、解釋、追問與研究方法說明，**不派工、不寫入 dispatch payload、不改系統狀態**（承接 ADR-004、ADR-301 定位）。
- LLM 供應商採 **AWS Bedrock**，只由後端呼叫（Converse API）。前端不持金鑰、不直連 Bedrock。
- 新增契約端點 `POST /api/v1/assistant/twin`。請求只帶精簡 grounded context（洞察指標、圖層結論、前幾名空／滿站與行政區），不送全市站點原文。
- 模型與區域用環境變數／設定覆寫，不把特定 model ID 寫死成不可改的架構。預設建議 `ap-northeast-1` 的 Amazon Nova Lite；帳號若無該模型再改 `BEDROCK_MODEL_ID`。
- Bedrock 未設定、無權限或逾時時，**降級成規則型摘要**，頁面不可空白。
- 第一版「研究」範圍是這頁已有的戰情資料與分析方法，不上網搜尋，不假造真實 OD／人口／路網。
- 長官頁 `/overview` 規則型助理維持現況，不在本 ADR 範圍。

## 理由與判準

- 正確性：數字以系統算出的 `twinInsights` 為準，LLM 不得虛構。
- 資安：金鑰只在後端，使用者問題當不可信輸入。
- 成本：不送 1600 站原文；此端點另有用量上限。
- 可逆：關掉 Bedrock 或停用端點即可退回規則型。
- 交付：黑客松現場可用既有 AWS 憑證，不必另接第三方 LLM 帳號。

## 考慮過的替代方案

### 方案 A：維持規則型、不接 LLM

- 優點：零成本、無幻覺。
- 缺點：無法自由追問與解釋分析方法。
- 未採用原因：owner 明確要求戰情室接真實 LLM。

### 方案 B：後端代理 Bedrock（採用）

- 優點：符合 ADR-301 選項 B 與無金鑰原則。
- 缺點：需 AWS 模型權限與費用控管。
- 採用原因：與現有 S3／IAM 同一信任邊界。

### 方案 C：前端直連 Bedrock 或第三方 LLM

- 優點：實作最短。
- 缺點：金鑰外洩、出向難審、違反 ADR-301 選項 C。
- 未採用原因：資安不可接受。

## 影響與後果

### 正面

- 戰情室可用自然語言理解當前地圖與洞察，而不把決策交給 LLM。

### 負面與代價

- 需要 Bedrock 模型存取與額外延遲／費用。
- LLM 仍可能講超過 context 的話，必須靠 prompt 護欄與降級。

### 尚未解決

- 正式環境的成本上限、用量審計儲存、串流回應。
- 東京區實際可用模型以現場帳號為準。
- 長官頁是否沿用同一代理。

## 介面與相容性

- 新增 API 3.21：`POST /api/v1/assistant/twin`。
- 回應含 `source=bedrock|fallback`、`advisory=true`。
- 不改派工、預測、資料源契約。

## 資安與隱私

- 金鑰只在後端環境變數；不進前端、版控或 log。
- 入向：需有效 `X-Operator-Id`；問題與歷史長度設上限；prompt injection 以分隔符隔離。
- 出向：Bedrock 回應當不可信；timeout、有限重試、失敗降級。
- 不外送 PII；站名僅限 context 內前幾筆。

## 回復或取代方式

- 設 `BEDROCK_ENABLED=false` 或停用端點即退回規則型。
- 換供應商或把 LLM 用於決策時，以新 ADR supersede，不改寫本檔。

## 驗證方式

- 後端以 mock Converse 測摘要、問答、失敗降級、未登入 401。
- 前端無憑證或 Mock 模式仍能開助手並看到規則型總結。
- 回覆不得進入 dispatch payload。

## 追溯

- 相關 commit：實作後補。
- 相關 Spec／文件：api_contract.md 3.21。
- 相關 ADR：ADR-004、ADR-007、ADR-301、ADR-205／208。
