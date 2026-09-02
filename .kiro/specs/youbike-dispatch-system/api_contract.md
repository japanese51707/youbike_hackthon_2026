# API 契約（v3 定案）

> 這是三人協作的「共同約定」。B（模型）和 C（前端）都照這份開發。
> 定案後若要改，需三人同意（因為會影響別人）。
> 最後更新：2026-08-31（v3：對齊 design.md，修正審查 v2 發現的衝突 — 緊急度尺度、target_level、環境係數值域、資料過期標記、任務狀態、身分驗證等）

---

## 題目對映（確保我們做的東西命中要求）

題目原文要求：
> 具備即時數據視覺化與 AI 預測模型；易於理解、可顯示即時租賃站車輛情形之視覺化模板；
> AI 預測或即時反映站點租借需求，優化調度模式；現行機關系統無警示通知功能。

| 題目要求 | 我們的對應功能 | 負責 |
|---------|--------------|------|
| 即時數據視覺化 | 即時熱點地圖（API 3.1 + WebSocket/輪詢） | C |
| 易於理解的視覺化模板 | 顏色分級 + 多維度切換 | C |
| 可切換顯示維度 | 區域類型/地形/行政區（API 3.9） | C + B |
| 時間軸流動 | 時間軸播放 API（API 3.10） | A + C |
| 歷史資料檢視 | 近一週歷史分頁（API 3.2 history） | A + C |
| AI 預測 | 預測模型（Prediction） | B |
| 優化調度 | 規則引擎 + 調度建議 | A |
| **警示通知功能（現行沒有）** | **警示 API，供機關串接（API 3.11）** | A |

---

## 0. 這份文件在幹嘛

它定義三件事：
1. **系統有哪些模組，資料怎麼流動**（架構）
2. **後端提供哪些 API，前端會拿到什麼格式的資料**（給 C 看）
3. **預測模型要吃什麼、吐什麼**（給 B 看）

只要大家遵守這份契約，三個人就能各做各的，最後接得起來。

---

## 1. 整體架構

```
┌──────────────────────────────────────────────────────────────┐
│                          資料源層                              │
│   歷史 Parquet (S3/Athena)  │  TDX 即時 API  │  天氣/活動 API   │
└───────────────────────┬──────────────────────────────────────┘
                        │  （透過 data_source 介面，可抽換）
                        ▼
┌──────────────────────────────────────────────────────────────┐
│                    B 負責：模型因子與權重校準層                │
│   設定各因子（地形/區域/天氣/活動/時間...）與權重               │
│   輸入：站點近期狀態 + 時間 + 外部因子                          │
│   輸出：預測可借車數 + 不確定區間 → 緊急度                       │
│   校準目標：算出的緊急度吻合歷史後續實際狀況                     │
│   對外只暴露：predict() / calc_urgency() 介面                   │
└───────────────────────┬──────────────────────────────────────┘
                        │  預測結果（固定格式）
                        ▼
┌──────────────────────────────────────────────────────────────┐
│                    A 負責：後端核心層                          │
│   1. 規則引擎：預測 → 調度建議（含前瞻窗口緊急度）              │
│   2. 優先級排序：多站同時出問題時排順序                        │
│   3. 任務管理：建立/追蹤調度任務狀態                            │
│   4. API 服務：把結果用 HTTP 傳給前端                          │
└───────────────────────┬──────────────────────────────────────┘
                        │  API（HTTP + JSON）
                        ▼
┌──────────────────────────────────────────────────────────────┐
│                    C 負責：前端顯示層                          │
│   1. 即時熱點地圖（站點狀態顏色，可即時更新）                   │
│   2. 多維度切換（區域類型/地形/行政區）                        │
│   3. 時間軸播放（看整區熱點流動）                              │
│   4. 歷史資料分頁（近一週）                                    │
│   5. 調度建議清單 + 確認按鈕                                   │
│   6. KPI 看板                                                  │
└──────────────────────────────────────────────────────────────┘
                        │
                        ▼
┌──────────────────────────────────────────────────────────────┐
│              警示通知層（預留給機關串接）                       │
│   系統偵測到異常 → 推警示 → 機關系統/LINE/Email                 │
│   （題目明確點名：現行機關系統無此功能）                        │
└──────────────────────────────────────────────────────────────┘
```

### 分工邊界

**A（PM）— 架構與對接**
- 先把整體架構生出來（模組怎麼切、介面長怎樣、資料怎麼流）
- 定義好 API 契約與資料格式，讓 B、C 有依據各自開發
- 把 B 的模型輸出、C 的前端顯示對接起來
- 規則引擎、系統整合、Git 整合（merge）
- 一句話：**建骨架，讓 B 和 C 照架構把血肉填進去，再對接起來**

**B（空間工程師）— 模型因子與權重校準**
- 設定每個模型因子（地形、區域、天氣、活動、時間...）
- 調整各因子的權重
- **校準目標：讓當下算出的數字（緊急度）與歷史資料的後續實際狀況吻合**
  - 例：模型算出某站當下緊急度高 → 回頭看歷史，該站後續確實越來越緊急 → 校準正確
  - 越貼近歷史真實走向越好
- 一句話：**讓模型算出來的緊急度，能準確對應到歷史上後來真的發生的事**

**C（品質技術工程師）— 前端視覺化呈現**
- 設計兩種角色的畫面：
  - **調度員視角**：任務派遣清單、工時、地圖站點熱力圖
  - **後台調派員視角**：整體調度情況、調度人數、站點空/滿率、流動度、緊急度
- 核心目標：**用最清楚、明瞭的視覺化方式呈現**
- 一句話：**把複雜的數據，變成一眼看懂的畫面**

### 開發順序
```
A 先出架構 + API 契約
       ↓
B、C 拿到契約，各自照架構開發（用假資料就能開工，不互相等）
       ↓
A 把三方對接、整合到 Git
```

---

## 2. 共同資料格式（Schema）

這是三方共用的資料結構。所有 API 都用這些格式。

> **關於範例值**：各 Schema 的 JSON 範例是「格式示意」，數字取自不同時刻的情境，**不必跨 Schema 對齊**（例如 KPI 的 empty_rate 與 DispatchOverview 的 empty_stations 是不同快照，Operator 的工時也是舉例）。實作以「欄位名稱、型別、單位」為準，不以範例數字為準。
> **尺度規範（避免混淆）**：緊急度/優先級一律 0~100；usage_rate 0~100（%）；target_level / buffer_level 0~1（比例）；環境係數 0~3（1.0=無影響）。

### 2.1 站點即時狀態 `StationStatus`
```json
{
  "station_id": "500101001",
  "station_name": "捷運南勢角站(4號出口)",
  "district": "中和區",
  "lat": 24.99348,
  "lng": 121.48758,
  "total_docks": 64,
  "available_bikes": 12,
  "available_docks": 52,
  "usage_rate": 18.75,
  "status": "low",
  "area_type": "transit",
  "terrain": "gentle_down",
  "timestamp": "2026-06-02T08:00:00",
  "source_timestamp": "2026-06-02T08:00:00",
  "data_freshness": "live"
}
```

