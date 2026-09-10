# 前端 API 資料格式速查表

> 給前端夥伴：所有端點回傳什麼資料、欄位意義、目前接線狀態。
> 共同規則：端點前綴 `/api/v1`｜需身分的帶標頭 `X-Operator-Id`｜回傳皆 JSON。
> 狀態圖例：🟢 已接真實　🟡 部分真實/部分 mock　🔴 mock 骨架（欄位已定、值待接）

---

## 1. 站點 Stations

| 端點 | 方法 | 狀態 | 回傳 | 用途 |
|---|---|---|---|---|
| `/stations` | GET | 🟢 | 站點陣列 | 地圖畫 1600 站 |
| `/stations/{id}` | GET | 🟢 | 單站詳情（current/history/prediction 皆真實） | 單站面板 |
| `/stations/{id}/params` | GET | 🟢 | 站點參數（三層疊加生效版） | 參數檢視 |
| `/stations/{id}/params/history` | GET | 🟢 | 參數版本歷史（新→舊） | 參數回溯 |
| `/stations/{id}/params/rollback` | POST | 🟢 | 回溯結果（需 maintainer） | 參數回溯 |
| `/stations/heatmap` | GET | 🔴 | 熱點聚合 | 多維熱力圖 |
| `/stations/timeline` | GET | 🔴 | 時間序列 | 時間軸播放 |
| `/stations` | POST | 🔴 | 新站建立結果 | 新增站別 |
| `/stations/{id}` | DELETE | 🔴 | 移除結果 | 刪除站別 |

**`GET /stations` 每站欄位：**

| 欄位 | 型別 | 意義 |
|---|---|---|
| `station_id` | str | 站點代碼 |
| `station_name` | str | 站名 |
| `district` | str | 行政區 |
| `lat` / `lng` | float | 緯度 / 經度 |
| `total_docks` | int | **總柱數** |
| `available_bikes` | int | 可借車數（柱上現有車） |
| `available_docks` | int | 可還空位數 |
| `usage_rate` | float | 借用率 %（0~100） |
| `status` | str | `empty`（空）/ `full`（滿）/ `low` / `high` / `normal` |
| `service_available` | bool | 是否營運中 |
| `data_freshness` | str | `realtime` / `historical`（降級時標記來源） |

**`GET /stations/{id}` 結構：** `{ current, history[], prediction, params }`
- `current`：同上單站格式
- `history[]`：歷史快照陣列（同格式，時間序）
- `prediction`：🟢 真實 LightGBM，`{source, horizons[4視野 P10/P50/P90]}`（見 §8.7；降級時 source=mock_fallback）
- `params`：站點參數 + `target_usage_rate`（目標水位換算成 0~100%）

---

## 2. 調度建議 Dispatch（規則引擎）

| 端點 | 方法 | 狀態 | 回傳 | 用途 |
|---|---|---|---|---|
| `/dispatch/recommendations` | GET | 🟢 | 已排序建議陣列 | 需調度清單（組單起點） |
| `/dispatch/tasks` | GET | 🟢 | 任務陣列（接 task_manager，可篩 status/operator） | 任務看板 |
| `/dispatch/tasks/{id}` | GET | 🟢 | 單一任務詳情（含站級 route） | 任務詳情 |
| `/dispatch/build/from-vehicle` | POST | 🟢 | 以車組草稿（body: vehicle_id/operator_id/district?） | 組單入口 a |
| `/dispatch/build/from-station` | POST | 🟢 | 以站組草稿 + vehicle_candidates（body: station_id...） | 組單入口 b |
| `/dispatch/build/emergency` | POST | 🟢 | 緊急組草稿 + resource_suggestion（body: station_ids[]） | 組單入口 c |
| `/dispatch/confirm-trip` | POST | 🟢 | 草稿落地（需 dispatcher，body: draft） | 確認派發閘門 |
| `/dispatch/confirm` | POST | 🔴 | （舊）確認結果 | 舊派發（改用 confirm-trip） |
| `/dispatch/tasks/{id}/report` | POST | 🟢 | 逐站回報（body: station_id/actual_available） | 逐站回報 |
| `/dispatch/tasks/{id}/stations/{sid}` | DELETE | 🟢 | 後台抽離個別站（需 dispatcher） | 後台介入 |
| `/dispatch/tasks/{id}/stations` | POST | 🟢 | 後台增加個別站（需 dispatcher） | 後台介入 |
| `/dispatch/tasks/{id}/return` | POST | 🟢 | 執行者退回（附原因） | 退回任務 |
| `/dispatch/claim-map` | GET | 🟢 | 站點認領地圖（防重複接） | 認領地圖 |
| `/dispatch/next-trip?vehicle_id=` | GET | 🟢 | 下一趟建議（緊急度-距離評分） | 滾動排程 |
| `/dispatch/overview` | GET | 🔴 | 全域總覽 | 長官儀表板 |

