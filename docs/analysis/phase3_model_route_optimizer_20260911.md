# 第三批：模型驗證、路線可執行性與最適化一致性

日期：2026-09-11。分支：`feature/A-dispatch-safety-lifecycle`。依 owner「照你的建議做」核准。
未 stage／commit／push；第一、二批既有變更全數保留。

決策：[ADR-122](../decisions/ADR-122-時序評估協議與標籤完整性.md)（supersedes ADR-106）、
[ADR-123](../decisions/ADR-123-路線載量守恆與逐站到達可行性.md)、
[ADR-304](../decisions/ADR-304-派工可行性閘門與最適化套用一致性.md)。
A 批的詳細數字另見 [model_validation_phase3](model_validation_phase3_20260911.md)。

## 一、A 模型驗證與標籤（ADR-122）

| 問題 | 修正後行為 |
|---|---|
| 時序 CV 折內洩漏 | `build_training_frame(fit_mask=...)`；統計量（站點識別 p50、周轉量與權重、行為指紋、介入基準 mean-std）只在擬合窗口擬合再 transform；`run_tuning` 每折各自組表 |
| 跨界標籤 | 新增 `is_train_{30,60,90,120}`，依 `dt + 視野` 切分；輸入在訓練期但答案跨進驗證期的列不進訓練集 |
| 補值當答案 | 新增 `is_imputed` 與 `target_imputed_{mins}`；訓練排除補值標籤，評估主指標只用真實觀測，補值列另計 |
| 遮罩只蓋起始列 | 新增 `is_rebalancing_{mins}`（t..t+h 任一格為介入即遮）與逐視野 `is_censored_{mins}` |
| 輸出語意 | 評估模組標明 `event_basis`：模型用區間下界判危險（與 ADR-111 一致），基準用點估計，兩者不對等；不把負向預測當已證實需求量 |
| 不覆蓋現行模型 | `run_train_save --out-dir` 預設 `_models_candidate/`；`_models/` 未動，serving 不變 |

新增 `backend/prediction/evaluation.py`（統一指標）與 `tools/run_offline_eval.py`（修正前後對照）。

## 二、B 路線可執行性（ADR-123）

| 問題 | 修正後行為 |
|---|---|
| 無車輛初始載量 | `vehicles` 加 `onboard_bikes`／`onboard_source`／`onboard_observed_at`（冪等擴欄）。未回報或過期 → 草稿標阻擋原因、確認回 409，**不假設為零**。新增 `POST /vehicles/{id}/onboard`；結案由實際回報推算並寫回，推不出來就標回未知 |
| 只檢查總量 | 新增 `core/dispatch_feasibility.py`：依路線順序逐站累加（取車 +q／補車 −q），全程須落在 `[0, 容量]` |
| 整趟共用同一視野 | 逐站累計行車 + 作業時間得到到達偏移，各站取最接近的視野（30／60／90／120）；超出最長視野標記 `stop_beyond_forecast_horizon`，不外推 |
| 工時規則沒接線 | `shift.check_labor` 正式接入；另檢查班別跨區限制與人／車既有未結束任務的時間重疊 |
| 預覽與確認驗證不同 | 三入口組單與 `confirm-trip` 呼叫同一個 `evaluate_feasibility`；草稿回 `blocking_reasons` 與 `load_plan`；後台加站也重跑同一份評估 |
| 保留既有安全機制 | 人工確認閘門、單一交易、重送不重派、結案釋放全部沿用 ADR-302，未放寬 |

距離與時間沿用既有 haversine 與 `config.travel`，未新增付費路線服務。

## 三、C optimizer 與排程（ADR-304）