**資料新鮮度（`data_freshness`，對應 NFR-10 降級）：**
| 值 | 意義 | 前端呈現 |
|----|------|---------|
| `live` | 即時資料源正常 | 正常 |
| `stale` | 用最後一次成功資料（第一層降級） | 顯示「資料可能過期」 |
| `historical_fallback` | 用歷史同時段估計（第二層降級） | 顯示「估計值，非即時」 |

`source_timestamp`：資料源實際更新時間（TDX SrcUpdateTime），與 `timestamp`（系統取得時間）分開，用來判斷新鮮度。

**欄位來源說明（正式環境對接 TDX）：**

| 欄位 | 來源 | TDX 對應欄位 |
|------|------|-------------|
| station_id | TDX | `StationUID` |
| station_name | TDX | `StationName` |
| lat / lng | TDX | `StationPosition` |
| total_docks | TDX | `BikesCapacity` |
| available_bikes | TDX | `AvailableRentBikes` |
| available_docks | TDX | `AvailableReturnBikes` |
| timestamp | TDX | `SrcUpdateTime` |
| district | TDX 解析 | 由 `StationAddress` 解析 |
| usage_rate | 我們計算 | available_bikes / total_docks × 100（%，例 12/64×100=18.75） |
| status | 我們計算 | 見下表 |
| area_type | **我們加值** | 政府分區 + POI（TDX 無） |
| terrain | **我們加值** | 高程 API 換算（TDX 無） |

> ✅ 核心欄位全部對應 TDX，正式環境無縫接軌。`area_type` 和 `terrain` 是我們的加值分析，也是差異化。

**`status`（重要：這只是「當前空/滿現況」，不是緊急度！）**

`status` 純粹反映站點當下的空滿狀態，給前端上色用。
**緊急度是另一回事** — 緊急度綜合了預測 + 多因子，在 `DispatchRecommendation` 的 `priority_score`。兩者不可混淆。

| status | 意義 | 建議顏色 |
|--------|------|---------|
| `empty` | 空站（可借=0） | 紅 |
| `low` | 低水位（<15%） | 橘 |
| `normal` | 正常 | 綠 |
| `high` | 高水位（>85%） | 紫 |
| `full` | 滿站（可還=0） | 深紅 |

**`area_type`（區域類型，對應政府都市計畫分區 + 周邊 POI — B 負責分類）**

判定雙來源：
1. 政府都市計畫土地使用分區（法定用途當底）
2. 周邊 500m POI 加權（含地標、熱門景點、運動中心、學校、捷運、商圈等 — 這些都算 POI）

| area_type | 意義 | 典型 POI |
|-----------|------|---------|
| `residential` | 住宅區 | 社區、市場 |
| `commercial` | 商業區 | 百貨、商圈、辦公 |
| `school` | 學區 | 學校、補習班 |
| `transit` | 捷運/交通樞紐 | 捷運站、轉運站、火車站 |
| `leisure` | 休閒/景點 | 河濱、運動中心、觀光地標、熱門景點 |
| `mixed` | 混合型 | 多種並存 |

**`terrain`（地形，方圓 500m 坡度 + 坡向 — B 負責，用高程 API 換算）**

坡度分級（參考自行車坡度耐受度，詳見 parameter_groups.md）+ 坡向組合：

| terrain | 意義 | 影響 |
|---------|------|------|
| `flat` | 平地（坡度 0~3%） | 中性 |
| `gentle_up` | 緩坡上（3~5%） | 略易空 |
| `gentle_down` | 緩坡下（3~5%） | 略易滿 |
| `moderate_up` | 中坡上（5~8%） | 易空 |
| `moderate_down` | 中坡下（5~8%） | 易滿 |
| `steep_up` | 陡坡上（>8%） | 很易空 |
| `steep_down` | 陡坡下（>8%） | 很易滿 |

> 原則：站點在坡上 → 使用者傾向騎下坡離開 → 易空；站點在坡下 → 易滿。

### 2.2 預測結果 `Prediction`（B 產出，A 使用）
```json
{
  "station_id": "500101001",
  "predict_from": "2026-06-02T08:00:00",
  "predict_target_time": "2026-06-02T08:35:00",
  "horizon_minutes": 35,
  "horizon_source": "dispatch",
  "predicted_available": 4.0,
  "lower_bound": 1.0,
  "upper_bound": 8.0
}
```

**欄位說明：**

- `predicted_available`：**預測未來某時刻的可借車數**（不是現況！現況在 StationStatus）。
  - 預測依據：該站歷史「同時段的淨流出/流入」+ 當前狀態 + 各因子
  - 意義：「從現在起算，`horizon_minutes` 之後，這站預計還有幾台」
- `lower_bound` / `upper_bound`：**動態信賴區間**（quantile regression 產出）
  - 由歷史資料學出「這站這時段的可能範圍」，每站每時段的區間寬窄不同
  - 規則引擎用**下界**觸發（預測可失手、判斷不跟著失手）
  - 「實際值落在區間內 = 預測準確」
- `horizon_minutes` + `horizon_source`：**有兩種來源（C-03，重要）**，因為不是每個預測場景都有調度員：
  | horizon_source | 用途 | horizon_minutes 怎麼來 |
  |----------------|------|----------------------|
  | `dispatch` | 派任務時 | 動態 = 調度員當前位置到目標站的交通時間 + 當前任務完成預估（見 parameter_groups §7） |
  | `default` | 警示掃描（每 60 秒全市）、歷史時間軸預存 urgency | 固定值 `config.fleet.響應時間_分鐘`（30 分） |
  - 警示掃描與歷史回填沒有特定調度員，用 `default` 的固定 horizon；只有實際派任務才用 `dispatch` 的動態 horizon
- `predict_from`：預測的起算時間（通常是現在）
- `predict_target_time`：預測的目標時刻（= predict_from + horizon_minutes）

> 已移除原本的 `confidence` 欄位：不確定性已由 lower/upper_bound 區間表達，confidence 多餘。

### 2.3 調度建議 `DispatchRecommendation`（A 產出，C 顯示）
```json
{
  "recommendation_id": "REC-20260602-0800-001",
  "station_id": "500101001",
  "station_name": "捷運南勢角站(4號出口)",
  "district": "中和區",
  "action": "補車",
  "quantity": 15,
  "priority_score": 87.0,
  "priority_level": "high",
  "reason": "預測調度員到達時(35分後)僅剩 2 台，將空站",
  "current_available": 12,
  "predicted_at_arrival": 2,
  "lat": 24.99348,
  "lng": 121.48758
}
```

- `action`：`補車` 或 `取車`
- `priority_score`：**緊急度分數，尺度 0~100**（與 `calc_urgency()` 輸出、`urgency_score`、`config.alert.warning_urgency/critical_urgency` 同一尺度，不可用 0~10）
- `priority_level`：`high` / `medium` / `low`（由 priority_score 對照 config.alert 門檻換算）
- `reason`：人看得懂的中文句子（不是代號）
- `predicted_at_arrival`：預測調度員「到達時」的存量（前瞻窗口的核心）