**`GET /dispatch/recommendations` 每筆欄位（查詢參數 `limit` / `priority`）：**

| 欄位 | 型別 | 意義 |
|---|---|---|
| `station_id` / `station_name` / `district` | str | 站點 |
| `action` | str | `補車` / `取車` |
| `quantity` | int | 建議增減量（輔助） |
| `target_available` | int | **補到/抽到幾台（目標存量，主指令）** |
| `urgency_tier` | str | `censored`(最急截斷) / `warning`(警示) / `normal` |
| `priority_score` | float | 緊急度分數 0~100 |
| `priority_level` | str | `high`(≥70) / `medium`(≥40) / `low` |
| `breach_horizon_min` | int/null | 最早穿透邊界的視野（分鐘），null=未穿透 |
| `arrival_by_horizon` | obj | `{"30":x,"60":x,"90":x,"120":x}` 各視野到達存量（趨勢圖） |
| `current_available` | int | 現況可借 |
| `reason` | str | 中文原因（可解釋） |
| `basis` | str | 判斷依據（截斷訊號/區間下界/保底門檻/降級） |
| `override_active` | bool | 是否被③即時覆寫（排序置頂） |
| `lat` / `lng` | float | 座標 |

---

## 3. 警示 Alerts

| 端點 | 方法 | 狀態 | 回傳 | 用途 |
|---|---|---|---|---|
| `/alerts` | GET | 🟢 | 警示陣列（參數 `level` / `acknowledged`） | 警示面板 |
| `/alerts/{id}/acknowledge` | POST | 🟢 | 標記已讀結果 | 確認警示 |
| `/alerts/subscribe` | POST | 🟢 | webhook 訂閱結果 | 機關訂閱 |
| `/alerts/stream` | GET | 🟢 | `{events:[...]}` 待推佇列 | 即時推播（輪詢/SSE） |
| `/emergency/deadlocks` | GET | 🟢 | 各區死結大站清單 | 死結警報 |
| `/emergency/check` | POST | 🟢 | `{triggered, dispatched[], alerts[]}`（body: in_transit_eta_min/persist） | 死結救火 |

**警示每筆欄位：**

| 欄位 | 型別 | 意義 |
|---|---|---|
| `alert_id` | str | 警示代碼 |
| `level` | str | `info` / `warning` / `critical` |
| `station_id` / `station_name` / `district` | str | 站點 |
| `message` | str | 警示訊息（中文） |
| `suggested_action` | str/null | 建議動作（如「補車 8 台」） |
| `triggered_at` | str | 觸發時間（ISO） |
| `acknowledged` | bool | 是否已讀 |

---

## 4. 人力 / 調度員 Operators

| 端點 | 方法 | 狀態 | 回傳 | 用途 |
|---|---|---|---|---|
| `/operators` | GET | 🟢 | 調度員陣列（可篩 role_type） | 人力面板 |
| `/operators/{id}` | GET | 🟢 | 單一調度員 | 調度員詳情 |
| `/vehicles` | GET | 🟢 | 車隊陣列（max_capacity/status/is_depot/current_district） | 車隊面板 |
| `/vehicles/standby` | GET | 🟢 | `{reserve_standby, depot_standby}` 待命車 | 預備車/總站待命 |
| `/vehicles/{id}` | GET | 🟢 | 單一調度車 | 車輛詳情 |
| `/operators/{id}/stream` | GET | 🔴 | 即時更新 | SSE 推播 |

**調度員欄位（資料模型已備，端點待接真實）：**

| 欄位 | 型別 | 意義 |
|---|---|---|
| `operator_id` / `name` | str | 調度員 |
| `role_type` | str | `driver`(調度車) / `stationed`(駐點) / `controller`(後台) / `depot_standby`(總站待命) |
| `status` | str | `on_duty` / `busy` / `resting` / `off_duty` |
| `current_district` | str/null | 當前作業行政區（動態） |
| `stationed_at` | str/null | 駐守站（僅 stationed） |