| 問題 | 修正後行為 |
|---|---|
| 參數是否被讀取 | **查核結果：沒有**。`grep` 全 backend，`get_effective_params`／`station_params` 的消費端只有 `api/stations.py` 三個唯讀端點；`rule_engine`／`dispatcher`／`prediction` 零讀取。維持 ADR-120 做法 Y，本批不接線，並新增測試固定「approve 後規則引擎輸出不變」 |
| 狀態語意不分 | `status ∈ {ok, no_data, insufficient_samples, failed}` + `reason` + `diagnostics`；計算失敗回 `failed` 並帶例外類型，樣本不足逐站列出 |
| 重複觸發 | `review_id`（uuid4，不可猜測）；`approve` 必填，重送回原結果不重複寫版本；已退回／已套用的建議不可再改 |
| 部分寫入 | `commit_optimized_batch` 在單一交易；任一站失敗整批回滾，不再回「部分成功」。`params_repo` 改用共用交易的 `commit()`，不再提前提交 |
| 回滾未驗證 | `rollback` 後重讀當前生效參數，不等於目標版本即拋錯讓交易回滾 |
| 雲端排程 | 不啟用，維持手動觸發的離線分析 |

## 四、驗證結果

```bash
# 後端全套（記憶體 SQLite，MockPredictor 隔離外部讀取）
PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 python3 -B -m pytest \
  -p no:cacheprovider -o addopts='' backend/tests -q
```

| 階段 | 結果 |
|---|---|
| 第二批基線 | 218 passed |
| C 批後 | 234 passed（+16 `test_optimizer_apply.py`） |
| B 批後 | 250 passed（+16 `test_dispatch_feasibility.py`） |
| A 批後 | 257 passed（+7 `test_label_integrity.py`） |
| 前端接線後 | 258 passed（+1 司機自報授權回歸）；前端 **11 tests passed** + Vite build 通過 |
| 全量評估後 | **262 passed**（+4 `test_evaluation_protocol.py`，守住評估口徑） |

小型固定資料的修正前後對照（A 批）：以 `git show HEAD:backend/prediction/feature_pipeline.py`
換回舊版後跑同一組測試，**7 failed**；換回新版 **7 passed**。

離線評估（60 站子集、51 萬列、6 月驗證約 8.5 萬列、實際空滿事件約 1.14 萬件）：

- 修正前後整體 MAE 幾乎不動，但**已空區 MAE 在長視野明顯變差（60／90／120 分 +9.5%／+7.4%／+10.9%）、
  覆蓋率由 82.x% 降到 80.x%**——洩漏被拿掉後，原本偏樂觀的正是決策最在意的區域。
- 模型 vs 基準（含 POI／指紋／地形因子）：整體 MAE **沒有明顯贏過 seasonal naive**（30 分小勝、
  60／120 分打平、90 分小輸），但**已空區 MAE 比基準低 14～19%**；兩者都明顯贏過 persistence。
- P10–P90 覆蓋率 79～81%（名目 80%），分位數交叉率 ≤0.3%。
- 事件 precision 低於基準、recall 高很多，是因為模型照規則引擎的用法以區間下界判危險
  （寧可多喊少漏），與基準的點估計不對等，報告已標明 `event_basis`。

### 全量評估（1,583 站、13,324,945 列、含天氣、修正後協定選參）

完整數字見 [model_validation_phase3 §4.2](model_validation_phase3_20260911.md)，
可重現步驟見 [`tools/fullscale_eval/README.md`](../../tools/fullscale_eval/README.md)。三個結論：

1. **超參數不用改**：ADR-110 既有那組在修正後的協定下 CV 2.3263，贏過 12 組隨機搜尋（最佳 2.3747）
   與預設值（2.4523）。洩漏修正沒有推翻當初的調參結論。
2. **整體 MAE 模型輸給 seasonal naive**（四個視野都輸或打平），但拆開看，
   **輸的全部來自 3～4% 的「截斷列」**——那些列的答案是被物理邊界壓抑的 0，ADR-105 已宣告不可信、
   訓練時也排除了，評估卻仍拿它當答案。persistence 在那裡 MAE 剛好 0.000，不是比較準，是永遠猜 0。
   **在標籤可信的列上，模型四個視野全部贏過兩個基準**（未截斷 MAE 低 1.7～2.9%，排除 Δ=0 後低 4.3～5.5%；
   「未截斷且 Δ≠0」的事件 F1 高 6～9 個百分點），區間覆蓋率 80.8～81.2%（名目 80%）。
