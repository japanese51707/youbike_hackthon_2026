# 架構審查報告 v2 — 給接手修正的 AI agent

> 審查日期：2026-08-31　審查對象：`design_dataflow.drawio` + `.kiro/specs/` 四份 + `.kiro/steering/` + `config.yaml`
> 同內容的可視化版本：`review_architecture_v2.html`（含修正後的架構圖）

## 給 AI agent 的使用說明

1. **先讀 `AGENTS.md` 與 `.kiro/steering/development_principles.md`**，本報告不取代它們。
2. **核准閘門仍然有效**：動任何檔案前先說明計畫（目標、影響檔案、架構影響、風險、驗證指令），等使用者核准。
3. **本報告的優先序**：第 3 節「已完成」不要重做；第 5 節「會出事」是下一批要修的；第 4 節是圖的問題，改圖不改碼。
4. **不要動的東西**：`youbike資料集/`（原始資料）、`output/youbike_parquet/`（實際資料源）、`.venv/`、`config.poc_v1.yaml` 與 `rule_engine.poc_v1.py`（回滾用備份）。
5. **核心約束不可違反**：LLM/AI 只做估計，確定性規則引擎才能做調度決策。規則引擎吃預測**區間下界**，不吃點估計。

---

## 1. 總評

五層骨架（資料源 → 執行平面 → 控制平面 → API → 前端）與 `design.md §1.1` 一致，A/B/C 分工歸屬正確，方向沒有問題。

問題分三類：
- **圖沒畫出 spec 的核心設計**（第 4 節，10 項，多數已修）
- **文件之間互相打架**（第 5 節，39 項，尚未修）
- **根因**：`api_contract.md` 與 `requirements.md` 停在 2026-08-19，`design.md` / `model_architecture.md` / `parameter_groups.md` 已走到 08-31。39 項裡超過一半是舊版沒同步，不是設計想錯。**先補這兩份文件，一半的問題會一起消失。**

---

## 2. 這次已經改動的檔案

| 檔案 | 動作 |
|------|------|
| `config.yaml` | 換成 `design.md §7` 的動態判斷版（17 個設定區塊），檔頭寫明決策 |
| `config.poc_v1.yaml` | 舊的死數字版，原封保留（回滾用） |
| `rule_engine.py` | 遷移成動態觸發版，已用 1554 站真實快照實跑驗證 |
| `rule_engine.poc_v1.py` | 舊版原封保留（回滾用） |
| `.kiro/specs/.../design.md` | §7 補上 `fleet.調度車數量` / `fleet.響應時間_分鐘`、註明「時段 = 30 分鐘」、把觸發註解改成「吃 lower_bound」 |
| `design_dataflow_v2.drawio` | 修正版架構圖（原檔 `design_dataflow.drawio` 保留） |

---

## 3. 已完成的修正（不要重做）

### 3.1 觸發門檻改為動態判斷

**決策**：以 `design.md` 的動態判斷為準，不用固定死數字。

主判斷（`rule_engine.py`）：
```
調整後到達存量 = 當前存量 −（當前存量 − 預測區間下界）× trigger.觸發靈敏度
若 調整後到達存量 ≤ trigger.安全緩衝_台數 → 觸發補車
滿站側對稱：預測可還位下界 = (總車柱 − 當前存量) −（區間上界 − 當前存量）× 靈敏度
```

三層依據，每筆建議都帶 `判斷依據` 欄位，降級絕不偽裝成預測值（NFR-5 失敗可見）：
1. `區間下界` — 主判斷
2. `歷史同時段淨流出（降級）` — 沒有預測區間時
3. `保底門檻` — 低/高水位借用率百分比

**順帶解掉的矛盾**：`design.md §7` 原本只寫「用歷史同時段淨流出算到達存量」，但 `steering §5` 與 `design §3` 都要求 rule_engine 吃區間下界。兩者若各自實作，會變成繞過模型用歷史均值減法——不會報錯，只會在尖峰系統性漏觸發。已把 §7 註解與 config 檔頭統一成「吃 lower_bound，歷史淨流出只是降級路徑」。