> ⚠️ 車隊 `vehicles` 主檔（vehicle_id / max_capacity / status含standby / is_depot總站待命 / current_district）
> 後端已備，尚無對應 API 端點，需後端補。

---

## 5. 帳號 Accounts（登入/管理）

| 端點 | 方法 | 狀態 | 回傳 | 用途 |
|---|---|---|---|---|
| `/auth/login` | POST | 🟢 | `{message, operator}`（失敗 401） | 登入 |
| `/accounts` | GET | 🟢 | 帳號陣列（需 maintainer） | 帳號管理 |
| `/accounts` | POST | 🟢 | 建立結果（需 maintainer） | 新增帳號 |
| `/accounts/{id}` | DELETE | 🟢 | 停用結果（需 maintainer） | 停用帳號 |

> 回傳一律不含 `password_hash`。登入 body：`{operator_id, password}`。

---

## 6. 覆寫 / 稽核 Overrides & Audit

| 端點 | 方法 | 狀態 | 回傳 | 用途 |
|---|---|---|---|---|
| `/stations/{id}/emergency-override` | POST | 🟢 | 覆寫結果（需 dispatcher） | ③即時緊急覆寫 |
| `/stations/{id}/emergency-override` | DELETE | 🟢 | 取消結果 | 取消覆寫 |
| `/overrides/active` | GET | 🟢 | 生效中覆寫陣列 | 覆寫列表 |
| `/audit/logs` | GET | 🟢 | 稽核陣列（參數 `type`/`station_id`/`operator`） | 稽核留痕 |

**稽核每筆欄位：** `log_id` / `type`（emergency_override/task_transfer/optimization/param_edit/task_report） / `station_id` / `operator` / `action` / `reason` / `timestamp`

---

## 7. 其他 KPI / 事件 / 最適化 / 天氣

| 端點 | 方法 | 狀態 | 回傳 | 用途 |
|---|---|---|---|---|
| `/kpi` | GET | 🔴 | KPI 指標 | 營運儀表板 |
| `/simulation/replay` | GET | 🔴 | Before/After | Demo 成效重放 |
| `/events` | GET/POST/DELETE | 🔴 | 活動事件 | 活動影響 |
| `/optimization/daily-review` | GET | 🟡 | 每日最適化待確認摘要 | ②AI 最適化（需人工核准） |
| `/optimization/daily-review/*` | POST | 🔴 | 逐站/核准/退回結果（需 maintainer） | 最適化決策 |
| `/weather/by-location?lat=&lng=` | GET | 🟢 | 該點最近雨量站+氣象站即時（見 §8.3） | 站點天氣/驟雨 |
| `/weather` | GET | 🟡 | 天氣摘要（相容，回 mock；逐站改用 by-location） | 天氣顯示 |
| `/health` | GET | 🟢 | 健康檢查 | 服務探活 |

**`/optimization/daily-review` 結構：** `{ review_id, review_date, lookback_days, summary{total_stations_adjusted, avg_change_pct, significant_count}, station_changes[], status }`

> ⚠️ 天氣：後端 `weather_source`（CWA 即時，觀測站級雨量/氣溫）**已接通**，但 `/weather` 端點還回 mock，
> 需後端把 `get_rainfall_by_location`/`get_weather_by_location` 接進端點。

---

---

## 8. 底層資料源能撈到的資料（完整欄位 + 真實範例）

> 每個源附**實際撈取的一筆真實資料**（值會隨即時變動）。部分尚未包成 HTTP 端點，但值後端都拿得到。

### 8.1 即時站點源（新北開放資料 010e5b15）🟢

`get_stations()` → 1600 站陣列，每站：

| 欄位 | 型別 | 意義 |
|---|---|---|
| `station_id` | str | 站點代碼 |
| `station_name` | str | 站名（含 `YouBike2.0_` 前綴） |
| `district` | str | 行政區 |
| `lat` / `lng` | float | 緯度 / 經度 |
| `total_docks` | int | 總柱數 |
| `available_bikes` | int | 可借車數 |
| `available_docks` | int | 可還空位數 |
| `usage_rate` | float | 借用率 %（可借÷總柱×100） |
| `status` | str | `empty`/`full`/`low`/`high`/`normal` |
| `service_available` | bool | 是否營運中 |
| `timestamp` | str | 本次抓取時間（ISO） |
| `source_timestamp` | str | 官方源更新時間 |
| `data_freshness` | str | `live:youbike_official` / `historical`（降級標記） |
| `yb2_quantity` | int | YouBike2.0 車數 |
| `eyb_quantity` | int | 電輔車數 |

