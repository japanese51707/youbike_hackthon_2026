---
status: accepted
date: 2026-09-12
decision-makers:
  - project-owner
approval-evidence: "2026-09-12 本對話：owner 選定 push main 觸發、憑證怎麼快怎麼來（GitHub Secrets，不走 OIDC）；並要求完成自動部署。"
scope:
  - deployment
  - security
related-commits: []
retrospective: false
supersedes:
superseded-by:
---

# ADR-317：push `main` 自動部署同源前後端（GitHub Actions → ECR → ECS）

## 背景與問題

ADR-314 已把前端打進同一支 ECS image，評審網址為 `http://54.227.205.77:8000/`。
部署仍是本機 `docker build` → ECR push → `ecs update-service`。隊友若用舊 Dockerfile
覆寫 `:latest`，首頁會變 FastAPI 404（`request_error` / Not Found）。

ADR-314 明確把「git push 自動部署」留待獨立決策。號段上 ADR-315／316 已被
`origin/main` 的派工 commit 使用，本決策取 **ADR-317**。

## 決策

1. **GitHub Actions** 在 push `main` 或手動 `workflow_dispatch` 時建置
   `backend/Dockerfile`（含 SPA），推 ECR，並滾動 ECS `youbike` / `youbike-backend`。
2. **區域固定 `us-east-1`**（不讀本機憑證檔預設的 us-west-2）。
3. **認證用 GitHub Secrets**（最快）：`AWS_ACCESS_KEY_ID`、`AWS_SECRET_ACCESS_KEY`、
   可選 `AWS_SESSION_TOKEN`。本 ADR **不**採用 OIDC。
4. Image 標 `latest`（既有 task def 使用）與 `git sha`（可回上一版）。
5. **不**對 feature branch 自動部署；**不**另開 CodePipeline／第二個服務。
6. CWA 等執行期金鑰仍只在 ECS task，不進 Actions。

## 理由與判準

- **交付速度**：沿用既有 ECR／ECS／NLB，不新增 AWS 服務。
- **與 ADR-314 一致**：前後端同一 image，一次滾動兩邊都更新。
- **可逆**：Secrets 刪掉即停自動部署；ECS 可改回舊 sha。

## 考慮過的替代方案

### GitHub OIDC → IAM Role

- 優點：沒有長期金鑰。
- 未採用原因：owner 要求怎麼快怎麼來；現場 SCP 曾擋 App Runner，OIDC provider 也可能被擋。

### AWS CodePipeline／CodeBuild

- 優點：AWS 原生。
- 未採用原因：多兩個服務、接 GitHub 連線較慢。

### 每條 feature branch 都部署

- 未採用原因：會把評審網址洗成半成品。

## 影響與後果

### 正面

- `main` 合併後雲端前後端一起更新，不必本機裝 Docker。
- 可手動重跑同一 workflow。

### 負面與代價

- 現場憑證是臨時 assumed-role，過期後 workflow 失敗，要重貼 Secrets。
- 建置約 8–12 分鐘；ECS 再滾 2–3 分鐘。
- 只推 `mapbroken` 等分支**不會**更新雲端。
- `:latest` 仍可能被本機手動 push 覆蓋；自動部署之後以 Actions 的 `latest` 為準。

### 尚未解決

- HTTPS／自訂網域。
- 憑證過期自動換發。
- OIDC（若之後 SCP 允許，以新 ADR supersede）。

## 介面與相容性

- 新增 `.github/workflows/deploy-ecs.yml`。
- 必要 Secrets：`AWS_ACCESS_KEY_ID`、`AWS_SECRET_ACCESS_KEY`；臨時憑證再加 `AWS_SESSION_TOKEN`。
- 既有 task definition、NLB、EIP 不變。

## 資安與隱私

- 金鑰只在 GitHub Secrets 與 ECS task，不進版控。
- workflow 權限僅 `contents: read`。
- 不把 `secrets/aws-credentials` 或 CWA key 寫進 YAML。

## 回復或取代方式

- 停用：刪 Secrets 或 disable workflow。
- 回上一版：`aws ecs update-service` 指向舊 sha，或以新 ADR 改觸發／認證方式。

## 驗證方式

- workflow 綠燈；`GET /` 為 SPA HTML；`/health` 與 `/api/v1/kpi` 為 JSON 200。

## 追溯

- 相關 ADR：ADR-307、ADR-312、ADR-314
- 相關文件：`docs/architecture-cloud.md`、`.github/workflows/deploy-ecs.yml`