### 3.2 補回三個設定 key（先改 spec 再同步 config）

- `fleet.調度車數量: 20` — 消費者：`min(每時段最大調度站數, 調度車數量 × 每趟最大站數)`
- `fleet.響應時間_分鐘: 30` — 消費者：觸發判斷的前瞻窗口，觸發原因會寫「30 分鐘後預測到達存量…」
- `每站最大搬運量` 由 `fleet.每車容量` 取代

### 3.3 實跑後發現（尚未解決，交給 B）

`output/model_results/prediction_sample.csv` 在測試時間點只對上 **1 / 1554 站**，其餘全走降級路徑。這是 sample 檔本來就只有單站時間序列，不是遷移造成的。B 產出全站預測時，需要輸出 `場站名稱 × 時間點` 的完整區間，rule_engine 才會走主判斷。`判斷依據` 欄會誠實顯示降級，可當成對接完成的驗收訊號。

---

## 4. 架構圖的落差（已在 v2 圖修正）

| # | 問題 | 依據 | 修正 |
|---|------|------|------|
| 01 | 參數三層被壓成一個方塊 | `model_architecture.md` 稱其為「最核心的設計決策」，三層來源散在三處 | 拉成獨立的參數子系統，畫出 ①→②→閘門→③→生效參數 |
| 02 | `geo_batch` 放錯層 | `design.md §2` 放在 `backend/params/`，是批次一次算 | 移進參數子系統的 ① 基礎參數 |
| 03 | 箭頭只連分區框不連模組 | 原圖五條主箭頭全是 `l1bg → l2bg` | 畫出 rule_engine → dispatcher → 閘門 → task_manager 主鏈 + 兩條回流 |
| 04 | 缺 `degradation`（NFR-10） | `design.md` 有 `data/degradation.py` | 放在資料源層底部 |
| 05 | 缺 `data_source` 介面本體、漏 YouBike 官方源 | NFR-7 可抽換是核心價值 | 介面畫成實體橫條，五個源匯入 |
| 06 | 缺 `simulation/replay`（FR-5）與站點動態管理（FR-13） | API 層有端點，下面沒有模組 | 補進控制平面第二排 |
| 07 | 儲存層畫在前端正下方 | 與「前端不碰 DB」視覺矛盾 | 移到右側橫切欄，補 `versioning` 與模型檔 |

**顏色與呈現問題**（v2 已修）：分區底色與模組方塊同色值（`#e1d5e7` 對 `#e1d5e7`）導致方塊隱形；圖例用 emoji 色塊與實際色系對不上；所有方塊未指定 `fontColor`，draw.io 深色模式會看不見；webhook 線硬編 `x=1600` 落在內容區外。

---

## 5. 文件之間的邏輯衝突（39 項，尚未修）

### 5.1 會出事（12 項）

**C-01 緊急度尺度自相矛盾：0~100 vs 8.7**
- `api_contract §4` / `§2.12`：`calc_urgency()` 回傳 0~100、`"urgency_score": 65`
- vs `api_contract §2.3` 範例：`"priority_score": 8.7`
- 後果：C 顯示 8.7/10、A 用 `config.alert.warning_urgency: 60` 判等級、B 回 0~100。整合當天所有站都不會觸發 warning。
- 建議：§2.3 範例改 87.0，註明兩者同尺度 0~100。

**C-02 ③ 覆寫要拉滿緊急度，但沒有介面能把覆寫送進去**
- `parameter_groups §緊急度因子`：「即時人工覆寫（③層）｜緊急直接拉滿 100」
- vs `api_contract §4`：`calc_urgency(prediction, station_meta, arrival_minutes)` 不含覆寫
- vs `design §1/§3`：urgency 在無狀態執行平面、覆寫在有狀態控制平面，`override_service` 明訂「不動模型參數」
- 後果：最後只能在 dispatcher 偷加 if，決策邏輯散到兩處。
- 建議：二選一寫死——`calc_urgency()` 加第四個參數 `override`，或明訂「覆寫不進 urgency，只在 dispatcher 排序時當最前綴」。

