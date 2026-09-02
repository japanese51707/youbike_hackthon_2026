---
status: accepted
date: 2026-09-02
recorded: 2026-09-02
decision-makers:
  - project-owner
approval-evidence: "2026-09-02 Kiro session：owner 明確要求建立必讀治理規則並直接補齊過去缺漏決策文件"
scope:
  - authentication
  - authorization
  - security
related-commits:
  - 83fd07c
  - 57c9d4d
  - e1152ba
  - 25efc0d
retrospective: true
supersedes:
superseded-by:
---

# ADR-010：Demo 採本地帳號與後端角色驗證

> 追溯說明：初始 design 已記錄 `X-Operator-Id` 與後端角色驗證，後續 commits 證明本地帳號實作；accepted 表示 owner 已核准本次補記邊界。Cognito／OIDC 等內容是針對 production 缺口的未來評估，不表示當時已正式比較或否決。

## 背景與問題

系統有 operator、dispatcher、maintainer 三種角色，確認派發、緊急覆寫、參數審核與帳號管理不能只靠前端隱藏。A0 的固定身分對照足以測試介面，但不能管理密碼、停用帳號或保存稽核關聯。

## 決策

- 黑客松／Demo 階段以 SQLite `operators` 表管理本地帳號與角色。
- 密碼使用 bcrypt 雜湊，不保存或回傳原文；測試可透過環境變數降低 rounds，正式維持安全預設。
- 不開放自助註冊；只有 maintainer 能建立、列出或停用帳號。
- 停用取代刪除，以保留任務與稽核關聯。
- 敏感端點以 FastAPI dependency 在後端驗證角色。
- 目前 API 身分傳遞仍使用 `X-Operator-Id`；登入端點只驗證帳密並回帳號資料，**沒有簽發 session 或 token**。
- 因此本決策只接受為受控 Demo 的身分方案，不宣稱符合公開網路的生產認證要求。

## 理由與判準

- 在不引入外部 IdP 的情況下，提供可測試的帳號、角色與停用流程。
- bcrypt 避免資料庫直接暴露原始密碼。
- 後端角色檢查不能被前端繞過。
- 保留帳號紀錄能維持稽核可追溯性。

## 考慮過的替代方案

### 固定記憶體角色 dict

未採用為最終 Demo 方案：無密碼、無停用、重啟與管理能力有限。

### 前端自行判斷角色

未採用：任何人都能直接呼叫 API。

### Cognito／OIDC／簽章 token

- 優點：可提供正式 session、token 驗證與集中式生命週期。
- 缺點：增加整合與部署範圍。
- 目前未採用原因：相關 commit 只證明本地 Demo 帳號需求；正式上線前仍應採此類方案並建立新 ADR。

## 影響與後果

### 正面

- Demo 可登入、建帳號、停用並測試角色權限。
- 密碼不以原文保存。
- 權限規則集中於後端 dependency。

### 負面與代價

- `X-Operator-Id` 可由客戶端自行填寫；沒有 token 綁定，不能當作公開網路的強認證。
- 預設 Demo 帳密存在 repo 程式中，部署前必須移除或強制更換。
- bcrypt 計算成本需要平衡安全與資源。

### 尚未解決

- Session／JWT／OIDC、登出、token 到期、密碼重設、MFA 與登入 rate limit。
- TLS、秘密管理與正式帳號 bootstrap 流程。
- SSE 與 webhook 訂閱者的完整身分驗證。

## 介面與相容性

目前敏感 API 接受 `X-Operator-Id`。未來改用 Cognito／OIDC 時，應建立 superseding ADR，定義 Authorization header、token claims 到角色的對映、舊 header 淘汰與前端遷移。

## 資安與隱私

- 不記錄密碼或 password hash 到 log／API。
- 登入失敗訊息不區分帳號不存在或密碼錯誤，降低枚舉。
- 預設帳號僅限本機／Demo，不能直接用於公開部署。
- 帳號管理與敏感動作必須寫稽核。

## 回復或取代方式

不應退回前端權限或硬編碼角色。正式部署前以新 ADR 取代本方案，導入可信任 IdP／token；SQLite 帳號可停用並保留歷史稽核對照。

## 驗證方式

- 正確／錯誤密碼與停用帳號得到預期結果。
- API 回應不含 `password_hash`。
- operator、dispatcher、maintainer 的 401／403／成功矩陣符合契約。
- 建立與停用帳號留下稽核紀錄。

## 追溯

- `57c9d4d`：建立 `X-Operator-Id` 與角色骨架。
- `e1152ba`：SQLite 帳號、bcrypt、登入與帳號管理。
- `25efc0d`：同步 operators schema 與 A5 文件。
- 相關 ADR：ADR-007（API 邊界）、ADR-009（SQLite）。
