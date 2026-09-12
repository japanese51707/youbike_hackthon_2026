# AWS 黑客松競賽環境規範與資源（每次必讀）

本檔把主辦方「黑客松競賽環境規範與限制_20260722」與「Supported AWS Services List 20260722」的關鍵約束，
納入本專案的常駐規範。凡涉及 AWS 資源、部署、憑證、資料、模型訓練的任務，Agent 與團隊都必須遵守。
原始文件在 `比賽規範/`（PDF + xlsx），本檔為可執行摘要；有衝突以主辦方競賽期間公告為最終依據。

---

## 一、一般性使用規範（硬約束）

1. **區域**：以 **us-east-1** 與 **us-west-2** 為指定主要部署區域。新建資源一律放這兩區。
2. **S3 不可公開**：務必開啟 S3 Block Public Access 或用 Bucket Policy 限制；禁止建立公開對外 Bucket。
3. **網路不可對外全開**：禁止建立 Security Group 完全對外開放的 EC2；禁止啟用公開存取的 RDS / EMR。
4. **資源節制**：只啟動「必要工作所需」的執行個體數量，用完即關，避免浪費。
5. **憑證不進版控**：AWS Access Key、API Token、DB 密碼等一律用環境變數 / `.env`（已 gitignore）管理，
   絕不 commit。上傳 GitHub 前確認未含機密。
6. **禁止匯入受限資料**：不得在 AWS 帳戶使用/匯入個資、受管制資料、財務、種族/政治/宗教/工會/基因/
   生物識別/性向/健康/付款處理資料，或惡意程式碼。本專案用的是公開站點資料，維持此界線。
7. **`.kiro` 必須進版控**：上傳 GitHub 時專案根目錄必須包含 `/.kiro`（展示 specs/hooks/steering），
   **不可**把 `/.kiro` 或其子資料夾加入 `.gitignore`。

## 二、Amazon Bedrock

- 請求速率 **≤ 1 RPS/TPS**（每秒 1 個請求以下）。呼叫 Bedrock 要自行節流。
- 只申請「當前專案直接相關」的模型存取權，不要無目的啟用全部模型；不用的定期撤銷。

## 三、EC2 / SageMaker AI 執行個體限制

- **不建議大規模模型訓練**（競賽時間與計算資源有限）。本專案模型已離線訓練完成，
  競賽期間以「推論 / 服務」為主，不在雲上重訓大模型。
- **EC2 配額**（All regions）：標準 (A,C,D,H,I,M,R,T,Z) 256 vCPU；**GPU 類 G/P/X/High-Memory = 0 vCPU（不可用）**；
  Inf 8 vCPU、Trn 8 vCPU、DL 96 vCPU、F 64 vCPU、HPC 192 vCPU。→ 需要 GPU 的工作走 SageMaker，不要開 GPU EC2。
- **SageMaker AI 執行個體**：cluster/endpoint 各機型有數量上限（例：`ml.t3.medium` cluster 10、
  `ml.m5.xlarge` cluster 10、`ml.g5.*` spot 各 1）。endpoint 每 endpoint 最多 200 instance、
  每 endpoint 最多 100 inference component。詳細配額見 `比賽規範/Supported AWS Services List 20260722-2.xlsx`
  的 `SageMaker AI` 與 `EC2` 工作表。開資源前先查該表確認機型可用與上限。
- 支援的 AWS 服務與可用 IAM action 見同檔 `Services List` 工作表；用到不確定的服務先查表。

## 四、本專案的 AWS 資源使用現況

- **S3**：`youbike-hackathon-2026`（`youbike_data/year_month=YYYY-MM/data.parquet`，2026-01~06 官方歷史）。
  後端歷史資料源（`backend/core/data/historical.py`）與預測 lag 代理（ADR-306）讀取此 bucket。
- **憑證**：本機透過 `~/.aws/credentials` 的 default profile 提供（boto3 自動抓）；`.env` 的 AWS_* 可留空。
  正式/雲上部署改用 IAM Role，不寫死金鑰。
- **SageMaker（規劃中）**：如需雲端推論端點或批次推論，用 SageMaker（GPU EC2 不可用）；
  遵守機型配額、用完即刪端點、避免長時間閒置計費。

## 五、Agent 執行 AWS 相關任務前的檢查

1. 動到區域/資源前，確認落在 us-east-1 或 us-west-2。
2. 建 S3/EC2/RDS 前，確認未開公開存取 / 未對外全開。
3. 用到的 AWS 服務先對照 `Supported AWS Services List`，確認在支援清單內。
4. 任何金鑰/憑證只走環境變數，產出的檔案、log、commit 都不得含機密。
5. 需要 GPU → 走 SageMaker，不開 GPU EC2（配額為 0）。