### 2.4 調度任務 `DispatchTask`（A 管理，C 顯示給調度員）
```json
{
  "task_id": "TASK-20260602-0800-001",
  "task_type": "normal",
  "assigned_operator": "調度員A",
  "task_status": "pending",
  "route": [
    {"seq": 1, "station_id": "A", "station_name": "板橋車站", "action": "取車", "quantity": 15, "lat": 25.014, "lng": 121.462, "stop_status": "pending"},
    {"seq": 2, "station_id": "B", "station_name": "大觀路站", "action": "送車", "quantity": 5, "lat": 24.998, "lng": 121.448, "stop_status": "pending"},
    {"seq": 3, "station_id": "C", "station_name": "縣民大道站", "action": "送車", "quantity": 10, "lat": 25.011, "lng": 121.459, "stop_status": "pending"}
  ],
  "estimated_travel_minutes": 28,
  "estimated_work_minutes": 17,
  "estimated_total_minutes": 45,
  "estimated_distance_km": 8.5,
  "estimated_fuel_cost": 43,
  "route_map_url": "https://www.google.com/maps/dir/?api=1&origin=25.014,121.462&waypoints=24.998,121.448&destination=25.011,121.459&travelmode=driving",
  "assigned_at": "2026-06-02T08:05:00"
}
```

**欄位說明：**

- `task_status`：整個任務的狀態（見下表）— **注意：與 StationStatus 的 `status`（站點空滿）不同，故命名為 task_status 避免混淆**
- `route`：路線清單，每個停靠點含：
  - `seq`：停靠順序
  - `action`：`取車` / `送車`
  - `quantity`：取/送幾台
  - `stop_status`：該停靠點的完成狀態（`pending` / `done` / `skipped`）— **與站點空滿 status 分開命名**
  - `lat` / `lng`：座標（給地圖與導航用）
- `estimated_travel_minutes`：預估交通時間（開車移動）
- `estimated_work_minutes`：預估搬運工時（取/送車的作業時間）
- `estimated_total_minutes`：預估總任務時間（交通 + 搬運）
- `estimated_distance_km`：預估總行駛距離
- `estimated_fuel_cost`：預估交通花費（油錢，依距離 × 油耗率換算，NT$）
- `route_map_url`：**Google Maps 路線導引連結**，調度員點了直接開啟導航（origin → waypoints → destination）

**任務歸屬規則（重要）：**

每個停靠點在前端顯示為**獨立的任務框**，完成後各自按「完成」回報。歸屬邏輯依任務類型不同：

| 任務類型 (`task_type`) | 歸屬 | 能否被轉派 |
|----------------------|------|-----------|
| `normal`（一般任務） | **綁定該調度員**，一旦指派就固定 | ❌ 系統不能再指派給別人 |
| `emergency`（緊急任務） | 指派後、**尚未執行前**，其他調度員也可幫忙 | ✅ 系統排程時會把「未完成的緊急任務」納入計算，可轉派 |

- 一般任務：路線內 5 個站都是這位調度員的責任，逐站完成回報，系統不會中途搶走
- 緊急任務：在還沒開始執行時，若有更適合的調度員 → 可轉派（見 model_architecture.md ③ 動態任務轉派）；一旦開始執行就鎖定

`task_status` 的可能值（整個任務）：
| task_status | 意義 |
|-------------|------|
| `pending` | 待派發（尚未指派給任何調度員） |
| `assigned` | 已指派、尚未開始執行（★動態轉派只在此狀態可轉派） |
| `in_progress` | 執行中（鎖定，不再轉派） |
| `completed` | 完成（已驗證） |
| `retryable` | 失敗可重試 |
| `manual_required` | 需人工介入 |

> 動態轉派條件（對應 model_architecture ③-4）：`task_type == emergency AND task_status == assigned`。
> `pending` 會被重複派發、`in_progress` 已鎖定，都不可轉派，所以必須有 `assigned` 這個中間狀態。

`stop_status` 的可能值（route 內每個停靠點）：
| stop_status | 意義 |
|-------------|------|
| `pending` | 尚未抵達 |
| `done` | 該站取/送完成 |
| `skipped` | 跳過（如該站已由他人處理） |

### 2.5 警示通知 `Alert`（A 產出，供機關/前端接收）
> 題目明確點名：現行機關系統無警示通知功能。這是我們的差異化亮點。

**運作邏輯：**
系統每次收到最新站點狀況（TDX 即時資料）就自動做一次警示確認：
1. 跑預測 + 緊急度計算
2. 若有站點達到警示門檻 → 產生 Alert，即時推到後台
3. 後台人員看到警示 → 可據此調整站別的調派順序（結合 ③ 即時人工調整）
4. 這就是現行機關系統缺少的「主動警示」能力
```json
{
  "alert_id": "ALERT-20260602-0800-001",
  "level": "warning",
  "station_id": "500101001",
  "station_name": "捷運南勢角站(4號出口)",
  "district": "中和區",
  "message": "捷運南勢角站預測30分鐘內將空站，建議立即補車",
  "triggered_at": "2026-06-02T08:00:00",
  "suggested_action": "補車 15 台",
  "acknowledged": false
}
```

`level` 的可能值：
| level | 意義 | 建議前端呈現 |
|-------|------|------------|
| `info` | 提示 | 藍色，不打擾 |
| `warning` | 警告（即將出問題） | 黃色，需注意 |
| `critical` | 緊急（已空/滿或必定發生） | 紅色，需立即行動 |

### 2.6 稽核記錄 `AuditLog`（③ 即時調整 + 調度任務留痕）
```json
{
  "log_id": "LOG-20260602-0800-001",
  "type": "emergency_override",
  "station_id": "500101001",
  "operator": "王主任",
  "action": "緊急覆寫：拉高優先級",
  "reason": "站前突發活動",
  "timestamp": "2026-06-02T08:00:00",
  "expired_at": "2026-06-02T10:00:00",
  "task_duration_minutes": 42
}
```
用途：分析調度員工作狀況、作業時間、後續流動修正、稽核。
（對應 API：`GET /audit/logs`，見 3.14）

### 2.7 活動事件 `Event`（群組 4 — 事件動態影響）
```json
{
  "event_id": "EVT-20261231-001",
  "event_name": "跨年演唱會",
  "location": {"lat": 25.04, "lng": 121.51},
  "expected_attendance": 50000,
  "event_type": "concert",
  "start_time": "2026-12-31T20:00:00",
  "end_time": "2027-01-01T01:00:00",
  "influence_radius_km": 2.0,
  "affected_stations": [
    {"station_id": "...", "distance_km": 0.5, "influence_factor": 1.8}
  ]
}
```
（對應 API：`POST /events`，見 3.15）

