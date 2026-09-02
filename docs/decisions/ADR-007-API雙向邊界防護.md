---
status: accepted
date: 2026-09-02
recorded: 2026-09-02
decision-makers:
  - project-owner
approval-evidence: "2026-09-02 Kiro session：owner 明確要求建立必讀治理規則並直接補齊過去缺漏決策文件"
scope:
  - api
  - security
related-commits:
  - 83fd07c
  - ff5f478
  - 4b1cb6d
  - c02ed56
  - 7f596ca
retrospective: true
supersedes:
superseded-by:
---

# ADR-007：API 採雙向邊界防護

> 追溯說明：accepted 表示 owner 已核准本次補記的決策邊界；歷史事實以列出的 commit／Spec 為準。下列替代方案是依現況重建的取捨分析，不表示當時曾逐項留下討論紀錄。

## 背景與問題

前後端分離後，隱藏按鈕不能阻止使用者直接呼叫敏感 API；同時，系統主動呼叫 webhook 或第三方 API 時，也可能被惡意 URL、異常回應或超時拖垮。只做入向防護不足以保護完整資料流。

## 決策

### 入向

- 敏感操作由後端宣告式驗證角色，不能只靠前端控制。
- CORS 使用明確 origin、method、header 白名單，不使用萬用 `*`。
- API 層進行 Schema／輸入驗證與每 IP rate limit。
- 4xx、422、500 使用統一錯誤結構；500 不回傳堆疊、路徑或內部例外。
- 真實世界調度維持預覽、人工確認、執行、驗證閘門。

### 出向

- webhook callback 只允許安全 scheme，阻擋 localhost、link-local、metadata 與私有網段，降低 SSRF 風險。
- 第三方回應視為不可信輸入；憑證不進前端、不寫 log。
- 正式送出需設定 timeout、有限重試、簽章／token 與最小 payload。

## 理由與判準

- 權限必須在可信任的後端邊界執行。
- 對外通訊同時有「別人騙我」與「我被帶去危險位置／洩漏資料」兩種風險。
- 統一錯誤格式兼顧可觀測性與資訊最小揭露。
- 確定性、可測試的安全規則比散落在 route 內的手動檢查可靠。

## 考慮過的替代方案

### 只由前端隱藏敏感功能

未採用：HTTP API 可被直接呼叫，前端不是安全邊界。

### 開放 CORS 與任意 webhook URL

未採用：擴大跨站呼叫與 SSRF 攻擊面。

### 發生錯誤時回傳完整例外

未採用：便於開發但會洩漏內部資訊；詳細內容應留在受保護的伺服器 log。

## 影響與後果

### 正面

- 敏感操作不能繞過前端權限。
- 對內與對外邊界都有明確測試點。
- 錯誤不靜默，也不向客戶端暴露內部細節。

### 負面與代價

- 記憶體 rate limiter 只適合單程序／黑客松規模。
- URL 驗證與 DNS／redirect 防護需隨真正送出流程持續檢查，不能只驗證登記時字串。

### 尚未解決

- webhook 實際 HTTP 發送、簽章、重試與 SSE 長連線認證仍待正式整合。
- TLS／HTTPS 強制與分散式 rate limit 屬部署層工作。
- 完整 session／token 身分驗證另見 ADR-010 的限制。

## 介面與相容性

敏感 API 使用 `X-Operator-Id` 作為目前身分輸入，角色由後端查詢。錯誤回應維持 `{error, message, details?}` 類型。正式改用 token 時應以新 ADR 定義遷移，不可讓兩套權限來源無聲並存。

## 資安與隱私

本 ADR 本身即為安全邊界決策。所有新增進出系統的箭頭都必須分別檢查輸入欺騙、SSRF、憑證外洩、敏感資料外流、timeout 與重試上限。

## 回復或取代方式

安全控制不得直接移除；若改用 API Gateway、WAF、反向代理或集中式身分服務，建立 superseding ADR，說明哪些責任移到基礎設施、哪些仍由應用層保留。

## 驗證方式

- 無身分、角色不足、合法角色分別得到預期 401／403／成功。
- 超過限流門檻回 429；健康檢查依設定豁免。
- 非 HTTPS、localhost、私網與 metadata callback 被拒絕。
- 500 不含堆疊與內部路徑。

## 追溯

- `ff5f478`：警示、覆寫、稽核與 webhook SSRF 邊界。
- `4b1cb6d`：CORS、rate limit、統一錯誤格式。
- `c02ed56`：固定權限、規則與安全行為測試。
- `7f596ca`：同步安全設計與 review 修正。
