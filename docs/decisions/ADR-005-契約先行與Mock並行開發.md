---
status: accepted
date: 2026-08-31
recorded: 2026-09-02
decision-makers:
  - project-owner
approval-evidence: "2026-09-02 Kiro session：owner 明確要求建立必讀治理規則並直接補齊過去缺漏決策文件"
scope:
  - api
  - schemas
  - collaboration
related-commits:
  - 83fd07c
  - 57c9d4d
retrospective: true
supersedes:
superseded-by:
---

# ADR-005：契約先行與 Mock 並行開發

> 追溯說明：accepted 表示 owner 已核准本次補記的決策邊界；歷史事實以列出的 commit／Spec 為準。下列替代方案是依現況重建的取捨分析，不表示當時曾逐項留下討論紀錄。

## 背景與問題

專案由後端、預測模型與前端三條工作流並行開發。若先等待真實資料源、模型和完整後端完成，其他角色會被阻塞；若各自猜測 JSON 或函式格式，整合時又會產生大量破壞性修改。

歷史證據顯示，初始 Spec 已定義 API／Schema，A0 隨後建立 Pydantic models、薄 API 路由與共用 `mock_data.json`，讓不同角色可先依同一契約工作。

## 決策

- 跨模組與前後端協作採「介面契約先行」。
- HTTP 契約以 `api_contract.md` 與 Pydantic Schema 為準；預測邊界只暴露穩定的 `predict()`／`calc_urgency()` 介面。
- 真實依賴尚未完成時，以符合正式 Schema 的 Mock 實作解鎖並行開發。
- API 路由保持薄層，只做 HTTP／JSON 轉換與權限宣告，不承載核心業務邏輯。
- 內部實作可以替換，但不得靜默改變外部契約；破壞性契約變更必須重新評估 ADR 與遷移方案。

## 理由與判準

- 三個角色可以獨立開發與測試，不必互相等待。
- Schema 能把整合錯誤提早到開發期發現。
- Mock 和正式資料共用格式，切換來源時前端與控制平面不需重寫。
- 職責邊界清楚，降低單一大檔案與跨模組耦合。

## 考慮過的替代方案

### 依序完成資料、模型、後端，再開始前端

- 優點：短期不必維護 Mock。
- 缺點：工作流串行，任何上游延遲都會阻塞全隊。
- 未採用原因：不符合黑客松的並行交付需求。

### 各模組自行定義暫時格式

- 優點：個別開發者起步快。
- 缺點：欄位語意、型別與錯誤格式容易分歧。
- 未採用原因：把成本延後到整合階段，且容易破壞 API。

## 影響與後果

### 正面

- A、B、C 可依同一契約並行。
- 核心邏輯能用假資料獨立驗證。
- 資料源與模型完成後可在邊界內替換。

### 負面與代價

- Schema、API 文件與 Mock 必須同步維護。
- Mock 能證明契約可用，但不能證明真實資料品質或模型準確度。

### 尚未解決

- 截至相關歷史 commit，React 前端與真實 LightGBM Predictor 尚未整合。
- API 版本演進與破壞性遷移流程仍需在首次變更時定義。

## 介面與相容性

`backend/models_schema/` 是執行期格式驗證；`.kiro/specs/youbike-dispatch-system/api_contract.md` 是跨人契約；`frontend/src/mock/mock_data.json` 必須符合兩者。外部欄位異動需同步更新契約、Schema、Mock、測試與消費端。

## 資安與隱私

Mock 不得包含真實憑證、PII 或私人使用者資料。前端不能因使用 Mock 而假設正式 API 無需後端權限驗證。

## 回復或取代方式

若未來改用 code generation、OpenAPI-first 或其他契約來源，建立新 ADR 說明單一真相來源與遷移方式；不得讓多份契約無聲分叉。

## 驗證方式

- Pydantic Schema 可解析 Mock fixtures。
- API 回應符合契約。
- B／C 可在不依賴真實資料源的情況下呼叫邊界。

## 追溯

- `83fd07c`：建立 API contract、設計與介面先行原則。
- `57c9d4d`：建立後端 Schema、API 骨架與共用 Mock。
- 相關文件：`api_contract.md`、`design.md`、`development_principles.md`。