### 2.8 調度員 `Operator`（後台調派員 + 調度員視角）
```json
{
  "operator_id": "OP-001",
  "name": "調度員A",
  "status": "on_duty",
  "current_location": {"lat": 25.01, "lng": 121.46},
  "current_task_id": "TASK-20260602-0800-001",
  "task_queue": ["TASK-...001", "TASK-...002", "TASK-...003"],
  "today_stats": {
    "completed_tasks": 6,
    "total_bikes_moved": 142,
    "total_work_minutes": 285,
    "on_duty_since": "2026-06-02T06:00:00"
  }
}
```

`status` 的可能值：
| status | 意義 |
|--------|------|
| `on_duty` | 上班中，可派任務 |
| `busy` | 執行任務中 |
| `resting` | 休息中（法定休息/疲勞降載） |
| `off_duty` | 下班 |

說明：
- `task_queue`：**這位調度員的任務排程佇列**（有前後順序）。緊急狀況可能臨時插入佇列前端，或把未執行的任務抽離轉派給別人（見 2.4 任務歸屬規則）
- `today_stats`：今日工時、完成任務數、搬運總量（後台監控 + 疲勞管理用）

### 2.9 全域調度總覽 `DispatchOverview`（給後台調派員 + 長官看）
```json
{
  "timestamp": "2026-06-02T08:00:00",
  "operators": {
    "on_duty": 12,
    "busy": 9,
    "resting": 2,
    "off_duty": 1
  },
  "today_totals": {
    "completed_tasks": 48,
    "pending_tasks": 15,
    "emergency_tasks": 3,
    "total_bikes_moved": 1120,
    "total_distance_km": 210,
    "estimated_fuel_cost": 1050
  },
  "station_summary": {
    "empty_stations": 45,
    "full_stations": 12,
    "need_dispatch": 15
  }
}
```
用途：後台調派員與長官的宏觀儀表板，一眼看到目前人力、今日成效、站點壓力。

### 2.10 天氣現況 `Weather`（人性化顯示 + 預測因子）
```json
{
  "district": "中和區",
  "condition": "rain",
  "temperature": 24.5,
  "rain_probability": 80,
  "description": "陣雨，建議留意站點需求下降",
  "timestamp": "2026-06-02T08:00:00"
}
```
`condition`：`sunny` / `cloudy` / `rain` / `heavy_rain` / `typhoon`
用途：前端顯示當前天氣（人性化），同時是預測模型的外部因子（群組 3）。

### 2.11 站點參數 `StationParams`（模型三層架構的參數）
```json
{
  "station_id": "500101001",
  "params": {
    "outflow_rate": 1.3,
    "inflow_rate": 0.9,
    "target_level": 0.5,
    "buffer_level": 0.5,
    "nearby_stations": ["500101002", "500101008"],
    "capacity_class": 2
  },
  "param_source": "ai_optimized",
  "override_active": false,
  "conditions": [
    {"param": "outflow_rate", "value": 1.3, "reason": "捷運轉乘站 + 鄰近學區"}
  ],
  "last_optimized": "2026-06-01T03:00:00"
}
```

**參數單位（重要 — 明確定義，避免尺度混淆）：**
- `target_level`：目標借用率，**0~1 比例**（0.5 = 50%）。
- `usage_rate`（在 StationStatus / HistoryPoint）：**0~100 百分比**（18.75 = 18.75%）。
- **對比規則**：前端算「目標 vs 現況」時，`target_level × 100` 才能和 `usage_rate` 同尺度比較（0.5×100=50% vs 18.75%）。兩者尺度不同是刻意的：target_level 是模型參數（習慣 0~1），usage_rate 是顯示值（習慣 %）。程式對接時務必換算，不可直接比 0.5 vs 18.75。
- **`target_usage_rate`（後端已換算好的便利欄位，0~100%）**：`GET /stations/{id}` 與 `GET /stations/{id}/params` 回傳會在 params 外層附上 `target_usage_rate = target_level × 100`，前端可直接與 `usage_rate` 比大小，不必自己換算（避免 I-3 的誤判）。此為顯示便利值，內層 `target_level` 維持 0~1 不變。
- config.yaml 的 `target.預設借用率百分比: 50` = target_level 0.5 的人類可讀版。
- `outflow_rate` / `inflow_rate`：流出/流入率係數
- `buffer_level`：站群緩衝水位（0~1），該站在站群中應保留的緩衝比例
- `nearby_stations`：500m 內鄰近站 ID（FR-13 站點增減時需重算）
- `capacity_class`：容量級距（0~3）

**`param_source`**：`base`（①基礎）/ `ai_optimized`（②AI）
> 注意：**沒有 `emergency_override`**。③ 即時覆寫「不寫參數」（見 model_architecture ③），是否有生效中的覆寫改用獨立的 `override_active: bool` 表示。

說明：`conditions` 說明每個參數背後代表的條件（後台點擊站點時顯示，讓維護人員看懂為何這樣設）。
（對應 API：`GET /stations/{id}/params`，見 3.12）

### 2.12 歷史趨勢點 `HistoryPoint`（時間軸拉動 + 趨勢圖）
```json
{
  "timestamp": "2026-06-02T08:00:00",
  "available_bikes": 12,
  "available_docks": 52,
  "usage_rate": 18.75,
  "urgency_score": 65,
  "status": "low",
  "anomaly_tags": ["dispatch_intervention"]
}
```
說明：**某站在某個歷史時間點的完整狀況快照**。多個 HistoryPoint 串成時間序列，前端拉動時間軸時，就能看到該站在歷史上每個時間點的：
- `available_bikes`：停放/可借車數
- `available_docks`：空車位數
- `usage_rate`：空滿率（借用率）
- `urgency_score`：**該時間點的緊急指數 0~100**（回填歷史，讓使用者看到「當時有多急」）
- `status`：當時的空滿狀態
- `anomaly_tags`：**異常標記**（見下表），讓調閱歷史時一眼看懂「這個異常變化是什麼造成的」

`anomaly_tags` 可能的值（可多個）：
| 標籤 | 意義 | 對模型的作用 |
|------|------|------------|
| `dispatch_intervention` | 調度介入（短時間空滿率異常跳變） | 訓練/最適化時排除 |
| `event` | 活動舉辦影響 | 排除一般模型，但保留供同類事件預估 |
| `holiday` | 假日/連假 | 用假日模型，不混入平日 |
| `school_vacation` | 寒暑假 | 學區站特殊模式 |
| `weather_extreme` | 極端天氣（颱風/豪雨） | 排除，但保留供同類天氣預估 |
| `station_change` | 站點改造（容量變動） | 觸發重新學習 |
| `data_error` | 資料異常（缺值/跳動） | 直接排除 |
| `normal` | 正常（無異常，可留空或不帶此欄） | — |

**雙重用途（呼應 parameter_groups.md 群組 4 的異常標籤概念）：**
1. **歷史回顧**：前端時間軸上，異常點可用特殊圖示標示，滑鼠移過去顯示「此處為調度介入 / 活動影響」，讓使用者秒懂當時發生什麼
2. **模型排除 + 情境預估**：AI 最適化時排除這些異常點避免學壞；但保留下來，未來遇到同類情境（如颱風、活動）時可調出估算