**C-03 `horizon_minutes` 綁死「調度到達時間」，但三個消費場景沒有調度員**
- `api_contract §2.2`：「等於『調度到達時間』…只在調度員要觸發新任務時才計算」
- vs `§2.5` + `config.refresh_interval_sec: 60`：每 60 秒全市警示掃描要先跑預測 + 緊急度
- vs `§2.12/§8.8`：歷史時間軸要為過去每時間點每站預存 `urgency_score`
- 建議：拆兩種 horizon（警示/歷史用固定 `default_horizon_minutes`，派任務才用動態），Prediction 加 `horizon_source`。

**C-04 環境係數鎖死 [0,1]，需求上升無法表達**
- `design §7`/config：「所有係數範圍 [0,1]，最大 1（完全不影響需求）」，`holiday_factor` 全 1.0
- vs `parameter_groups` 群組 4：「暫時**調高**該站的需求參數」；`api_contract §2.7`：`influence_factor: 1.8`
- 建議：值域改 [0,3]（1.0 = 無影響），或分成衰減係數 [0,1] 與放大係數 [1,N]。

**C-05 `target_level` 單位與存在與否有兩種說法**
- `api_contract §2.11`：`"target_level": 0.5`（比例）vs `design §7`：`預設借用率百分比: 50`
- 而且 `§3.12` 回傳範例裡 `target_level` 消失了，只剩 `outflow_rate`/`inflow_rate`/`buffer_level`
- 後果：FR-3 的「目標 vs 現況」畫不出來；`usage_rate` 18.75 對比 `target_level` 0.5 會判定所有站滿載。
- 建議：統一 0~1 比例（`usage_rate` 一起改），補回 §3.12 的 `target_level`。

**C-06 SQLite 三張表放不下至少四種狀態**
- `design §8` 只有 `tasks` / `audit_logs` / `station_params`
- 缺：警示已讀 `acknowledged`、webhook 訂閱 `callback_url`、生效中 `events`、調度員 `today_stats`
- `tasks` 表另缺 `estimated_travel_minutes`/`estimated_work_minutes`/`estimated_distance_km`/`assigned_at`/`route_map_url`
- 後果：重啟後已讀警示變未讀、機關訂閱消失、工時歸零導致 `fatigue.法定休息間隔小時` 失效。
- 建議：補四張表 + tasks 五個欄位。

**C-07 事件影響計算沒有任何模組負責（完整死路）**
- `api_contract §3.15`：「系統自動換算影響半徑、找出範圍內站點、計算各站影響度」
- vs `design §2/§3`：B 與 A 的模組清單裡都沒有；`api/events.py` 標為「對應端點的轉發」
- 後果：`affected_stations` / `influence_factor` 沒有生產者，config 的 `event_radius` / `event_impact` 沒人讀。
- 建議：新增 `backend/prediction/event_impact.py`（B），介面 `compute_event_impact(event, stations) → affected_stations`。

**C-08 存取控制沒落地，report 端點無法驗證身分**
- `NFR-8`/`design §6.2`：「調度員只能回報自己的任務」「權限一定在後端驗」
- vs `config.security` 只有 CORS 與 rate limit；`design §2` 沒有 auth 模組
- vs `api_contract §3.6/§3.13`：report body 只有 `status`/`note`/`operator_location`，沒有身分
- 後果：`POST /dispatch/confirm` 這個人在迴圈的唯一閘門任何人都能直接打，NFR-2 形同虛設。
- 建議：加 header `X-Operator-Id` + config 角色對照表，report body 補 `operator_id`。

**C-09 「資料過期標記」沒有 Schema 欄位承載**
- `NFR-10`：「標記為『資料過期』，前端顯示提醒」vs `api_contract §2.1` StationStatus 十一個欄位都沒有旗標
- 建議：加 `data_freshness: "live" | "stale" | "historical_fallback"` 與 `source_timestamp`。

