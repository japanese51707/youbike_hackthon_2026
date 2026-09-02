# A0~A4 實作檢查報告 — 給 Kiro 的修正清單

> 檢查日期：2026-09-02｜檢查範圍：`backend/`（A0~A4 已宣稱完成的部分）
> 檢查方式：實際啟動 FastAPI app 用 TestClient 打端點，不是只看 tasks.md 的勾勾
> 架構層面的審查見 `review_architecture_v2.md`（上一輪，39 項衝突，大部分已修）

---

## 給 Kiro 的使用說明

1. **先讀 `AGENTS.md` 與 `.kiro/steering/development_principles.md`**，本報告不取代它們。核准閘門仍然有效。
2. **修正順序照第 2 節的編號**，I-1 到 I-4 是必修（會出事），I-5 到 I-10 是建議修。
3. **第 4 節「已驗證通過」的東西不要動。** 那些是實測過行為正確的，順手重構容易改壞。
4. **全部修完、驗收指令跑過之後，才開始 A5。** 第 5 節有 A5 開工前要先確認的事。
5. 每修完一項，回來把 tasks.md 對應的勾勾補上。

---

## 1. 檢查結論

A1~A4 宣稱的驗收項目**實測全部通過**，程式碼品質好，權限、SSRF、rate limit、覆寫置頂都是真的能動的，不是骨架。上一輪架構審查的 39 項衝突，文件側幾乎都修掉了。

問題不在功能，在**工程紀律**：程式碼沒進版控、依賴清單沒跟上實作、沒有任何測試。這三件事在剩下 10 天、三人並行改同一份 `core/` 的情況下，是最容易出事的地方。

---

## 2. 必修（會出事）

### I-1　所有程式碼都沒進 git ★最高優先

- **證據**：`git log` 只有 3 個 commit（`83fd07c` initial、`fab7784` docs(model)、`4dafb4e` docs(repo)），全部是文件。`git status` 顯示 `backend/`、`frontend/`、`docker-compose.yml` 為 untracked。
- **後果**：A1~A4 約 2,900 行程式碼只存在工作目錄。誤刪或改壞沒有任何還原點；三人也無法開分支並行，一定會互相覆蓋。
- **修法**：確認 `.gitignore` 已排除 `.venv/`、`__pycache__/`、`output/`、`.env`、大型資料後，把 `backend/`、`frontend/`、`docker-compose.yml` 加入版控並 commit。依 CONTRIBUTING.md 的 Conventional Commits 格式，建議拆成幾個有意義的 commit（A0 骨架 / A1 資料源 / A2 規則引擎 / A3 警示覆寫稽核 / A4 資安），不要一個 commit 塞完。
- **驗收**：`git status --porcelain` 只剩刻意忽略的項目；`git log --oneline` 看得出 A0~A4 的軌跡。

### I-2　`requirements.txt` 缺 `boto3` 與 `pyarrow`

- **證據**：`backend/requirements.txt` 只有 fastapi / uvicorn / pydantic / pyyaml，註解還寫「之後 A1/B 需要時再加」。但 `backend/core/data/historical.py:88-89` 已經在函式內 `import boto3` 與 `import pyarrow.parquet as pq`。
- **後果**：延遲 import 讓問題被藏起來——app 啟動正常，只有在把 `config.data_source.mode` 切成 `historical` 的那一刻才 ImportError。照 README 指令裝依賴的隊友、以及 `backend/Dockerfile` 建出來的容器（只裝 requirements.txt），都會在切換資料源時掛掉。而「切 mode 能換源」正是 A1 的驗收項目。
- **修法**：把 `boto3`、`pyarrow` 加進 `requirements.txt` 並釘版本。順便確認 Dockerfile 建出來的映像能跑 historical 模式。
- **驗收**：乾淨環境 `pip install -r backend/requirements.txt` 後，切 `mode: historical` 呼叫 `GET /api/v1/stations` 不會 ImportError（拿不到 S3 憑證而失敗是另一回事，應走 degradation 並標 `data_freshness`）。

### I-3　`target_level` 與 `usage_rate` 單位不一致

- **證據**：`GET /api/v1/stations` 回 `usage_rate: 3.1`（百分比，2/64 站）；`GET /api/v1/stations/{id}/params` 回 `target_level: 0.5`（0~1 比例）。
- **後果**：FR-3 要求儀表板顯示「即時水位 vs 動態目標水位」。C 直接比大小會得到「3.1 遠高於 0.5」，所有站都判定超過目標。這是上一輪 C-05 只修了一半——`target_level` 補回端點了，單位沒統一。
- **修法**：兩者統一。建議 `target_level` 改為百分比（0~100）與 `usage_rate` 對齊，因為 `config.target.預設借用率百分比: 50` 本來就是百分比；或反過來全改 0~1 比例。**選一個，然後同步改 `api_contract.md` §2.11 的範例值**，不要只改程式。
- **驗收**：`usage_rate` 與 `target_level` 同尺度，且 api_contract 的範例值與實際回傳一致。