用途：
- `GET /stations/{id}` 的 `history` 就是 `HistoryPoint[]`
- `GET /stations/timeline` 的每個 frame 內的站點狀態也用這格式
- 前端時間軸拉動 → 逐點顯示該站歷史狀況（含異常標記）

---

## 3. API 端點清單（A 提供，C 呼叫）

Base URL: `http://localhost:8000/api/v1`（開發）；部署時換成雲端網址

### 為什麼前端不直接讀資料庫？（架構觀念）

API 不是「多一層資料項」，而是資料庫和前端之間的**翻譯官 + 保護殼**。

```
資料庫層（原始資料 + 計算結果）
      ↓
  API 層（統一介面，決定給前端什麼格式）← 保護殼
      ↓
   前端（只依賴 API 格式，不直接碰資料庫）
```

API 背後分兩種情況：
- **薄 API（情境 A）**：前端要的就是原始資料 → API 幾乎只是「讀 DB、轉格式、回傳」
- **計算 API（情境 B）**：前端要的是加工值（緊急度、預測、熱點聚合）→ 後端先算好（可能存進「計算結果庫」），API 再回傳

為什麼一定要透過 API，不直接開放 DB：
1. **格式一致**：加工邏輯（顏色、緊急度）在後端統一做，避免多個前端頁面各算各的
2. **安全**：不暴露資料庫結構
3. **解耦**：DB 欄位改了，只要 API 格式不變，前端不受影響

### 3.1 取得所有站點即時狀態
```
GET /stations
```
回傳：`StationStatus[]`（陣列）
用途：前端畫地圖用

參數（可選）：
- `?district=中和區` — 只取某區
- `?status=empty,low` — 只取特定狀態

### 3.2 取得單一站點詳情（含預測）
```
GET /stations/{station_id}?history_range=7d
```
回傳：
```json
{
  "current": { StationStatus },
  "prediction": { Prediction },
  "params": { StationParams },
  "history": [ { HistoryPoint }, ... ]   // 歷史趨勢，預設近一週
}
```
參數 `history_range`：`24h` / `7d`（預設，近一週）— 呼應資料保留策略，不撈全部歷史

### 3.3 取得調度建議清單
```
GET /dispatch/recommendations
```
回傳：`DispatchRecommendation[]`（已按優先級排序）
用途：前端顯示「現在該調度哪些站」

參數（可選）：
- `?limit=15` — 最多回傳幾筆
- `?priority=high` — 只取高優先

### 3.4 確認調度建議（閘門：預覽→確認）
```
Header: X-Operator-Id: OP-002          # C-08：需 dispatcher/主管角色
POST /dispatch/confirm
Body: { "recommendation_ids": ["REC-...001", "REC-...002"] }
```
回傳：建立的 `DispatchTask[]`
用途：主管在前端按「確認派發」後呼叫。**這是人在迴圈的唯一閘門**。
> 身分驗證（NFR-8，C-08）：後端驗證此人角色為 `dispatcher`/`maintainer` 才可派發。前端隱藏按鈕不算保護——任何人都能直接打此端點，所以權限一定在後端驗。

### 3.5 取得任務清單
```
GET /dispatch/tasks
```
回傳：`DispatchTask[]`

### 3.6 回報任務狀態（調度員用）
```
Header: X-Operator-Id: OP-001          # C-08 身分驗證
POST /dispatch/tasks/{task_id}/report
Body: { "operator_id": "OP-001", "status": "completed", "note": "已補車，2 台故障回報" }
```
> 身分驗證（NFR-8）：後端驗證 `X-Operator-Id` 對應的角色，且該 operator_id 必須是此任務的 `assigned_operator`（調度員只能回報自己的任務）。
回傳：更新後的 `DispatchTask`
用途：調度員完成任務後回報，系統重新計算下一個任務

### 3.7 取得 KPI
```
GET /kpi
```
回傳：
```json
{
  "empty_rate": 5.66,
  "full_rate": 1.93,
  "avg_usage_rate": 45.2,
  "total_stations": 1583,
  "stations_need_dispatch": 15,
  "timestamp": "2026-06-02T08:00:00"
}
```

### 3.8 模擬重放（Demo 用）
```
GET /simulation/replay?date=2026-06-02
```
回傳：Before/After 對比數字
用途：Demo 展示成效

### 3.9 多維度熱點資料（即時視覺化，題目要求）
```
GET /stations/heatmap?dimension=area_type
```
參數 `dimension`：`status`（預設）/ `area_type` / `terrain` / `district`
回傳：站點清單 + 該維度的分組聚合
```json
{
  "dimension": "area_type",
  "groups": {
    "residential": { "count": 420, "avg_usage": 38.2, "empty_count": 45 },
    "commercial": { "count": 310, "avg_usage": 55.1, "empty_count": 12 },
    "transit": { "count": 180, "avg_usage": 62.3, "empty_count": 38 }
  },
  "stations": [ { StationStatus }, ... ]
}
```
用途：前端切換顯示維度（住宅/商業/地形），畫不同的熱點分佈

### 3.10 時間軸播放資料（題目要求：看整區熱點流動）
```
GET /stations/timeline?district=中和區&date=2026-06-02&interval=30
```
回傳：該區一整天、每 30 分鐘的站點狀態快照序列（每站每時間點用 HistoryPoint 格式）
```json
{
  "district": "中和區",
  "date": "2026-06-02",
  "frames": [
    {
      "time": "00:00",
      "stations": [
        {"station_id": "500101001", "available_bikes": 12, "available_docks": 52, "usage_rate": 18.75, "urgency_score": 65, "status": "low"}
      ]
    },
    { "time": "00:30", "stations": [ ... ] }
  ]
}
```
每個站點狀態即 `HistoryPoint`（含 station_id）。
用途：前端拖曳時間軸，看整區站點的停放數/空車數/空滿率/緊急指數怎麼隨時間流動。

### 3.11 警示通知 API（題目明確要求：現行機關系統沒有）★差異化亮點

**取得目前警示：**
```
GET /alerts?level=warning,critical&acknowledged=false
```
回傳：`Alert[]`

**確認警示（標記已讀）：**
```
POST /alerts/{alert_id}/acknowledge
```

**訂閱警示推播（給機關串接 — 預留正式上線用）：**
```
POST /alerts/subscribe
Body: {
  "callback_url": "https://機關系統/webhook",
  "levels": ["warning", "critical"],
  "districts": ["中和區", "板橋區"]
}
```
用途：機關系統登記一個接收網址，之後系統偵測到警示，就主動 POST 到這個網址。
正式上線後，機關不用一直來查，系統會主動推。這就是「現行沒有的警示通知功能」。

**即時警示串流（前端用 — 儀表板即時跳警示）：**
```
GET /alerts/stream    (Server-Sent Events / WebSocket)
```
用途：前端訂閱後，有新警示會即時推到儀表板，不用一直輪詢。

