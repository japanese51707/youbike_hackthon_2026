# API 待包端點施工清單

> 給 API 串接負責人：後端邏輯已備、但還沒包成 HTTP 端點的部分。
> 每項列：建議路徑 / 方法 / 呼叫哪個後端函式 / 回什麼 / 給哪個前端畫面。
> 現況分三類：🟡 端點在但回 mock（換真實）｜🟣 後端有函式、無端點（新增）。

---

## 優先序總覽

| 優先 | 項目 | 為什麼 |
|---|---|---|
| **P0 必做** | 單站預測、天氣、任務 CRUD、互動組單三入口+確認 | Demo 核心：地圖點站看預測/天氣、組派工單全流程 |
| **P1 加分** | 逐站回報/認領、人力車隊、死結警報、下一趟建議 | 執行閉環 + 人力視覺化 + 反應速度亮點 |
| **P2 補完** | 地形/POI/行為指紋、KPI、熱力圖、每日最適化 | 分析佐證、簡報素材 |

---

## P0 — 必做（Demo 核心）　✅ 已完成（2026-09-10）

> 單站預測、天氣 by-location、任務清單/詳情、互動組單三入口、confirm-trip 皆已接真實並測試通過。
> 下方保留原規劃供對照。

### 1. 單站預測（換真實）🟡
| 項目 | 內容 |
|---|---|
| 現況 | `GET /stations/{id}` 的 `prediction` 欄位回 mock |
| 改法 | 呼叫 `LightGBMPredictor().predict_multi(station)` 填 `prediction` |
| 回傳 | 4 視野 × P10/P50/P90 到達存量（見速查表 §8.7） |
| 畫面 | 單站詳情面板的預測區間圖 |

### 2. 天氣（換真實）🟡
| 項目 | 內容 |
|---|---|
| 現況 | `GET /weather` 回 mock（但後端 CWA 已接通） |
| 改法 | 加參數 `lat`/`lng`，呼叫 `get_weather_source().get_rainfall_by_location()` + `get_weather_by_location()` |
| 建議新增 | `GET /weather/by-location?lat=&lng=` → 該點最近雨量站+氣象站 |
| 回傳 | 雨量（now/past10/past1hr）+ 天氣（condition/temp/humidity）（見 §8.3） |
| 畫面 | 站點天氣資訊、驟雨警示 |

### 3. 互動組單三入口（新增）🟣 ★最核心
| 建議端點 | 方法 | 呼叫 | 回傳 |
|---|---|---|---|
| `/dispatch/build/from-vehicle` | POST | `dispatch_builder.build_from_vehicle(vehicle_id, operator_id, dispatch_list, district?)` | 草稿 draft（含 estimate） |
| `/dispatch/build/from-station` | POST | `build_from_station(station_id, dispatch_list, ...)` | 草稿 + `vehicle_candidates` |
| `/dispatch/build/emergency` | POST | `build_emergency(station_ids, dispatch_list, ...)` | 草稿 + `resource_suggestion` |
| `/dispatch/confirm-trip` | POST | `confirm_trip(draft, operator)` | 落地結果（assigned） |
| 畫面 | 後台派工組單台（三按鈕 + 草稿預覽卡 + 確認） |
| 備註 | `dispatch_list` 可由後端內部先跑 `build_dispatch_list` 再傳入，前端不必自己算 |

### 4. 任務清單/詳情（換真實）🟡
| 項目 | 內容 |
|---|---|
| 現況 | `GET /dispatch/tasks`、`/dispatch/overview` 回 mock |
| 改法 | 接 `task_manager.list_tasks()` / `.get(task_id)` |
| 回傳 | 任務（trip_id/district/shift/mode/assigned_*/route[站級]/est_*） |
| 畫面 | 任務執行看板 |

---

## P1 — 加分（執行閉環 + 亮點）　✅ 已完成（2026-09-10）

> 逐站回報/認領/後台介入、下一趟建議、人力車隊(operators/vehicles)、死結警報 皆已接真實並測試通過。

