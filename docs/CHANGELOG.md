# 版本進度記錄（CHANGELOG）

本檔記錄各階段里程碑與主要更新，讓團隊與未來的自己快速掌握「這版做了什麼、目前到哪」。

---

## 目前階段：✅ 完成 A5，尚未進入 A6

後端 A0~A5 已完成並通過測試（43 測試全綠），程式碼已進版控。
下一步為 A6（整合 + 模擬重放），需 B 的模型與 C 的前端就緒才能全面串接。

---

## [A5 完成] — 2026-09-02

### 相較 A4 版的主要更新

A4 版狀態：後端 A0~A4，狀態全在記憶體、無資料庫、帳號寫死 3 個。

本版新增（A5 = SQLite 持久層 + 帳號系統 + 三層參數）：

**SQLite 持久層**
- `db/`：七張表（operators/tasks/audit_logs/station_params/alerts/alert_subscriptions/events）+ overrides 輔助表
- 連線層支援 `:memory:`（測試用）；config 加 `database.path`

**帳號系統（資安強化）**
- 密碼 bcrypt 雜湊，DB 只存亂碼，絕不存原文（直接用 bcrypt，passlib 已過時）
- `auth.py` 從寫死 3 帳號改成查 SQLite；停用帳號自動失效
- 帳號管理端點：登入、建帳號（需 maintainer，不開放自助註冊）、停用
- 登入失敗統一訊息防帳號枚舉；停用取代刪除保留稽核關聯

**記憶體狀態全搬 SQLite（一次搬乾淨）**
- audit/override/task/alert 四個 service 改 DB backend
- 驗證：重啟後端後覆寫/稽核/參數版本都還在（解決 A4 版重啟即消失的問題）

**三層參數 + 版本管理**
- `params/`：①基礎 ②AI最適化 ③覆寫狀態 的疊加；③不寫參數只給 override_active 旗標
- 版本控制：②approve 才存版本、reason 必填、可一鍵回溯
- I-10 兩端點：`GET /params/history`、`POST /params/rollback`（需 maintainer）
- param_source 只有 base/ai_optimized（覆寫時仍為 base，非 emergency_override）

**測試**：43 個全綠（新增帳號 4 + 參數 8）

### 尚未處理（留待 A6 或現場）
- A6：整合 B 模型 + C 前端 + 模擬重放
- I-7：根目錄 PoC 腳本歸檔
- I-9：webhook 實際送出、SSE 改真正 EventSource

---

## [A0~A4 完成] — 2026-09-02

### 相較上一版（僅有 Task 階段文件）的主要更新

上一版狀態：只有 spec/design/config/steering + Task 階段文件（tasks.md、README、CONTRIBUTING、ADR），**後端程式碼尚未進版控**。

本版新增（後端 A0~A4 全部落地 + Claude review 必修項修正）：

**A0 — 後端骨架**
- FastAPI 骨架：`config_loader`、`mock_store`、`auth`（3 測試帳號角色驗證）
- `api/` 10 個端點檔（薄層轉發，回 mock）約 31 端點
- `models_schema/` 15 個 Pydantic Schema class（對齊 api_contract §2）
- `frontend/src/mock/mock_data.json`（10 站真實座標假成品資料，給 C）
- Dockerfile + docker-compose.yml

**A1 — 資料源層（可抽換）**
- 抽象介面 + 工廠：換源只改 config 一行（mock / historical / tdx / youbike_official）
- `historical.py` 讀 S3 Parquet（實測 224 萬列），中文欄位對映標準英文欄位
- `station_id_lookup.json`：用新北官方 API 建站名→sno 對照（1600 站，命中率 99.9%）
- `degradation.py`：NFR-10 降級（即時源掛掉退回歷史，標 data_freshness）

**A2 — 規則引擎 + 調度**
- `rule_engine`：**雙向觸發**（下界防空站 / 上界防滿站），吃預測區間不吃點估計
- `dispatcher`：排序 + 緊急度分級 + ③覆寫「最前綴」（不改分數）
- `task_manager`：狀態機（含 assigned / cancelled）+ 動態轉派 + 可續跑
- `interfaces`：B 的 predict/calc_urgency 介面契約 + mock（讓 A 獨立開發）

**A3 — 警示 + 覆寫 + 稽核**
- `alert_service`：警示產生/分級/去重 + SSE 佇列 + webhook 出向 SSRF 防護
- `override_service`：③即時覆寫 + 時效自動恢復
- `audit`：稽核留痕（append-only）
- **覆寫到期任務取消規則定案**：覆寫到期/取消時，由它產生且仍在 assigned 的任務一併取消，in_progress 不受影響，全程留稽核

**A4 — 資安加固**
- rate limit（每 IP 每分鐘上限，超過 429，/health 豁免）
- CORS 收斂（方法/標頭白名單，不用 *）
- `require_role` 改宣告式 Depends（權限檢查無法被遺漏）
- 統一錯誤格式（4xx/422/500 不外洩內部細節）
- 輸入驗證（覆寫端點改 Pydantic schema）

**工程紀律（依 Claude review 必修項）**
- 建 `backend/tests/`：31 個測試全綠，固定 A0~A4 已驗證行為
- requirements 補齊依賴（boto3/pyarrow/pandas/httpx）並釘版本
- `target_usage_rate` 換算欄位（解決 target_level 0~1 與 usage_rate 0~100 的比較陷阱）
- spec/config/design 同步實作

### 尚未處理（留待 A5 或現場）
- A5：SQLite 七張表、三層參數 + 版本、帳號系統（密碼雜湊）
- I-7：根目錄 PoC 腳本歸檔
- I-8/I-9：記憶體狀態落地、SSE/webhook 實際送出
- I-10：`GET /params/history`、`POST /params/rollback` 兩端點（A5）

---

## [Task 階段] — 更早

- tasks.md（三人分工）、README、CONTRIBUTING、ADR-001~004
- 架構 review v2 的 39 項衝突修正