---

### 3.12 模型參數三層架構 API（詳見 model_architecture.md）

**取得站點參數（後台檢視畫面用）：**
```
GET /stations/{station_id}/params
```
回傳：
```json
（回傳格式同 Schema 2.11 `StationParams`）
```json
{
  "station_id": "500101001",
  "params": {
    "outflow_rate": 1.3,
    "inflow_rate": 0.9,
    "target_level": 0.5,
    "buffer_level": 0.5,
    "nearby_stations": ["500101002", "500101008"],
    "capacity_class": 2
  },
  "param_source": "ai_optimized",
  "override_active": false,
  "conditions": [
    {"param": "outflow_rate", "value": 1.3, "reason": "捷運轉乘站 + 鄰近學區"}
  ],
  "last_optimized": "2026-06-01T03:00:00"
}
```
`param_source`：`base`（①基礎）/ `ai_optimized`（②AI）。③ 覆寫不寫參數，用 `override_active` 表示。

---

### 3.20 ③ 即時緊急覆寫（調度員/主管用，與 ②最適化分開，路由檔 api/overrides.py）

```
POST /stations/{station_id}/emergency-override
Body: {
  "reason": "站前突發活動，大量借車",
  "expire_minutes": 120,
  "operator": "王主任"
}
```
效果：該站在 **dispatcher 排序時被當「最前綴」排到最優先**（不竄改 urgency 分數，見 model_architecture ③ C-02）；任務完成或時效到期後自動恢復。
系統記錄稽核痕跡（誰、何時、原因）。

**覆寫到期 vs 任務衝突（規則已定案）**：覆寫「到期」或「被手動取消」時，由該覆寫產生、且仍在 `pending`/`assigned`（未開始）的任務**一併取消**（狀態轉 `cancelled`）；`in_progress`（執行中）的任務**不受影響**（保護正在路上的調度員）。
- 依據：任務帶 `source_override_station_id` 欄位，標記「由哪個覆寫產生」，作為連動取消的判斷依據。
- 為什麼要取消：否則會出現「系統已不認為這站緊急，調度員手上卻還有一張因它產生的任務」的矛盾。
- 稽核：覆寫本身記 `emergency_override`（設定/到期/取消），連動取消的任務另記 `task_transfer`（記錄流向與原因），整個處理過程完整留痕。
- 實作：`override_service` 於到期(`_purge_expired`)/取消(`cancel`)時呼叫 `task_manager.cancel_by_override_source()`。`in_progress` 因狀態機不允許 `→cancelled` 而自然被保護。

**取消/查詢即時覆寫：**
```
DELETE /stations/{station_id}/emergency-override
GET /overrides/active          # 目前所有生效中的緊急覆寫
```

**② 每日 AI 最適化 — 取得待確認摘要（後台審核畫面用）：**
```
GET /optimization/daily-review
```
回傳：
```json
{
  "review_date": "2026-06-02",
  "lookback_days": 3,
  "excluded_abnormal_days": ["2026-05-31"],
  "summary": {
    "total_stations_adjusted": 156,
    "avg_change_pct": 3.2,
    "significant_count": 8
  },
  "station_changes": [
    {
      "station_id": "500101001",
      "station_name": "捷運南勢角站",
      "is_significant": true,
      "params": [
        {
          "param": "outflow_rate",
          "old": 1.20, "new": 1.35, "change_pct": 12.5,
          "reason": "近3日早高峰借車量持續高於預測"
        },
        {
          "param": "target_level",
          "old": 0.50, "new": 0.55, "change_pct": 10.0,
          "reason": "配合流出率上調"
        }
      ]
    }
  ],
  "status": "pending_approval"
}
```

說明：
- `summary`：總覽（調整總站數、平均調幅、重大調整站數）
- `station_changes`：**逐站的參數對比**（舊值 vs 新值 vs 調幅 vs 原因），前端可列表呈現讓後台人員逐站看
- `is_significant`：標記調幅較大的站（前端可高亮）

**② 逐站二次定義（後台人員可對個別站別再調整）：**
```
POST /optimization/daily-review/station/{station_id}
Body: {
  "decision": "re_adjust",     // re_adjust=再調整 / keep=不修改(維持舊值) / accept=接受AI建議
  "manual_params": {           // 當 decision=re_adjust 時，人工指定的參數值
    "outflow_rate": 1.30
  },
  "note": "AI 調太多，手動收斂一點"
}
```
用途：後台人員檢視每一站的 AI 調整後，可以：
- `accept`：接受 AI 建議
- `keep`：不修改，維持原本舊值
- `re_adjust`：人工再定義新值

**② 確認套用（全部）：**
```
POST /optimization/daily-review/approve   # 套用（含逐站二次定義的結果）
POST /optimization/daily-review/reject     # 全部退回，維持原參數
```

**② 參數版本回溯：**
```
GET /stations/{station_id}/params/history      # 參數變更歷史
POST /stations/{station_id}/params/rollback     # 回到前一版
Body: { "target_version": "2026-06-01", "reason": "..." }
```

**設定 AI 最適化回看天數（後台設定）：**
```
PUT /optimization/config
Body: { "lookback_days": 3 }
```

---

### 3.13 調度員位置導向任務分配（③ 的排序邏輯）

**調度員回報完成後，取得下一個任務（結合位置）：**
```
Header: X-Operator-Id: OP-001
POST /dispatch/tasks/{task_id}/report
Body: { "operator_id": "OP-001", "status": "completed", "operator_location": {"lat": 25.01, "lng": 121.46} }
```
回傳：下一個任務（系統依調度員當前位置 + 最優先站 + 急迫度綜合排序）
```json
{
  "next_task": { DispatchTask },
  "assignment_reason": "距您 1.2km 的中和國小站為最優先（覆寫中），同區另有審計大樓站一併安排"
}
```

### 3.14 稽核記錄（對應 Schema 2.6）
```
GET /audit/logs?type=emergency_override&date=2026-06-02
```
回傳：`AuditLog[]`
用途：分析調度員工作狀況、作業時間、後續流動修正、稽核。

### 3.15 活動事件（對應 Schema 2.7）
```
POST /events
Body: { event_name, location, expected_attendance, event_type, start_time, end_time }
```
後端呼叫 `prediction/event_impact.py` 的 `compute_event_impact()`：換算影響半徑、找出範圍內站點、計算各站影響度（供需比）。若有歷史同類活動資料，一併調出估算。
```
GET /events                # 取得目前生效中的活動事件
DELETE /events/{event_id}   # 移除活動
```

### 3.16 調度員清單與狀態（對應 Schema 2.8）
```
GET /operators                    # 所有調度員清單+狀態+今日統計
GET /operators/{operator_id}      # 單一調度員詳情（含任務佇列）
GET /operators/{operator_id}/stream   # SSE：只推該調度員工作範圍內的即時更新（NFR-9）
```
> `stream` 對應 NFR-9 的「現場調度員即時、只推工作範圍內」——不推全市，只推這位調度員負責範圍的站點變化，降低頻寬與延遲。若 SSE 實作不及，降級為輪詢並註明。
回傳：`Operator[]` / `Operator`
用途：後台調派員看誰在線、誰忙、誰在休息、各自工時與搬運量；調度員看自己的任務佇列順序。

### 3.17 全域調度總覽（對應 Schema 2.9）
```
GET /dispatch/overview
```
回傳：`DispatchOverview`
用途：後台調派員與長官的宏觀儀表板。

### 3.18 天氣現況（對應 Schema 2.10）
```
GET /weather?district=中和區
```
回傳：`Weather`
用途：前端人性化顯示；也是預測模型的外部因子來源。

### 3.19 站點動態管理（新增/刪除站別，對應 FR-13）

**新增站別：**
```
POST /stations
Body: {
  "station_name": "新站名",
  "lat": 25.01, "lng": 121.46,
  "total_docks": 30,
  "district": "中和區"
}
```
系統自動：
1. 批次換算地理參數（terrain / area_type / nearby_stations）
2. 冷啟動：套用當前模型 + 鄰近類似站參數當起始值
3. **重算受影響鄰近站的站群關係**（動態連動）
回傳：新站的 `StationStatus` + `StationParams`

**刪除/停用站別：**
```
DELETE /stations/{station_id}
```
系統自動移除該站參數組，並**重算鄰近站的站群關係**。

> 動態連動：新增/刪除只重算受影響範圍內的站，不需全市重算。

---

## 4. B 的模型介面（給 B 的約定）

### 核心概念：門口固定，門內自由

B 的模型是一個「黑盒子」。**大家只約定「門口」（輸入/輸出格式），門後面怎麼裝潢是 B 的事。**

```
             B 的模組（黑盒子）
        ┌──────────────────────────┐
 輸入   →│  門內是 B 的 know-how：   │→  輸出