```json
{
  "station_id": "500201001", "station_name": "YouBike2.0_下庄市場", "district": "八里區",
  "lat": 25.14678, "lng": 121.3999,
  "total_docks": 20, "available_bikes": 12, "available_docks": 8,
  "usage_rate": 60.0, "status": "normal", "service_available": true,
  "timestamp": "2026-09-10T22:45:13+08:00", "source_timestamp": "20260910T223902",
  "data_freshness": "live:youbike_official", "yb2_quantity": 12, "eyb_quantity": 0
}
```

### 8.2 S3 歷史（2026 年 1–6 月，30 分格）🟢

`get_history(station_id)` → 該站時間序陣列，每筆欄位同 8.1（少 yb2/eyb），`data_freshness="historical"`：

```json
{
  "station_id": "500201001", "station_name": "下庄市場", "district": "八里區",
  "lat": 25.14678, "lng": 121.3999,
  "total_docks": 20, "available_bikes": 14, "available_docks": 3,
  "usage_rate": 70.0, "status": "normal", "service_available": true,
  "timestamp": "2026-06-01 00:00:00", "source_timestamp": "2026-06-01 00:00:00",
  "data_freshness": "historical"
}
```
> 每站每 30 分一筆，期間 2026-01 ~ 2026-06（全量 1330 萬列）。用於歷史曲線/趨勢/訓練。

### 8.3 即時天氣（中央氣象署 CWA，觀測站級）🟢 後端已接

**雨量站** `get_rainfall_by_location(lat, lng)` → 最近雨量站（新北約 100 站）：

| 欄位 | 型別 | 意義 |
|---|---|---|
| `name` / `town` | str | 測站名 / 鄉鎮區 |
| `lat` / `lng` | float | 測站座標 |
| `now` | float | 當下雨量 (mm) |
| `past10` | float | 過去 10 分鐘雨量 (mm)（偵測驟雨主力） |
| `past1hr` | float | 過去 1 小時雨量 (mm) |
| `distance_km` | float | YouBike 站到此測站距離 |

```json
{"name":"八里","town":"八里區","lat":25.150211,"lng":121.403947,
 "now":0.0,"past10":0.0,"past1hr":0.0,"distance_km":0.56}
```

**氣象站** `get_weather_by_location(lat, lng)` → 最近氣象站（新北約 25 站）：

| 欄位 | 型別 | 意義 |
|---|---|---|
| `name` / `town` | str | 測站名 / 鄉鎮區 |
| `condition` | str | 標準化：`sunny`/`cloudy`/`rain`/`heavy_rain`/`typhoon` |
| `raw_weather` | str | CWA 原始中文天氣現象 |
| `temperature_c` | float | 氣溫 (°C) |
| `humidity` | float | 相對濕度 (%) |
| `rainfall_mm` | float | 當下雨量 (mm) |
| `distance_km` | float | 到此測站距離 |

```json
{"name":"西濱N000K","town":"淡水區","lat":25.17606,"lng":121.41807,
 "condition":"cloudy","raw_weather":"多雲","temperature_c":26.0,
 "humidity":81.0,"rainfall_mm":0.0,"distance_km":3.73}
```

### 8.4 地形（features.terrain）🟢

`get_terrain(lat, lng)` → 單站地形：

| 欄位 | 型別 | 意義 |
|---|---|---|
| `elevation` | float/null | 海拔高程 (m) |
| `slope_pct` | float/null | 局部坡度 %（中心±100m 最大高程差推算） |
| `terrain_class` | str | `flat`(<3%)/`gentle`(<5%)/`moderate`(<8%)/`steep`/`unknown` |

```json
{"elevation": 15.0, "slope_pct": 2.0, "terrain_class": "flat"}
```

### 8.5 POI 與區域類型（features.poi_distance）🟢

`get_poi_feature(lat, lng)` → `area_type` + 到 14 類 POI 最近距離(km)：

| 欄位 | 型別 | 意義 |
|---|---|---|
| `area_type` | str | `transit`/`school`/`commercial`/`leisure`/`medical`/`venue`/`sports`/`residential`/`mixed` |
| `dist_metro_km` | float | 最近捷運距離 |
| `dist_train_km` | float | 火車站 |
| `dist_bus_terminal_km` | float | 轉運站 |
| `dist_school_km` | float | 學校 |
| `dist_mall_km` | float | 百貨商場 |
| `dist_traditional_market_km` | float | 傳統市場 |
| `dist_night_market_km` | float | 夜市 |
| `dist_hospital_km` | float | 醫院 |
| `dist_park_km` | float | 公園 |
| `dist_park_sports_km` | float | 運動公園 |
| `dist_park_forest_km` | float | 森林公園 |
| `dist_riverside_km` | float | 河濱 |
| `dist_venue_km` | float | 場館 |
| `dist_sports_center_km` | float | 運動中心 |