3. **60 站子集的結論是錯的**（子集上模型在已空區贏 14～19%，全量相反）。子集取的是高周轉站，
   全量有大量低流量站。往後不要用少量站點下判斷。

因此 `evaluation.py` 新增 `label_censored`，把 `excluding_censored`／`censored_only` 納入協定，
並以 `tests/test_evaluation_protocol.py` 固定口徑。

**`_models_candidate/` 不換掉 `_models/`**：候選 booster 只用 1～5 月訓練（要留 6 月驗證），本來就不可上線；
可信標籤上的改善只有 1.7～2.9%；換版要同時換 12 個 booster 與特徵包並通過 ADR-121 成套驗證。
建議賽後再用修正後 pipeline 以全量 1～6 月重訓、重建特徵包後換版。候選 booster 為評估產物，不納入 repo。

其他檢查：三份新 ADR 的 frontmatter 與索引（ADR-000 登記表、`docs/decisions/README.md`）已同步，
ADR-106 標為 `superseded`，`superseded-by: ADR-122`。API 契約（`.kiro/specs/.../api_contract.md` §3.4／3.12
與 `docs/api_reference_for_frontend.md`）已同步新增欄位與錯誤語意。`git diff --check` 通過。

## 四之二、前端接線（第三批補做）

| 檔案 | 內容 |
|---|---|
| `frontend/src/utils/dispatchGating.js`（新） | 純邏輯：`blockingReasonsOf` / `canConfirm` / `onboardBlocking` / `nextStepFor`。**`blocking_reasons` 非空 → 確認鈕失效**，並把每個 code 對應到「下一步該做什麼」 |
| `frontend/src/utils/dispatchGating.test.js`（新） | 6 項 node --test：乾淨草稿可確認、有阻擋原因即失效、缺人車不可確認、缺欄位視為無阻擋、載量類原因可辨識、每個 code 都有下一步 |
| `frontend/src/api/dispatchApi.js` | 新增 `reportVehicleOnboard()`；可行性判斷改由 `dispatchGating` re-export，避免兩份定義 |
| `frontend/src/api/taskApi.js` | 新增 `reportVehicleLoad()`（司機回報自己任務中的車） |
| `frontend/src/components/dashboard/RecommendationPanel.jsx` | 阻擋原因逐條顯示＋下一步；載量未知／過期時提供就地回報並自動重新 build；車輛下拉顯示車上台數；逐站顯示到達時間、採用視野、完成後車上台數；無阻擋時顯示「檢查皆通過」 |
| `frontend/src/pages/BackendDriverPage.jsx` | 任務卡顯示出車／預計收車載量，並可更正車上台數 |

同時修掉一個實作 bug：`POST /vehicles/{id}/onboard` 的司機自報授權原本讀 `get_operator` 回傳的 dict，
但該 dict 只有 `{operator_id, role}`，沒有 `role_type`／`current_task_id`，導致**指派中的司機會被誤判 403**。
改為查 `operators_repo` 主檔，並新增回歸測試 `test_driver_can_report_only_own_task_vehicle`。

前端驗證：

```bash
cd frontend && npm ci && npm run build
node --test src/api/httpClient.test.js src/utils/escapeHtml.test.js src/utils/dispatchGating.test.js
```

結果：Vite build 通過（4,630 modules，約 5.3 秒）；**11 tests passed**（第二批 5 項 + 本批 6 項）。
另以 TestClient 做了一次端到端契約核對：`/vehicles` 帶 `onboard_bikes`、載量未知時草稿帶
`vehicle_onboard_unknown` 且確認回 409、回報後重新組單無阻擋、`stations[]` 帶
`arrival_offset_min`／`horizon_used_min`／`onboard_after`、任務帶 `onboard_start`／`onboard_planned_end`、
司機可報自己的車、別的司機 403。