（契約固定）│  • 用什麼演算法           │ （契約固定）
         │  • 特徵怎麼設計           │
         │  • 各因子權重怎麼調       │
         │  • 怎麼校準貼近歷史       │
         └──────────────────────────┘
   ↑ 兩端是契約（不可變）      ↑ 中間全是 B 的自由
```

- **契約固定的**：`predict()` 吃什麼、吐什麼（下方定義）
- **B 的自由 / know-how**：演算法選型（LightGBM / XGBoost / 任意）、特徵工程、權重調校、校準方法
- 只要輸入輸出格式不變，B 內部隨時可以改演算法、調權重，**A 和 C 完全不受影響，不用改任何程式**

### 唯一的硬性要求

雖然內部是黑盒子，但**輸出格式**有一條不可妥協的規定：
- **必須輸出不確定區間**（`lower_bound` / `upper_bound`），不能只給點估計
- 因為規則引擎要吃「區間下界」觸發（預測可失手、判斷不跟著失手）
- 「怎麼算出這個區間」是 B 的自由，「一定要有這個區間」是契約要求

### 介面定義

```python
def predict(
    station_id: str,
    current_status: dict,      # 當前 StationStatus
    history: list,             # 近期歷史（近 1~2 週）
    horizon_minutes: int,      # 要預測多久之後
    horizon_source: str,       # "dispatch"（動態）或 "default"（固定 30 分，警示/歷史用）
    external_factors: dict,    # 天氣、假日、事件等
) -> dict:
    """
    回傳核心三欄（B 只需保證這三欄）：
    {
        "predicted_available": float,   # 預測未來某時刻的可借車數
        "lower_bound": float,           # 動態信賴區間下界（必要）
        "upper_bound": float,           # 動態信賴區間上界（必要）
    }
    → 其餘 Prediction 欄位（station_id / predict_from / predict_target_time /
      horizon_minutes / horizon_source）由 A 在組裝 API 回應時補齊。
      B 不需要重複產生這些時間/識別欄位。
    """


def calc_urgency(
    prediction: dict,          # predict() 的輸出
    station_meta: dict,        # 站點資訊（容量、鄰近站、重要性...）
    arrival_minutes: int,      # 調度到達時間
) -> float:
    """
    回傳緊急度分數 0~100（怎麼算是 B 的 know-how；校準目標是吻合歷史後續實際狀況）

    注意（C-02）：本函式「不」處理 ③ 即時人工覆寫。
    覆寫是控制平面（A）的事，由 dispatcher 排序時當最前綴，不進 urgency。
    """
```

### 為什麼這樣設計對團隊好

1. **B 可以獨立埋頭優化模型**，不用管 A、C 在幹嘛
2. **A、C 不用懂模型**，只要知道餵什麼、拿什麼
3. **模型是團隊的 know-how 資產**，比賽後可持續進化，介面不變系統就不用重寫
4. **Demo 賣點**：「預測引擎可抽換，現在用 LightGBM，未來換更強的模型，系統其他部分完全不動」

---

## 5. C 的前端約定（給 C 的約定）

C 需要做的畫面（對應題目要求）：
1. **即時熱點地圖** — 呼叫 `/stations`，用顏色畫站點狀態，定時更新（或用 `/alerts/stream` 即時推）
2. **維度切換** — 呼叫 `/stations/heatmap?dimension=...`，讓使用者切換住宅/商業/地形視角
3. **時間軸播放** — 呼叫 `/stations/timeline`，做可拖曳的時間動畫
4. **歷史分頁** — 呼叫 `/stations/{id}?history_range=7d` 拿 `history`（HistoryPoint[]），畫趨勢圖
5. **調度建議清單 + 確認按鈕** — 呼叫 `/dispatch/recommendations` 和 `/dispatch/confirm`
6. **KPI 看板** — 呼叫 `/kpi`
7. **警示顯示** — 訂閱 `/alerts/stream`，有警示就在畫面上跳出

開發要點：
- **開發時可以先用假資料（mock）**，不用等 A 的後端做完
- 我（A）會提供 `mock_data.json`，含所有格式的假資料
- React + Vite + 地圖用 Leaflet + 圖表用 ECharts（建議）

---

## 6. 資料源可抽換設計

後端有一個 `data_source` 介面，可切換四種來源：

```python
class DataSource:
    def get_current_status(self) -> list[StationStatus]: ...
    def get_history(self, station_id, days) -> list: ...

# 四種實作：
# - MockDataSource（假資料，開發/測試用）
# - HistoricalDataSource（讀 Parquet/Athena）
# - TDXDataSource（接 TDX 即時 API）
# - YouBikeOfficialDataSource（接 YouBike 公司官方即時源，現場可能用）
```

現場 Demo 時，在 `config.yaml` 改設定（物件格式，與 design §7 / config.yaml 一致）：
```yaml
data_source:
  mode: "tdx"              # mock / historical / tdx / youbike_official
  tdx_api_key: "..."       # 若用 tdx
  youbike_official_url: "" # 若用 youbike 官方源