### I-4　沒有任何測試

- **證據**：全專案找不到 `tests/`、`test_*.py`、`conftest.py`。`design.md §2` 明列 `backend/tests/`；`AGENTS.md` 要求「跑最窄的相關測試」「沒實際跑過的檢查，不宣稱通過」。
- **後果**：A1~A4 的驗證都是一次性腳本，沒有留下來。接下來 A5 要動 params 與 SQLite、B 要接真模型、C 要串真後端，三線同時改 `core/`，沒有回歸網——改壞了要到 Demo 當天才知道。
- **修法**：建 `backend/tests/`，用 `fastapi.testclient.TestClient` 把**已經驗過的行為固定下來**。最低限度五支：
  1. `test_auth.py` — confirm 端點：無身分 401、`OP-001` 403、`OP-002` 200；optimization approve 只有 maintainer 過
  2. `test_rule_engine.py` — 給定站況 → 觸發補車/取車正確，`basis` 欄位正確（區間下界 vs 降級 vs 保底）
  3. `test_override.py` — 覆寫後該站排在建議清單第一、`priority_score` 不被竄改、到期自動恢復
  4. `test_security.py` — webhook 訂閱擋掉 localhost / 169.254.169.254 / 10.x / 非 https；rate limit 超過上限回 429 且 `/health` 豁免
  5. `test_schema.py` — `GET /stations` 回傳含 `data_freshness` 與 `source_timestamp`，欄位符合 Pydantic
- **驗收**：`cd backend && pytest` 全綠。把 `pytest` 加進 requirements（或另開 requirements-dev.txt）。

---

## 3. 建議修（不急但會累積成本）

### I-5　`config.yaml` 又和 `design.md §7` 不同步

新增了 `priority_band`、`data_source.stale_after_sec` / `s3_bucket` / `s3_prefix` / `historical_default_month`、`security.allowed_methods` / `allowed_headers` / `rate_limit_exempt_paths`，`design.md §7` 都沒有這些。

上一輪立的規矩是**先改 spec 再同步 config**。這些設定本身都合理，補進 §7 即可——重點是別讓 config 再度變成「唯一知道真相的地方」。

### I-6　A0 沒打勾，但實際已完成

`tasks.md` 的 A0 四個項目都還是 `- [ ]`，但 `backend/` 結構、12 個 Pydantic Schema（另含 enum）、`frontend/src/mock/mock_data.json`、31 個端點全部到位且會動。

這會讓 B、C 誤以為 A0 還沒好、還不能開工——而 A0 正是解鎖他們的前提。請補上勾勾與交付說明。

### I-7　根目錄 PoC 腳本與 `backend/` 同名檔混雜

根目錄還有 10 個 `.py`，其中 `rule_engine.py` 與 `backend/core/rule_engine.py` **同名但不同版本**。`archive/poc_backup/` 只收了 `config.poc_v1.yaml` 和 `rule_engine.poc_v1.py`。

B 要重構 `analysis_rebalancing_detection_v2.py` 時，很可能改到根目錄那份、或誤以為根目錄的 `rule_engine.py` 是正式版。建議把已被 `backend/` 取代的腳本移進 `archive/poc_backup/`，尚未重構的（`analysis_*.py`、`model_prediction.py`、`merge_csv_to_parquet.py`、`setup_aws.py`、`teardown_aws.py`）留在根目錄或移進 `scripts/`，並在 README 說明哪些是 PoC、哪些是正式。

### I-8　狀態全在記憶體（A5 前的 Demo 風險）

警示已讀、webhook 訂閱、③ 覆寫、稽核記錄、任務狀態目前都在記憶體。這是 A5 還沒做的必然結果，不算 bug，但要知道：**後端一重啟，剛剛示範的覆寫和稽核就消失了**。

Demo 當天若要展示覆寫 → 稽核留痕這條線，確保中途不重啟後端，或把 A5 排在 Demo 之前完成。

### I-9　SSE 與 webhook 還是骨架

`GET /alerts/stream` 目前回佇列而非真正的 EventSource；webhook 只做了訂閱時的 SSRF 檢查，實際 `httpx.post` 還沒送出（`alert_service.py:193` 的 TODO）。