**最適化 daily-review 沒有接前端**：目前前端完全沒有這個畫面，而 ADR-304 第 7 條明確要求
不得把「已套用」呈現成「調度行為已改變」。在係數尚未生效前建這個 UI 會誤導，故不做，
`approve` 的 `review_id` 契約改動對現有前端沒有影響。

## 五、契約變更（前端需同步）

1. build 三入口回傳新增 `blocking_reasons`／`load_plan`／`onboard_start`／`onboard_end`；
   **`blocking_reasons` 非空就不要讓使用者按確認**。
2. 新增 `POST /vehicles/{vehicle_id}/onboard`（回報車上台數）。
3. `POST /optimization/daily-review/approve` **新增必填 `review_id`**。目前前端沒有最適化 UI，
   故無既有呼叫端受影響；未來要做這個畫面時必須帶上。
4. `daily-review` 的 `status` 值域擴充為四種。
5. 既有欄位名稱與型別皆未移除或變更。

## 六、剩餘限制

- 全量評估已完成（含天氣／POI／指紋／地形）；**上線模型維持不動**，換版建議留到賽後（見上）。
- 選參用單塊子集（159 站）；全量選參需 40+ 次全量擬合，成本不成比例。
- 全量管線在 7 GB 記憶體下必須分塊（單次建 200 站特徵就會 OOM），中間結果約 2.3 GB 落地。
- 未做每站型分層分析：低流量站也許查表就夠，高周轉站才需要模型；本次只做全市彙總與截斷／未截斷切分。
- conformal 校準、ADR-105 的需求插補仍未做，輸出語意仍是淨變化而非需求量。
- 車輛載量的自動回報（車隊 API）未接，現階段靠人工回報或結案推算；直線距離低估實際路程，ETA 為估算值。
- 跨趟的完整車輛庫存帳未做，只做到結案推算。
- optimizer 的調整係數**仍未生效**；`_pending_review` 仍是單程序記憶體，多實例需另行設計。
- Docker daemon 未啟動，容器未驗證（沿用第二批限制）。本次測試在 Linux 容器以 Python 3.11 執行
  （專案 `.venv` 為 macOS Python 3.14，沙盒無法執行），依賴版本依 `requirements.txt` 釘選安裝。
- 未做瀏覽器端自動化點擊驗證；前端驗證為 Vite build、node --test 與 TestClient 端到端契約核對。
- 孿生頁、舊司機頁與部分總覽資料仍為明確 Mock；最適化 daily-review 沒有前端 UI（刻意，見四之二）。

## 七、主要檔案

模型：`backend/prediction/{feature_pipeline,train,evaluation}.py`、`tools/run_offline_eval.py`。
派工：`backend/core/{dispatch_feasibility,dispatch_builder,dispatcher,task_execution}.py`、
`backend/db/{schema.sql,connection.py,vehicles_repo.py,tasks_repo.py}`、`backend/api/operators.py`、
`backend/models_schema/dispatch.py`、`config.yaml`。
最適化：`backend/optimization/param_optimizer.py`、`backend/api/optimization.py`、
`backend/params/{versioning,station_params,__init__}.py`、`backend/db/params_repo.py`。
前端：`frontend/src/utils/dispatchGating.{js,test.js}`、`frontend/src/api/{dispatchApi,taskApi}.js`、
`frontend/src/components/dashboard/RecommendationPanel.jsx`、`frontend/src/pages/BackendDriverPage.jsx`。
測試：`backend/tests/{test_label_integrity,test_dispatch_feasibility,test_optimizer_apply}.py`
及既有測試的夾具調整（`conftest.py` 的載量回報慣例、四個既有測試補宣告出車載量）。
