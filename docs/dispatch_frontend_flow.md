# 後端假設的前端調度流程（步驟結構）

> 來源：backend/api/dispatch.py、core/dispatch_builder.py、core/dispatch_confirmation.py、
> core/dispatch_drafts.py、core/dispatch_guards.py、core/task_execution.py、core/task_manager.py、
> core/dispatcher.py，以及 ADR-119 / ADR-302 / ADR-206。
> 對應圖檔：`docs/dispatch_frontend_flow.drawio`（3 頁）。
> 整理日期：2026-09-10

---

## 一句話總結

後端假設的前端是「**看板 → 三入口組單 → 預覽草稿 → 確認閘門 → 逐站回報 → 自動結案 → 滾動下一趟**」，
系統只算建議、**所有派工指令都必須是後端預覽產物**，人（後台）拍板才落地。

---

## 步驟結構

### ① 登入／選身分
- `POST /auth/login` → `{operator_id, password}`，回 `{message, operator}`（不含密碼雜湊）。
- 之後所有寫入請求帶標頭 `X-Operator-Id`。
- 角色決定可用動作：`dispatcher` / `maintainer`（組單、確認、加減站）、`driver` / `depot_standby`（執行）。

### ② 戰情看板（唯讀，組單的起點）
| 端點 | 用途 |
|---|---|
| `GET /dispatch/recommendations?limit=&priority=` | 需調度清單（**後端已排序**） |
| `GET /dispatch/claim-map?district=` | 哪些站已被別的任務認領（防重複組單） |
| `GET /alerts`、`GET /emergency/deadlocks` | 警示與死結大站 |
| `GET /kpi`、`GET /stations` | 全市統計與地圖底圖 |

排序規則已在後端做完：**③即時覆寫站強制置頂 → 再依 `priority_score` 由高到低**，並套用資源上限
（站數 ≤ min(每時段最大調度站數, 車數 × 每趟最大站數)）。

每筆建議的關鍵欄位：
- `target_available` — **主指令**：補到／抽到幾台（`quantity` 只是輔助顯示）
- `urgency_tier`（censored / warning / normal）、`priority_score`、`priority_level`
- `breach_horizon_min`、`arrival_by_horizon{30,60,90,120}` — 前瞻趨勢
- `reason`（中文原因）、`basis`（判斷依據）、`override_active`

> 前端不得自行計算數量或目標水位。

### ③–④ 三入口組單（產出草稿 draft，**不落地**）
全部需 `dispatcher` / `maintainer`。

| 入口 | 端點 | body | 回傳額外欄位 |
|---|---|---|---|
| (a) 以車為起點 | `POST /dispatch/build/from-vehicle` | `{vehicle_id, operator_id, district?}` | — |
| (b) 以站為起點 | `POST /dispatch/build/from-station` | `{station_id, vehicle_id?, operator_id?}` | `vehicle_candidates{in_district, nearby, depot_standby}` |
| (c) 緊急出車 | `POST /dispatch/build/emergency` | `{station_ids[], vehicle_id?, operator_id?}` | `resource_suggestion{nearest_idle, reserve_standby}`、`mode="emergency"` |

三入口共同底層：需調度清單 → `_pack_trips`（依車載運上限與每趟最大站數切一趟）→
`_order_route`（先取後放最近鄰）→ `_estimate_trip_kpi`（預估）。

**draft 結構**：
```
draft_id, version, expires_at, created_by, is_draft:true
district, shift, mode
stations[]      # 已排序，每站含 target_available / station_status
assigned_vehicle, assigned_operator, vehicle_capacity
estimate{ 距離, 交通時間, 作業時間, total_quantity, stop_count, urgency_sum }
note
```

各入口特性：
- **(a)** 未指定 `district` 時用車當前所在區；後台改目標區 → **重新呼叫端點整張重算**。
- **(b)** 找車候選順序：該區閒置 → 鄰近區閒置 → 總站待命；人員池 = 該區閒置 + 總站待命。
  該區與鄰近皆無車時，`note` 會提示改用總站待命車。
- **(c)** 資源優先序：就近閒置的一般調度車 → 才動用預備車 `standby`；可跨區（跨多區時 `district="緊急跨區"`）。
  `POST /emergency/check` **只回建議不派車**（`persist=true` 會被明確拒絕），正式緊急派遣一律走 (c)。

### ⑤ 預覽（人在迴圈）
前端顯示 `estimate` + 路線順序 + 每站目標存量。

**草稿不可就地編輯**：改車／人／區／站＝重新呼叫 build 端點，拿新的 `draft_id` + `version`。
草稿只存在後端記憶體、有 TTL、不佔用人車、不進認領地圖。

### ⑥ 確認派發（唯一落地閘門）
- `POST /dispatch/confirm-trip`，body = `{draft_id, version}`（或**原封不動**的完整 draft，會用 fingerprint 比對）。
- 需 `dispatcher` / `maintainer`；只能確認自己建立的草稿。
- 回傳 `{trip_id, confirmed:true, status:"assigned"}`。
- 舊的 `POST /dispatch/confirm` 已改成同一契約，不再回假成功。

**錯誤語意（前端要有對應 UI）**：

| 狀況 | 碼 |
|---|---|
| 未帶身分 | 401 |
| 無權限 / 不是草稿建立者 / 已被別人確認 | 403 |
| 草稿過期或版本不符、內容被改、人車或站點已被占用、超出車容量、停用站 | 409 |
| 欄位不合法 | 422 |

