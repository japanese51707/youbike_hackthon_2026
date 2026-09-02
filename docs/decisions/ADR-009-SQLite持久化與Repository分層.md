---
status: accepted
date: 2026-09-02
recorded: 2026-09-02
decision-makers:
  - project-owner
approval-evidence: "2026-09-02 Kiro session：owner 明確要求建立必讀治理規則並直接補齊過去缺漏決策文件"
scope:
  - database
  - backend
related-commits:
  - 83fd07c
  - e1152ba
  - 25efc0d
  - 647f117
  - aafa5dc
retrospective: true
supersedes:
superseded-by:
---

# ADR-009：黑客松階段使用 SQLite 與 Repository 分層持久化

> 追溯說明：初始 design 已記錄 SQLite 方向，後續 commits 證明實作；accepted 表示 owner 已核准本次補記邊界。下列替代方案是依現況重建的取捨分析，不表示當時曾逐項留下討論紀錄。

## 背景與問題

A0～A4 的 alert、override、task、audit 等狀態主要在記憶體，服務重啟後會遺失，也無法提供可靠稽核與參數回溯。專案需要持久化，但黑客松規模與時程不足以合理化 PostgreSQL、Redis 與連線池的營運成本。

## 決策

- 黑客松與單實例 Demo 階段使用 SQLite 作為控制平面持久層。
- DB schema 集中於 `backend/db/schema.sql`，啟動時以 idempotent 方式初始化。
- 各領域透過獨立 Repository 存取資料；core service 不直接散寫 SQL。
- operators、tasks、alerts、overrides、audit、params 與版本資料都移出記憶體並持久化。
- DB 路徑外部化，預設為 `backend/data/youbike.db`；測試使用 `:memory:`。
- 檔案型 DB 是執行期產物，不進 Git。

## 理由與判準

- SQLite 無需額外服務，適合單機、低流量 Demo。
- 持久化能支援重啟復原、append-only 稽核、覆寫到期與參數版本回溯。
- Repository 將儲存細節隔離，未來換 DB 時控制平面介面不必整體重寫。
- 記憶體模式讓測試快速且互相隔離。

## 考慮過的替代方案

### 繼續使用記憶體狀態

- 優點：簡單、速度快。
- 缺點：重啟遺失、無可靠稽核與回溯。
- 未採用原因：不符合任務可續跑與可究責需求。

### PostgreSQL／RDS

- 優點：高併發、連線管理與正式營運能力較完整。
- 缺點：增加部署、憑證、成本與維運工作。
- 未採用原因：超過目前單實例黑客松需求。

### SQLite 但由 service 直接寫 SQL

未採用：儲存責任會散落核心邏輯，未來遷移困難。

## 影響與後果

### 正面

- 服務重啟後任務、警示、覆寫與稽核仍存在。
- 參數調整可以版本化與回溯。
- 不需額外資料庫服務。

### 負面與代價

- SQLite 寫入併發與多實例共享能力有限。
- 備份、migration 版本與損毀復原仍需正式化。
- Repository abstraction 降低但不消除未來 DB 遷移成本。

### 尚未解決

- 目前以 `schema.sql` 初始化，尚無正式 migration tool。
- 多 worker／多 container 部署前必須重新評估鎖、共享儲存與交易需求。
- 生產備份、加密與 retention 尚未完整定義。

## 介面與相容性

Core service 對 Repository 介面互動，API Schema 不因 SQLite 而綁定。DB schema 或資料語意的破壞性變更需提供 migration，不能只修改 `CREATE TABLE IF NOT EXISTS`。

## 資安與隱私

DB 檔不得進 Git；密碼只存雜湊。部署時需限制檔案權限與備份存取。稽核資料不可由一般前端任意修改。

## 回復或取代方式

可在測試切回 `:memory:`，但正式功能不得默默退回易失狀態。若流量或多實例需要 PostgreSQL，建立 superseding ADR，定義 migration、連線池、秘密管理、備份與回復計畫。

## 驗證方式

- 初始化可重複執行。
- 建立狀態後重新開啟連線仍可讀取。
- Repository 測試涵蓋 CRUD、狀態與版本回溯。
- DB 檔符合 `.gitignore`。

## 追溯

- `e1152ba`：建立 schema、connection、operators repository 與帳號持久化。
- `25efc0d`：同步 design／tasks 的資料欄位。
- `647f117`：alert、audit、override、task 全面改用 Repository。
- `aafa5dc`：參數與版本回溯持久化。
- 相關 ADR：ADR-001（三層參數）、ADR-003（單機運算層）。