**C-10 任務狀態機缺「已指派、未開始」，動態轉派無法成立**
- `model_architecture ③-4`：「尚未開始執行 → 可轉派；一旦開始 → 鎖定」
- vs `api_contract §2.4`：只有 `pending`（待派發）/ `in_progress`（執行中）
- 後果：填 `pending` 會被重複派發，填 `in_progress` 則永遠不能轉派，FR-10 直接死掉。
- 建議：加 `assigned` 狀態，轉派條件 = `task_type == emergency AND task_status == assigned`。

**C-11 天氣 API 串接同時指派給 C 和 A**
- `parameter_groups §分工提示`：「群組 3：**C** — 串接天氣 API」
- vs `design §2/§3`：`data/weather_api.py` 與 `api/weather.py` 都在 **A** 名下，C 只有 frontend/
- 建議：API 串接歸 A、係數校準歸 B，改掉 parameter_groups 那行。

**C-12 車隊三個數字推導不出可行班表**
- `config.fleet`：每車容量 25 / 每趟最大站數 5 / 每時段最大調度站數 15；`fatigue.單次最大搬運量 150`
- vs `api_contract §2.3/§2.4`：單站 `quantity: 15`、一趟三站 45 分鐘
- 矛盾：5 站 × 15 台 = 75 台 > 每車容量 25 的三倍；單趟 45 分鐘 > 時段 30 分鐘；「單次 150」若指一趟又和 25 衝突。
- 建議：註明「單次 = 單一輪班」；`每趟最大站數` 改由 `每車容量 ÷ 平均 quantity` 推導或降為 2~3。

### 5.2 需要釐清（16 項）

| 項目 | 衝突點 | 建議 |
|------|--------|------|
| `params/` 三個檔沒人負責 | `design §2` 有 `param_layers.py`/`versioning.py`/`station_params.py`，§3 分工表 A 只涵蓋 api+core+data、B 只認領 geo_batch | 整個 `params/`（geo_batch 除外）劃給 A |
| 覆寫端點沒有路由檔 | ② 與 ③ 混在 `3.12`，但 `api/optimization.py` 明訂「不跑最適化演算法」也沒提覆寫 | 拆 `api/overrides.py`；契約拆成 3.12(②) 與 3.20(③) |
| ③ 覆寫不寫參數卻被建模成參數版本 | `model_architecture ③`「不影響模型參數」 vs `param_source` 有 `emergency_override` | 移除該列舉值，改用 `override_active: bool` |
| `anomaly_tags` 八個標籤只有一個有生產者 | `§2.12` 列 8 個，design 只有 `rebalance_detector` 且回傳信心分數不是標籤 | 新增 `prediction/anomaly_tagger.py`（B），指定寫回 Parquet |
| FR-12 熱溫冷沒有執行者 | config 有 `retention`、design §5 有表，但 `scripts/` 沒有歸檔腳本也沒排程 | 補 `scripts/retention_job.py` 或標「僅設計不執行」 |
| NFR-9 最硬的效能要求沒有端點 | 「調度員 1~2 秒、只推工作範圍」vs 唯一推送通道是全市警示 SSE | 加 `GET /operators/{id}/stream`，或降級為輪詢並註明 |
| NFR-4 說無伺服器費用，部署卻是 EC2 | `NFR-4` vs `§8.3`/`design §10`「EC2 Free Tier（主）」 | 改寫成「資料層 Serverless、運算層 EC2」+ 記 ADR |
| 調度到達時間兩項還是三項 | `§2.2` 說三項並指向 `parameter_groups §7`，但 §7 標題明寫「兩項加總」 | 以三項為準，修 parameter_groups §7 |
| 最適化排程 × 人工確認會堆積 | `design §4.3` 把 versioning 排在人工確認**之前**；reject 後那筆版本狀態未定義；`daily-review` 是單數資源 | versioning 移到 approve 之後；加 `review_id`，未審批時新排程 skip |
| 覆寫到期 vs 任務未完成誰贏 | 覆寫「先到先觸發」恢復 vs 一般任務「一旦指派系統不能收回」 | 明訂「覆寫到期時未開始的任務一併降級或取消，執行中不受影響」 |
| 前瞻窗口緊急度歸 A 還是 B | `api_contract §1`（8/19）寫在 A 的規則引擎 vs `design §3` 在 B 的 `urgency.py` | api_contract §1 對齊 design §3 |
| `data_source` 設定格式不同 | `§6` 是字串 `data_source: "tdx"` vs config 是物件；第四種來源 `youbike_official` 只在 design 與 config | §6 改物件並補第四種；NFR-7 同步 |
| 三個參數缺來源或載體 | `buffer_level` 在 Schema 但五個群組都沒定義；`nearby_stations`/`capacity_class` 有定義、FR-13 要重算，但 StationParams 沒這兩欄 | Schema 補兩欄；`buffer_level` 補定義或刪除 |
| `predict()` 回傳欄位不足 | `§4` docstring 回 3 欄 vs `§2.2` Prediction 7 欄，而 `GET /stations/{id}` 要回完整 Prediction | 明訂由 A 補時間/識別欄，或 docstring 補成 7 欄 |
| 油耗率與車速沒進 config | `§2.4` 要算 `estimated_fuel_cost`「依距離 × 油耗率」，config 全檔沒有；`steering §3` 說任何閾值都不准寫死 | config 新增 `cost` 與 `travel` 兩區塊 |
| 路由順序會互相攔截 | `/stations/heatmap`、`/stations/timeline` 會被 `/stations/{station_id}` 吃掉；`/dispatch/overview` 被放進 `api/operators.py` | 靜態路徑先註冊；overview 移回 `dispatch.py` |

