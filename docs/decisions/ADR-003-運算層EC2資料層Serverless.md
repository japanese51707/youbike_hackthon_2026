# ADR-003：運算層 EC2、資料層 Serverless

狀態：已定案（2026-08-31）

## 決策

- **資料層**：S3 + Glue + Athena（Serverless，無持續費用）
- **運算層**：EC2 Free Tier 跑後端 API + 模型推論（常駐服務）

## 脈絡

NFR-4 要求低成本。第一輪把整體講成「Serverless 無伺服器費用」，但後端 API + 模型推論需要**常駐服務**，不適合純 Serverless（Lambda 冷啟動、SSE 長連線不適合）。審查 v2 指出這是矛盾。

## 替代方案

- **全 Serverless（Lambda + API Gateway）** — 否決：SSE 即時警示、模型常駐推論不適合 Lambda。
- **全 EC2** — 資料也放 EC2？否決：資料量大，S3+Athena 更省更彈性。
- **混合（採用）** — 資料 Serverless、運算 EC2。

## 理由

- 資料層：S3 存放 + Athena 按查詢計費，幾乎免費，且資料源可抽換
- 運算層：EC2 t2/t3.micro Free Tier 12 個月免費，適合常駐 FastAPI + 本機模型推論
- 模型推論在 EC2 本機跑，零邊際成本（見 ADR-002）

## 影響

- 部署：Docker + docker-compose 跑在 EC2（主）+ 本機（備案）
- 費用：研發期 < NT$100/月
- NFR-4 措辭改為「資料層 Serverless、運算層 EC2」