```json
{"area_type":"leisure","dist_metro_km":5.156,"dist_train_km":16.12,
 "dist_bus_terminal_km":10.33,"dist_school_km":0.48,"dist_mall_km":4.21,
 "dist_night_market_km":4.921,"dist_traditional_market_km":4.763,"dist_hospital_km":5.135,
 "dist_park_km":0.219,"dist_park_sports_km":5.604,"dist_park_forest_km":7.516,
 "dist_riverside_km":4.537,"dist_venue_km":4.73,"dist_sports_center_km":4.831}
```

### 8.6 站點行為指紋（features.station_profile）🟢

`compute_profile(歷史序列, 總柱數)` → 六個月歷史算出的站點性格（規劃層，非即時調度）：

| 欄位 | 型別 | 意義 |
|---|---|---|
| `daily_activity` | float | 日均周轉量（借+還總量） |
| `day_night_ratio` | float | 日夜活動比（>1 日間型） |
| `weekend_ratio` | float | 平假日比（>1 休閒型） |
| `peak_direction` | str | `residential`(早流出/住宅) / `office`(早流入/辦公) / `flat` |
| `peak_shape` | str | `single_peak`/`double_peak`/`flat` |
| `demand_density` | float | 需求密度（日均活動÷柱數） |
| `empty_freq` / `full_freq` | float | 空站/滿站頻率（0~1） |
| `capacity` | int | 柱位數 |
| `station_type_label` | str | 站型：`commuter_residential`/`commuter_office`/`leisure_tourism`/`transit_hub`/`low_traffic`/`mixed` |

```json
{"daily_activity":44.6,"day_night_ratio":4.07,"weekend_ratio":1.12,
 "peak_direction":"residential","peak_shape":"flat","demand_density":2.23,
 "empty_freq":0.0215,"full_freq":0.0,"capacity":20,"station_type_label":"transit_hub"}
```

### 8.7 預測（LightGBMPredictor，ADR-113）🟢 後端已接

`predict_multi(station)` → 4 視野（30/60/90/120 分）各一組區間：

| 欄位 | 型別 | 意義 |
|---|---|---|
| `horizon_minutes` | int | 視野：30 / 60 / 90 / 120 |
| `raw_lower_bound` | float | P10 到達存量（悲觀，防空用；可 <0＝截斷訊號） |
| `raw_predicted` | float | P50 中位數（最可能值） |
| `raw_upper_bound` | float | P90 到達存量（樂觀，防滿用；可 >total＝截斷訊號） |
| `lower_bound`/`predicted_available`/`upper_bound` | float | 夾 [0,total] 後的顯示值 |

```json
[
 {"horizon_minutes":30,"raw_lower_bound":11.0,"raw_predicted":12.0,"raw_upper_bound":13.3,
  "lower_bound":11.0,"predicted_available":12.0,"upper_bound":13.3},
 {"horizon_minutes":60,"raw_lower_bound":10.7,"raw_predicted":12.0,"raw_upper_bound":13.2},
 {"horizon_minutes":90,"raw_lower_bound":9.1,"raw_predicted":12.0,"raw_upper_bound":13.4},
 {"horizon_minutes":120,"raw_lower_bound":7.8,"raw_predicted":12.0,"raw_upper_bound":14.0}
]
```
> 隨視野拉長區間變寬（不確定性升高）：30分[11.0,13.3] → 120分[7.8,14.0]。

---

## 給前端的重點

1. **🟢 綠色可直接串**：站點清單、單站參數、調度建議、警示、覆寫、稽核、帳號登入。
2. **🟡 黃色欄位已定、值待接**：單站預測（LightGBM）、天氣（CWA 已接後端待接端點）、每日最適化。
3. **🔴 紅色 mock 骨架**：任務看板、人力/車隊、KPI、事件、熱力圖——**欄位結構已定，可先照欄位開發**，後端接上後不用改。
4. 所有資源後端走可抽換工廠（換模型/換資料源不影響端點契約）——**你依賴的是回傳欄位，不是後端實作**。