### 5.3 小不一致（11 項）

1. `usage_rate` 公式 `available_bikes / total_docks` 算不出範例值 18.75（漏 ×100）。
2. 低/高水位兩套數字：`§2.1` status 用 <15%/>85%，config 保底門檻 10%/90%。
3. 回報端點路徑兩處不同：`design §4.2` 的 `/tasks/{id}/report` vs `/dispatch/tasks/{task_id}/report`。
4. `history_24h` 這個參數不存在，`§3.2` 實際是 `history_range=24h|7d`。
5. 天氣類別對不上：parameter_groups 寫「雷雨」，config/§2.10 是 `heavy_rain`（豪雨）。
6. 同一時刻兩個空站數：`§3.7` `empty_rate: 5.66` × 1583 ≈ 90 站 vs `§2.9` `empty_stations: 45`。
7. Operator 範例工時算不出來：06:00 上班、`total_work_minutes: 285`，但 `assigned_at` 是 08:05。
8. `steering §3` 的「✅ 正確」範例仍是 `config["trigger"]["空站危險_可借車數"]`，該 key 已不存在，照抄會 KeyError。
9. `requirements §9`：「區間覆蓋率 目標 ~80%｜現況 ✅ 78.7%」——未達標卻打勾。
10. `api_contract.md` 標題還是「v2 草稿」、日期 8/19，但已被 design.md 當定案引用。
11. 「時段」長度過去從沒定義，這次已在 config 補成「時段 = 30 分鐘」，parameter_groups 與 api_contract 尚未同步。

### 5.4 沒找到問題的部分

「LLM 直接做調度決策」這條核心約束，七份文件在文字層面都守住了，沒有明確違反。最接近失守的是原本 config 的觸發註解只講點估計（已修）——那類問題不會報錯，只會讓系統安靜地變差。

---

## 6. 建議的修正順序

1. **先補 `api_contract.md` 與 `requirements.md`**（停在 8/19 的兩份）。39 項裡超過一半會一起消失。
2. **C-01 / C-02 / C-05**：緊急度尺度、覆寫進不了緊急度、`target_level` 單位。這三項不修，W3 三人對接當天一定會撞上。
3. **C-08**：至少加一層最簡身分驗證，否則人在迴圈的閘門是假的。
4. **C-07 / C-06**：補事件影響模組與四張表，否則有端點沒有實作。
5. 圖：v2 確認後，把 `design.md §9` 的圖說更新成 v2 內容（新增參數子系統、降級路徑、回流路徑三項）。