```

---

## 7. API 端點總覽（快速查表）

### 站點與視覺化
| 編號 | 端點 | 用途 | 題目對應 | 使用者 |
|------|------|------|---------|--------|
| 3.1 | `GET /stations` | 所有站點即時狀態 | 即時視覺化 | C |
| 3.2 | `GET /stations/{id}` | 單站詳情+預測+歷史 | 歷史檢視 | C |
| 3.9 | `GET /stations/heatmap` | 多維度熱點聚合 | 維度切換 | C |
| 3.10 | `GET /stations/timeline` | 時間軸序列 | 熱點流動 | C |

### 調度
| 編號 | 端點 | 用途 | 題目對應 | 使用者 |
|------|------|------|---------|--------|
| 3.3 | `GET /dispatch/recommendations` | 調度建議清單 | 優化調度 | C |
| 3.4 | `POST /dispatch/confirm` | 確認派發（閘門） | 人在迴圈 | C |
| 3.5 | `GET /dispatch/tasks` | 任務清單 | 調度管理 | C |
| 3.6 / 3.13 | `POST /dispatch/tasks/{id}/report` | 回報任務+取下一任務（位置導向） | 調度管理 | 調度員 |

### KPI 與成效
| 編號 | 端點 | 用途 | 題目對應 | 使用者 |
|------|------|------|---------|--------|
| 3.7 | `GET /kpi` | KPI 指標 | 成效呈現 | C |
| 3.8 | `GET /simulation/replay` | Before/After | Demo 成效 | C |

### 警示通知 ★差異化亮點
| 編號 | 端點 | 用途 | 題目對應 | 使用者 |
|------|------|------|---------|--------|
| 3.11 | `GET /alerts` | 取得警示 | ★警示通知 | C/機關 |
| 3.11 | `POST /alerts/{id}/acknowledge` | 確認警示已讀 | ★警示通知 | C |
| 3.11 | `POST /alerts/subscribe` | 訂閱警示推播（機關串接） | ★警示通知 | 機關 |
| 3.11 | `GET /alerts/stream` | 即時警示串流 | ★警示通知 | C |

### 模型參數三層架構
| 編號 | 端點 | 用途 | 層 | 使用者 |
|------|------|------|-----|--------|
| 3.12 | `GET /stations/{id}/params` | 檢視站點參數+背後條件 | 檢視 | 後台 |
| 3.12 | `POST /stations/{id}/emergency-override` | 即時緊急覆寫 | ③ | 調度員/主管 |
| 3.12 | `DELETE /stations/{id}/emergency-override` | 取消緊急覆寫 | ③ | 後台 |
| 3.12 | `GET /overrides/active` | 目前生效中的覆寫 | ③ | 後台 |
| 3.12 | `GET /optimization/daily-review` | 每日AI最適化摘要（逐站對比） | ② | 後台 |
| 3.12 | `POST /optimization/daily-review/station/{id}` | 逐站二次定義 | ② | 後台 |
| 3.12 | `POST /optimization/daily-review/approve` | 套用最適化 | ② | 後台 |
| 3.12 | `POST /optimization/daily-review/reject` | 退回最適化 | ② | 後台 |
| 3.12 | `GET /stations/{id}/params/history` | 參數變更歷史 | ② | 後台 |
| 3.12 | `POST /stations/{id}/params/rollback` | 參數回溯 | ② | 後台 |
| 3.12 | `PUT /optimization/config` | 設定回看天數 | ② | 後台 |

### 稽核與事件
| 編號 | 端點 | 用途 | 題目對應 | 使用者 |
|------|------|------|---------|--------|
| 3.14 | `GET /audit/logs` | 稽核記錄 | 可稽核 | 後台 |
| 3.15 | `POST /events` | 新增活動事件 | 事件影響 | 後台 |
| 3.15 | `GET /events` | 生效中的活動 | 事件影響 | 後台/C |
| 3.15 | `DELETE /events/{id}` | 移除活動 | 事件影響 | 後台 |

### 調度員、總覽與天氣
| 編號 | 端點 | 用途 | 題目對應 | 使用者 |
|------|------|------|---------|--------|
| 3.16 | `GET /operators` | 調度員清單+狀態+統計 | 調度管理 | 後台 |
| 3.16 | `GET /operators/{id}` | 單一調度員（含任務佇列） | 調度管理 | 後台/調度員 |
| 3.17 | `GET /dispatch/overview` | 全域調度總覽 | 宏觀監控 | 後台/長官 |
| 3.18 | `GET /weather` | 天氣現況 | 人性化+預測因子 | C |
| 3.19 | `POST /stations` | 新增站別（冷啟動+連動） | 站點動態管理 | 後台 |
| 3.19 | `DELETE /stations/{id}` | 刪除站別（+連動重算） | 站點動態管理 | 後台 |

---

## 8. 待確認事項（已定案）

1. ✅ **API 端點與前端資料** — 已補齊調度員、全域總覽、天氣、參數、歷史點
2. ✅ **資料格式欄位** — 12 個 Schema，含異常標記，涵蓋完整資料流
3. ✅ **station_id** — **跟 TDX 走**（用 `StationUID`），可額外自訂欄位，但基本定義以 TDX 為準
4. ✅ **前瞻窗口（調度到達時間）** — = 調度員目前位置到目的地的交通時間 + 目前任務需完成的預估時間
5. ✅ **動態目標水位** — **納入 API**（在 StationParams 的 `target_level`，前端可顯示「目標 vs 現況」）
6. ✅ **area_type 分類** — 主要照政府地域分類對照；另外標記主要人潮點（熱門景點、運動中心等）為 POI，設定各 POI 對人流的影響程度
7. ✅ **terrain 資料來源** — 用現成高程資料，**非手動標記**。兩個來源可選：
   - **內政部國土測繪中心 DEM（20m 網格數值地形模型）** — 政府開放資料，全台高程
   - **Google Elevation API** — 傳經緯度回高程，可批次查，開發快
   - 做法：查站點與周邊 500m 高程 → 算坡度 + 坡向 → 換算 terrain
8. ✅ **時間軸播放** — **參考歷史資料，不用即時計算**。只要歷史資料（含 urgency_score、anomaly_tags）預先算好存好，前端直接讀。
9. ✅ **警示推播** — Demo 時先在**我們自己的前端顯示**，跟評審說明此功能；並提供 `POST /alerts/subscribe` API，未來要對接政府系統時，系統可主動 POST 警示到需求端。

---

## 9. terrain 資料來源補充（第 7 點細節）

| 來源 | 優點 | 適用 |
|------|------|------|
| 內政部國土測繪中心 20m DEM | 政府開放、免費、全台涵蓋 | 正式/接地氣 |
| Google Elevation API | 傳經緯度即回高程、可批次、開發快 | 開發期快速實作 |

實作：對 1583 站批次查高程 → 用站點與周邊點的高程差算坡度（%）→ 依 parameter_groups.md 的坡度分級 + 坡向 → 寫入 terrain 參數（批次一次算完，非手動）。