兩者都有標註，但「警示通知」是題目點名、現行系統沒有的差異化亮點。要在 Demo 展示的話得留時間，別留到最後一天。

### I-10　A5 別漏兩個端點

`api_contract §3.12` 列了 `GET /stations/{id}/params/history` 與 `POST /stations/{id}/params/rollback`，目前都還沒實作。屬 A5 範圍，記得一起做。

---

## 4. 已驗證通過 — 不要動

以下是實際打過端點確認行為正確的，重構時請保留這些行為，並用 I-4 的測試把它們固定下來：

| 項目 | 實測結果 |
|------|---------|
| 權限閘門 | 無身分 401、`OP-001`(operator) 打 confirm 403、`OP-002`(dispatcher) 200；optimization approve 只有 `OP-003`(maintainer) 過 |
| `require_role` 宣告式 | 寫在端點簽名的 `Depends`，內部先驗身分再驗角色，漏驗不了 |
| 出向 SSRF | 擋掉 `http://localhost`、`https://169.254.169.254`、`https://10.0.0.5`、`ftp://`，放行 gov https |
| Rate limit | 130 次請求 → 120 通過、10 次 429；`/health` 打 20 次全 200（豁免正確） |
| ③ 覆寫置頂 | 覆寫原本排第 5 的站後，它躍至第 1，且 `priority_score` 未被竄改（覆寫走排序前綴，不動分數） |
| 輸入驗證 | 覆寫缺 `reason` / `expire_minutes` 超範圍皆回 422，帶欄位層級 `details`，不外洩堆疊 |
| 統一錯誤格式 | 4xx/422/500 都是 `{error, message}`，無內部路徑或框架版本 |
| 觸發原因可解釋 | 「30 分鐘後預測到達存量最低 0.0 台，低於安全緩衝 2 台，即將空站」+ `basis` 欄位標明依據來源 |
| 資料新鮮度 | `GET /stations` 回傳含 `data_freshness` 與 `source_timestamp`（NFR-10 / NFR-5） |
| 任務狀態機 | `TaskStatus` 含 `assigned`（已指派未開始，可轉派），`in_progress` 鎖定 |

**重跑驗證的方式**（改完程式後自己確認沒壞）：

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload        # Base URL: http://localhost:8000/api/v1
# 或直接跑 I-4 建立的測試：pytest
```

---

## 5. A5 開工前要先確認的事

`design.md` 的 A5 前置條件已經備好，可以直接開工：

- ✅ `design.md §8` 已擴充為**七張表**（tasks / audit_logs / station_params / alerts / alert_subscriptions / events / operators）
- ✅ `design.md §4.3` 已修正流程：**versioning 一定在 approve 之後**，reject 不留版本；`daily-review` 帶 `review_id`，上一筆未審批時新排程 skip

開工時請特別注意這四點：

1. **③ 覆寫不要做成兩套。** A2/A3 已經把 ③ 實作成「dispatcher 排序時的最前綴」，不改 urgency 分數。A5 的 `param_layers.py` 做 ①②③ 覆寫序時，**不要在參數層再實作一次緊急度覆寫**，否則同一件事有兩個真相。參數層的 ③ 只負責「這站現在有沒有覆寫中」這個狀態，排序行為留在 dispatcher。

2. **`param_source` 不該出現 `emergency_override`。** `model_architecture` 明訂 ③「不影響模型參數」，`override_service` 也明訂「不動模型參數」。既然覆寫不寫參數，`station_params` 就不會有 `emergency_override` 這個來源值——後台要顯示「覆寫中」請讀 `override_active` 布林，不要靠 `param_source`。

3. **記憶體狀態要一次搬乾淨。** SQLite 一落地，現有記憶體版的 alert / override / audit / task 儲存要同步改成讀寫 SQLite，不要留下「有些讀記憶體、有些讀 DB」的混合狀態。`operators` 表建好後，`auth.py` 那三個寫死的測試帳號也要改成查表（A4 已註明此事）。

4. **一個還沒定義的規則：覆寫到期時，它產生的任務怎麼辦。** `model_architecture` 只寫了覆寫「任務完成 OR 時效到期，先到先觸發」就恢復，但沒說**因該覆寫而產生、卻還沒開始的任務**要不要一起取消。若不定義，會出現「系統已經不認為這站緊急，調度員手上卻還有一張因它產生的任務」。建議在 A5 順手定義並寫進 spec：覆寫到期時，由它產生且仍在 `assigned` 的任務一併降級或取消，`in_progress` 的不受影響，兩種情況都留稽核。