**冪等**：同一 `draft_id + version` 重送 → 回傳原任務，不會重複派工（確認收據存 SQLite，重啟後仍有效）。

### ⑦ 落地（單一 SQLite 交易，全成或全退）
建立 task（`assigned`、含站級 `route[]`）＋ 佔用車與人（`current_task_id`、回寫 `current_district`）
＋ 站點認領 `claimed_by` ＋ 寫 `audit_logs` ＋ 存確認收據。任一步失敗全部回滾。

### ⑧–⑨ 執行（司機端）
- `GET /dispatch/tasks?operator=&status=`、`GET /dispatch/tasks/{id}`
- `POST /dispatch/tasks/{id}/start`（`assigned` → `in_progress`；首次合法回報也會自動開始）
- `POST /dispatch/tasks/{id}/report` — body `{station_id, actual_available}`
  → 回 `{station, gap, remaining, all_done, status}`

回報約束：只有該任務的 `assigned_operator` 本人可 start／report／return；
`actual_available` 必須是非負整數且不超過站點柱數；已完成或已移除的站不可重報。

### ⑩ 後台中途介入（需 dispatcher）
| 動作 | 端點 | 說明 |
|---|---|---|
| 抽離站 | `DELETE /dispatch/tasks/{id}/stations/{sid}?reason=` | 後端會重跑規則引擎判斷需求是否已消化，回 `resolved` / `back_to_pool` / `needs_notify` |
| 加站 | `POST /dispatch/tasks/{id}/stations` `{station_id, reason}` | **該站必須仍在當前 recommendations**，否則 409「請重新預覽」；只能送 ID，不能夾帶目標或完成狀態 |
| 執行者退回 | `POST /dispatch/tasks/{id}/return` `{reason}` | `in_progress` → `manual_required`；`assigned` → `cancelled`；兩者都釋放人車與認領 |

### ⑪ 自動結案
所有站離開 `pending`（completed 或 removed）→ 後端自動 `complete`，釋放車與人、清除認領，
預備車回復派出前 `standby`。**前端不呼叫「完成任務」。**

### ⑫ 滾動下一趟
`GET /dispatch/next-trip?vehicle_id=&top_k=` → 依「緊急度 − 距離懲罰」的候選清單（仍由後台拍板），
接回入口 (a)。早／晚班不跨區，大夜班可跨區。

---

## 狀態機

**任務** `pending → assigned → in_progress → completed`
- `assigned → assigned`：轉派（僅 `emergency` 型、僅未開始）
- `assigned → cancelled`：退回或來源覆寫到期連動取消（執行中的不受影響）
- `in_progress → retryable → in_progress`、`in_progress → manual_required`
- `in_progress` 不可取消

**站點** `pending（claimed_by）→ completed（actual_available / target_gap）或 removed（removed_resolved）`

---

## 後端對前端的六條紅線

1. **調度指令只能來自後端預覽**：目標存量、數量、路線順序前端一律不自算；加站只能送 `station_id`。
2. **草稿不可就地編輯**：任何修改＝重新 build 取得新 `draft_id/version`。
3. **確認只送 `{draft_id, version}`**：冪等、只能確認自己的、過期要重新預覽。
4. **身分決定動作**：組單／確認／加減站需 dispatcher 或 maintainer；start／report／return 只有本人。
5. **回報值嚴格**：非負整數、不超柱數、終態站不可重報。
6. **結案由後端判定**：站點回報完自動結案並釋放資源。

---

## 實作狀態（2026-09-11 更新）

- **後端**：三入口、草稿、confirm-trip、逐站回報、後台介入、自動結案、認領地圖、next-trip 皆已實作並有 pytest。
  第三批另加上可行性閘門（ADR-123／304）：逐站載量守恆、逐站對應預測視野、班別工時與任務重疊，
  預覽與確認共用同一份驗證。
- **前端**：第二批已建立 `api/httpClient.js`（明確 api／mock 模式、失敗不自動退回 mock、帶 `X-Operator-Id`），
  並接上站點、調度建議、組單預覽、`confirm-trip`、司機任務與逐站回報。第三批再補上：
  - `utils/dispatchGating.js`：`blocking_reasons` 非空時確認鈕失效，逐條顯示原因與下一步（有 node --test 覆蓋）
  - `api/dispatchApi.js` / `api/taskApi.js`：車上台數回報端點（後台就地回報、司機回報自己任務中的車）
  - `RecommendationPanel`：顯示逐站到達時間、該站採用的預測視野、車上載量變化
- **仍為 Mock**：孿生頁（`TwinPage`）、`driverApi.js` 的舊司機頁、`operationsApi.js` 的部分總覽資料，
  以及**最適化 daily-review 完全沒有前端 UI**（ADR-120 做法 Y，係數目前也不影響調度，刻意不做）。

接線時的注意事項：

1. `blocking_reasons` 非空就不要讓使用者按確認——確認回的 409 訊息一定是預覽已顯示過的其中一句。
2. 車輛未回報 `onboard_bikes`（或回報過期）不可確認派工；可在預覽畫面就地回報後重新 build。
3. 修改人車／區／站一律重新 build 取得新 `draft_id`+`version`，不可改草稿再送。
4. 錯誤 UI：401／403／409／422 各有明確語意，409 要能一鍵重新預覽。