### 5. 逐站回報 / 認領 / 後台介入（新增）🟣
| 建議端點 | 方法 | 呼叫 | 用途 |
|---|---|---|---|
| `/dispatch/tasks/{id}/report`（已有路由，換真實） | POST | `task_execution.report_station(id, station_id, actual_available, op)` | 逐站回報實際存量 |
| `/dispatch/tasks/{id}/stations/{sid}`（抽離） | DELETE | `remove_station(...)` | 後台抽離個別站 |
| `/dispatch/tasks/{id}/stations`（增站） | POST | `add_station(...)` | 後台增加個別站 |
| `/dispatch/tasks/{id}/return` | POST | `cancel_by_executor(id, op, reason)` | 執行者退回（附原因） |
| `/dispatch/claim-map` | GET | `station_claim_map(district?)` | 認領地圖（防重複接） |
| 畫面 | 任務看板逐站進度、認領地圖、後台介入 |

### 6. 下一趟建議（新增）🟣
| 建議端點 | 方法 | 呼叫 | 回傳 |
|---|---|---|---|
| `/dispatch/next-trip?vehicle_id=` | GET | `dispatcher.suggest_next_trip(vehicle_id, dispatch_list)` | 候選站排序（緊急度-距離評分） |
| 畫面 | 車完成任務後，後台選下一趟 |

### 7. 人力 / 車隊（換真實 + 新增）🟡🟣
| 建議端點 | 方法 | 呼叫 | 回傳 |
|---|---|---|---|
| `/operators`（換真實） | GET | `operators_repo.list_operators()` | 調度員（四角色/狀態/current_district） |
| `/vehicles`（新增） | GET | `vehicles_repo.list_vehicles()` | 車隊（max_capacity/status/is_depot/current_district） |
| `/vehicles/standby`（新增） | GET | `vehicles_repo.list_standby()` + `list_depot_standby()` | 預備車/總站待命車 |
| 畫面 | 人力車隊狀態面板 |

### 8. 死結警報 / 緊急救火（新增）🟣 ★反應速度亮點
| 建議端點 | 方法 | 呼叫 | 回傳 |
|---|---|---|---|
| `/emergency/deadlocks` | GET | `emergency.detect_deadlocks(stations)` | 各區死結大站清單 |
| `/emergency/check` | POST | `check_and_dispatch_reserve(stations, in_transit_eta)` | 是否觸發+派的預備車+critical警報 |
| 畫面 | 死結紅字警報、救火派車 |

---

## P2 — 補完（分析佐證 / 簡報）　✅ 大部分完成（2026-09-10）

> 站點靜態打包 `/stations/{id}/static`（位置+地形+POI+行為指紋，回快取不現算）、heatmap 聚合、
> KPI 即時統計 皆已接真實。行為指紋離線批次算存 `_profile_cache.json`（tools/build_profile_cache.py）。
> 仍 mock：`/simulation/replay`、`/optimization/daily-review`（需 param_optimizer，較複雜，後補）。

### 9. 地形 / POI / 行為指紋（新增）🟣
| 建議端點 | 方法 | 呼叫 | 回傳 |
|---|---|---|---|
| `/stations/{id}/terrain` | GET | `features.terrain.get_terrain(lat,lng)` | 海拔/坡度/分類（§8.4） |
| `/stations/{id}/poi` | GET | `features.poi_distance.get_poi_feature(lat,lng)` | area_type+14類距離（§8.5） |
| `/stations/{id}/profile` | GET | `features.station_profile.compute_profile(history, total)` | 行為指紋+站型（§8.6） |
| 畫面 | 單站分析卡、簡報素材 |
| 備註 | 這三個可合併成 `/stations/{id}/analysis` 一次回，減少請求 |

### 10. KPI / 熱力圖 / 每日最適化（換真實）🟡
| 項目 | 現況 | 改法 |
|---|---|---|
| `GET /kpi` | mock | 接真實統計（需先定義 KPI 算法） |
| `GET /stations/heatmap` | mock | 按維度聚合站點 |
| `GET /optimization/daily-review` | 半 mock | 接 param_optimizer |
| `GET /simulation/replay` | mock | Before/After 重放 |

---

## 施工建議

1. **P0 先做**：讓「地圖點站看預測+天氣」「後台組派工單」兩條 demo 主線先通。
2. **統一模式**：每個端點只呼叫 `get_xxx()` 工廠取抽象（換模型/換源不影響端點）。
3. **dispatch_list 共用**：組單三入口需要「當前需調度清單」，後端可先跑 `build_dispatch_list` 快取，各入口共用。
4. **權限**：confirm-trip / 抽離增站 / 帳號管理 走既有 `require_role` 閘門。
5. **每包完一個端點**：更新 `api_reference_for_frontend.md` 的狀態欄（🟡🟣 → 🟢）。
