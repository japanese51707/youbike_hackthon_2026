---
status: accepted
date: 2026-09-12
decision-makers:
  - project-owner
approval-evidence: "2026-09-12 本對話：owner 要求時計上雲自動跑、與網站後端隔離、寫入雲端共用庫且網站讀同一份；並選定較單純的 EFS + SQLite，不上 RDS。"
scope:
  - deployment
  - database
  - backend
related-commits: []
retrospective: false
supersedes:
superseded-by:
---

# ADR-321：雲端空滿時計獨立收集與 EFS 共用庫

## 背景與問題

ADR-319／320 讓時計自己跑，但本機 sidecar 不會上雲。雲端只有一個 `youbike-backend` Fargate task，SQLite 在容器碟上，重新部署即丟。網站一滾，收集也停。

Owner 要求：雲端有一支跟網站分開的收集行程，自動寫進共用庫；網站只讀同一份。

不做決策的後果：看板排除時間在雲端仍跟網站生死綁在一起。

## 決策

1. **沿用 SQLite**，不上 RDS（守 ADR-009；owner 選較單純方案）。
2. **時計檔放 EFS**：`service_clock.db` 掛在 `/data/runtime/service_clock.db`。加密、VPC 內、非公開。
3. **獨立 ECS service** `youbike-clock-worker`：同一 image，指令 `python tools/service_clock_worker.py`，`desiredCount=1`，不掛 NLB、不開 8000。網站重部署不殺它。
4. **網站**設 `SERVICE_CLOCK_EXTERNAL=1`，只讀同一 EFS 檔，不再自己輪詢。
5. **最小規格**：worker 0.25 vCPU／512MB；EFS SG 只對 ECS task SG 開 NFS 2049。
6. **自動部署**（ADR-317）推完 image 後同時滾 `youbike-backend` 與 `youbike-clock-worker`。此點局部放開 ADR-317「不另開第二個服務」——僅限時計收集。
7. 本機仍可用 `youbike-clock-worker` 容器寫 `backend/data/service_clock.db`，與雲端無關。

## 理由與判準

- **正確性**：收集與網站隔離；時計活過網站滾動。
- **範圍**：不換資料庫引擎、不開公開資料庫。
- **成本**：多一個最小 Fargate + 少量 EFS，賽後可關。
- **規範**：us-east-1、SG 非全開、憑證不進版控。

## 考慮過的替代方案

### RDS PostgreSQL

- 優點：才是一般雲端資料庫。
- 缺點：改連線／SQL／密鑰，違反 ADR-009 的黑客松假設。
- 未採用原因：owner 選較單純方案。

### 同一 task sidecar

- 優點：不必第二個 service。
- 缺點：網站一滾，收集一起死。
- 未採用原因：owner 要與網站後端隔離。

### 時計只寫 S3

- 優點：已有 bucket。
- 缺點：進行中時計要常讀寫，S3 不當主庫。
- 未採用原因：延遲與一致性不適合時計。

## 影響與後果

### 正面

- 雲端看板的空滿時計跟收集行程走，不跟網站重載走。
- 重部署網站不會清掉進行中時計。

### 負面與代價

- 多一個常駐 task 與 EFS；SQLite 仍是單寫者（worker 寫、網站讀）。
- 第一次上線前的空／滿時長無法回補。
- 舊 image 沒有 worker 腳本時，新 service 會先起不來，要等含 ADR-320 程式的 image。

### 尚未解決

- EFS 跨 AZ：目前後端只在 `us-east-1b` 一條 subnet，mount target 同 AZ。
- 主庫 `youbike.db`（派工）仍在容器碟，本 ADR 只保時計。

## 介面與相容性

- 環境變數：`YOUBIKE_CLOCK_DB_PATH=/data/runtime/service_clock.db`、`SERVICE_CLOCK_EXTERNAL=1`（僅網站）。
- 新資源：EFS `youbike-clock`、access point、SG `youbike-efs-sg`、ECS service／task `youbike-clock-worker`、log group `/ecs/youbike-clock-worker`。
- API 契約不變。
- 佈建腳本：`tools/provision_clock_efs.py`（冪等）。

## 資安與隱私

- EFS 加密；mount target 只在 VPC。
- NFS 只接受 `youbike-backend-sg`。
- Task role 只加該檔案系統的 `ClientMount`／`ClientWrite`／`ClientRootAccess`。
- 不把金鑰寫進版控。

## 回復或取代方式

- `aws ecs update-service --service youbike-clock-worker --desired-count 0`；網站拿掉 `SERVICE_CLOCK_EXTERNAL` 即退回 in-app。
- 換 RDS 或他法以新 ADR supersede。

## 驗證方式

- Worker CloudWatch 出現啟動與寫入路徑。
- 滾 `youbike-backend` 後，進行中時計 `opened_at` 不變。
- `GET /api/v1/service-problems` 的 `open_count` 與 EFS 檔一致。

## 追溯

- 相關 ADR：ADR-009、ADR-307、ADR-317、ADR-318、ADR-319、ADR-320
- 相關文件：`docs/architecture-cloud.md`、`.github/workflows/deploy-ecs.yml`
