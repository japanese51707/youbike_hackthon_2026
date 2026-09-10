# 前端四頁改版工作紀錄

依 ADR-205（四頁角色導向資訊架構與無捲動固定視窗版面）逐頁改版的紀錄。
每頁記錄「目的／動作／結果」，方便回溯與交接。

---

## 頁1 · 調度面板 `/dashboard`（無捲動重構）

- 狀態：已實作，build 通過。
- 依據：ADR-205。

| # | 修改項 | 目的 | 動作 | 結果 |
|---|---|---|---|---|
| 1 | 整站殼無捲動 | 頁面本身不出現捲軸 | `app.css`：`.app-shell` 改 `height:100vh` flex 直向 + `overflow:hidden`；`.topbar` 由 sticky 改 `flex:none`；`.page-content` 改 `flex:1 / min-height:0 / overflow-y:auto` | 視窗不再整頁捲動；未改造頁在內容區內捲動、不受影響 |
| 2 | 捲動頁維持置中限寬 | 長官頁排版不跑掉 | `.page-stack` 加 `width:min(1500px,100%)`＋`margin:auto`；新增 `.scroll-page` | overview 仍置中限寬、正常捲動 |
| 3 | 調度面板改固定視窗 | 一眼看完、細節點開 | 重寫 `DashboardPage.jsx`：`.fixed-page` → 精簡工具列＋KPI 條＋`.dashboard-main`（左地圖 1.7fr／右操作 1fr） | 調度面板填滿視窗、不捲動 |
| 4 | 右側操作分頁化 | 不捲動下容納三塊操作 | 右欄用 `Tabs`：調度建議／即時警示／缺口榜，清單於分頁內自捲 | 三塊操作共存、頁面不捲 |
| 5 | 面板可內嵌 | 放進單一 Card+Tabs 不卡中卡 | `RecommendationPanel`/`AlertPanel`/`DeficitRankingPanel` 新增 `embedded` prop | 分頁內乾淨呈現、無重複標題 |
| 6 | 站況地圖乾淨化 | 調度面板不放炫技 | `StationMap.jsx` 新增 `showLayerControl`（預設 `false`）、地圖填滿容器 | 只顯示站點狀態環，無 Voronoi/Hexagon 圖層控制 |
| 7 | 移出非調度內容 | 聚焦操作、去雜訊 | 調度面板移除時序面板、區域壓力表格、冗長安全提示 | 畫面聚焦「發現問題→建議→確認」 |
| 8 | 導覽改名 | 對齊四面板命名 | `AppShell.jsx` 選單命名 | 選單語意對齊 |
| 9 | 驗證 | 確保未壞 | `npm run build` | 通過 |

**待處理**：站點抽屜仍為完整版（可再瘦身）；矮螢幕若被切到需再壓縮 KPI／工具列高度。

---

## 頁2 · 司機手機端 `/driver`（完整決策紀錄）

- 狀態：已實作、build 通過、語意審查 APPROVED；待 owner 瀏覽器確認後 commit。
- 依據：ADR-205（司機角色面向）、ADR-004（AI 只估計、規則引擎決策、人在迴圈）。

### A. 頁面定位與載具決策（含演進）

| # | 決策 | 目的 | 動作 | 結果 |
|---|---|---|---|---|
| A1 | 司機＝手機優先 | 貼近外勤情境（車上用手機） | 新增 `pages/DriverPage.jsx`：手機優先、固定視窗、卡片式、大按鈕；路由 `/driver` | 手機端可接單→排程→導航→回報 |
| A2 | 移除桌機司機頁 | 桌機開車情境不成立；桌機版若改車隊監控會與調度面板重疊，且 mock 規模過小不值得獨立成頁 | owner 核准後移除 `/operator`：刪 `OperatorPage.jsx`／`TaskQueue.jsx`／`RouteMap.jsx`／`useOperatorData.js`＋operator 版面 CSS；ADR-205 加修訂註記、索引同步 | 司機僅手機端；導覽＝調度面板／司機手機端／長官導覽面板 |

### B. 資料來源與模型

| # | 決策 | 目的 | 動作 | 結果 |
|---|---|---|---|---|
| B1 | 任務池＝現有調度建議 | 免造資料、誠實 | `api/driverApi.js` 併 `getDashboard`(建議/站點)＋`getOperatorWorkspace`(操作員) | 任務卡＝真實建議：站名/取補數量/優先度/理由/距離 |
| B2 | 出發點＝操作員位置 | 排程與導航需要起點 | 取 `operator.current_location`（缺值則不排程） | 以真實 mock 操作員位置為路線起點 |

### C. 三個操作模式

| # | 模式 | 目的 | 動作 | 結果 |
|---|---|---|---|---|
| C1 | 任務池 | 司機挑單 | 建議卡片列出（取/補、數量、優先度、理由、距起點距離），按「接單」 | 接單加入路線（本機狀態） |
| C2 | 我的路線 | 看完整規劃 | 自動排程序列＋**總路線規劃地圖**（起點＋停靠點＋連線，沿用 `planLayers`）＋「整條路線 Google Maps 導航」（origin→途經點→destination）＋逐站清單與總距離 | 一眼看完整條路線、可整段導航 |
| C3 | 當前停靠 | 逐站作業閉環 | 大卡：站名、取/補數量、單站 Google Maps 導航、「完成／故障／異常」 | 完成即跳下一站 |

### D. 自動排程規則（示意）

| # | 決策 | 目的 | 動作 | 結果 |
|---|---|---|---|---|
| D1 | 透明確定性排序 | 可解釋、可追溯 | `dispatchPlanner.sequenceDriverRoute`：先取車後補車、各自從目前位置就近串接；`geo.haversineKm` 算距離 | 產生示意停靠序與每段/總距離 |

### E. 決策邊界與安全（守 ADR-004）

| # | 決策 | 目的 | 動作 | 結果 |
|---|---|---|---|---|
| E1 | 非正式最佳化 | 真實最佳化屬後端規則引擎 | 全頁標「示意 Mock」，並註明「不送出派遣指令」 | 不冒充最佳化 |
| E2 | 不進 payload、不改狀態 | 前端不做真實世界決策 | 接單/完成僅 `useState` 本機暫存，不呼叫 mutation、不改 mock store、不動後端契約 | 重整即重置（Demo 性質） |
| E3 | 導航只帶公開座標 | 出向資料最小化 | Google Maps URL 僅含經緯度，無任務/使用者資料 | 符合 ADR-202/204 導航約束 |

### F. 共用地圖修正（本輪順帶）

| # | 修改項 | 目的 | 動作 | 結果 |
|---|---|---|---|---|
| F1 | 修正地圖黑框 | 地圖全黑沒渲染 | `.map-fill` 高度原只綁 `.dashboard-map`，改全域 `.shared-map.map-fill{height:100%}` | 司機總路線地圖正常渲染（canvas 不再 0 高） |
| F2 | attribution 精簡 | 原本又大又是多餘連結 | `BasemapStatus.jsx`：去連結改一行小灰字；ready 不顯示大標籤；無底圖時不顯示來源 | 角落只剩必要小字，仍守 OSM/ODbL 與 ADR-204 |

### 新增／刪除檔案
- 新增：`pages/DriverPage.jsx`、`hooks/useDriverData.js`、`api/driverApi.js`、`utils/geo.js`（先前）、`dispatchPlanner.sequenceDriverRoute`。
- 刪除：`pages/OperatorPage.jsx`、`components/operator/TaskQueue.jsx`、`components/operator/RouteMap.jsx`、`hooks/useOperatorData.js`。
- 暫留未用：`components/map/layers/routeLayers.js`、`arcLayers.js`（戰情室可能重用）。

### 驗證
- `npm run build` 通過（模組 4621）；語意審查 APPROVED（無 blocker）。

### 待處理／下一步
- 手機端接單/完成為前端暫存，重整即重置。
- 未來可接後端真預測／真緊急度取代 mock（涉 ADR-203 待決策契約，另議）。
- 下一頁：`/overview` 長官導覽面板無捲動化、`/twin` 戰情室（炫技集中）。

---

## 頁3 · 長官導覽面板 `/overview`（無捲動 + 研究導向重構）

- 狀態：已實作、build 通過；待 owner 瀏覽器確認後 commit。
- 依據：ADR-205（長官頁定位，內容 refinement 不改頁面定位）；設計研究見 `docs/research/長官儀表板設計研究.md`。

| # | 修改項 | 目的 | 動作 | 結果 |
|---|---|---|---|---|
| 1 | 先做研究再設計 | 釐清長官該看什麼 | 研究 executive dashboard 原則＋公共自行車 KPI，落地成 `docs/research/長官儀表板設計研究.md` | 有依據的四區設計 |
| 2 | 無捲動化 | 符合 ADR-205 | 重寫 `OverviewPage.jsx` 為 `.fixed-page`，移除即時操作/示意路線/時序面板 | 整頁不捲、聚焦成效 |
| 3 | Zone1 服務水準頭條 | 回答「達標了嗎」 | 空站率/滿站率 + 達標燈號（Demo 目標 <6%/<3%）、需調度、平均使用率，可點開細節 | 一眼看服務水準與達標狀態 |
| 4 | Zone2 成效對比 | 回答「有沒有變好」 | Before/After 圖 + 改善幅度標籤（實際vs模擬換算） | 保留並強化 |
| 5 | Zone3 熱點行政區 | 回答「哪裡要關注」 | 由 stations 現算各區問題站排行，點開看該區站點 | 誠實彙總、可下鑽 |
| 6 | Zone4 人力與成本 | 回答「投入與問責」 | 人力圓餅 + 里程/油資/每台移動油資 | 資源效率一頁看 |
| 7 | 分類 icon 化 | 更清楚 | 分頁與卡片加 icon | 視覺分類明確 |
| 8 | 驗證 | 確保未壞 | `npm run build` | 通過，4616 模組 |

**誠實性標註**
- 達標「目標值」為 Demo（<6%/<3%），標示待交通局定義。
- 服務水準%（站時有車有位）、未滿足需求、跨日趨勢屬待接真實資料，未假造（研究筆記已記錄）。
- 熱點行政區、改善幅度均由既有 mock 現算，非捏造。

### 頁3 增修（2026-09-05）：黑畫面修正、AI 營運助理（浮動）、LLM 決策留檔

| # | 修改項 | 目的 | 動作 | 結果 |
|---|---|---|---|---|
| 1 | 修長官頁黑畫面 | render 崩潰 | `getOverview()` 補回既有 `kpi`（原本沒回傳，頁面讀 `kpi.empty_rate` 丟例外） | 長官頁正常顯示 |
| 2 | AI 營運助理（Demo 規則型） | 摘要現況＋輔助決策 | 新增 `OverviewAssistant.jsx`＋`utils/overviewAssistant.js`：自動摘要、規則問答、交通知識決策建議（空站優先於滿站），答案全來自既有資料、缺值不捏造 | 可摘要與問答，護欄明確 |
| 3 | 助理定位護欄 | 守 ADR-004 | 明訂 advisory-only：只建議/示警、不自行決策、不進 payload；底部標語標示 | 不會讓錯誤決策擴散 |
| 4 | LLM 接入留決策 | 交後端決定 | 新增 `docs/decisions/ADR-301`（proposed）：定位＋LLM 接入三選項＋護欄；ADR-000/README 登記 | 是否接 LLM 留給後端/owner |
| 5 | 助理改浮動小籤 | 不佔版面 | 助理改為右下角收合小籤，點開浮出、可隨時收起；主區回兩欄（成效圖＋熱點分頁） | 需要時才出現、可收合 |
| 6 | 三欄→兩欄→浮動 | 版面調整 | 過程中曾試三欄並排（卡片內部自捲），最後依需求改浮動助理 | 主區更寬敞 |
| 7 | 驗證 | 確保未壞 | `npm run build` | 通過，4618 模組 |

**知識落地**：研究筆記 `docs/research/長官儀表板設計研究.md`（executive dashboard 原則＋公共自行車 KPI＋長官需求＋資料盤點＋來源）。

---

## 頁4 · 數位孿生戰情室 `/twin`（空間/交通分析集中頁）

- 狀態：已實作、build 通過；待 owner 瀏覽器確認後 commit。
- 依據：ADR-205（第四頁＝酷炫/分析集中，服務騎乘者/觀眾/評審）、ADR-204（深色主題與地圖互動）、ADR-004（AI 只估計、規則引擎決策；本頁為分析呈現，不做自動調度決策）。
- 設計研究：`docs/research/交通與都市空間分析方法研究.md`。

### A. 頁面定位（先討論再做）

| # | 決策 | 目的 | 動作 | 結果 |
|---|---|---|---|---|
| A1 | 定位＝空間/交通分析，不只炫技 | owner 要的是「未來的城市設計/規劃/交通規劃」細緻優化 | 先研究交通與都市空間分析方法（空間統計/GIS/網路科學/運輸規劃/都市設計/時空），落地成研究筆記 | 有依據地選 8 個分析，非為炫而炫 |
| A2 | 每個分析附「這在分析什麼」 | 讓不懂空間分析的人也看得懂 | 建 `config/analysisCatalog.js`：每分析含 name/discipline/dataMode/purpose/白話 `info`；UI 每項旁放問號 Popover | 評審/觀眾點問號即懂 |
| A3 | 誠實度三態標註 | 守「不捏造」 | dataMode：`real` 實算／`method` 方法展示（站少不可靠）／`pending` 待接資料；UI 用 Tag 標示，並列出待接分析 | 統計方法不冒充可靠推論 |

### B. 分析工具與圖層

| # | 項目 | 目的 | 動作 | 結果 |
|---|---|---|---|---|
| B1 | 空間/網路統計工具 | 可重用的確定性算法 | 新增 `utils/spatialStats.js`：`stationPressure`、`getisOrdGiStar`(二元距離權重、母體 SD、z 分數)、`giStarClass`(±1.96/±2.58)、`buildKnnNetwork`(k 近鄰無向邊)、`degreeCentrality`(距離衰減加權、正規化) | 純函式、來自既有站點資料、不呼叫外部服務 |
| B2 | 分析圖層 | 把方法畫到地圖 | 新增 `components/map/layers/analysisLayers.js`：KDE 熱力、覆蓋缺口(格點到最近站距離)、鄰近網路+中心性(邊+節點)、服務集水區(半徑圓)、Voronoi+Gi\* 著色、流向弧線(取車→補車示意 OD) | 8 分析可切換疊加 |
| B3 | 復用既有圖層 | 不重造輪子 | 復用 `densityLayer`(Hexagon)、`stationGaugeLayer`(狀態環)、`voronoiLayer` 概念 | 一致的視覺語言 |
| B4 | 加依賴 | Gi\*/中心性需統計基礎 | 裝 `simple-statistics@7.12.0`（精確釘選，0 vulnerabilities；owner 同意） | mean/standardDeviation 供 Gi\* 用 |

### C. TwinPage 組裝

| # | 項目 | 目的 | 動作 | 結果 |
|---|---|---|---|---|
| C1 | 全螢幕暗色地圖 | 戰情室氛圍、無捲動 | `pages/TwinPage.jsx`：`.fixed-page.twin-page` + `SharedMap map-fill` 填滿 | 整頁不捲、地圖填滿 |
| C2 | 圖層控制盤（左上浮層） | 切換 8 分析、看說明 | overlay 內 Checkbox 清單＋每項問號 Popover(取自 catalog)＋誠實度 Tag；內容過長時控制盤自身內捲 | 頁面不捲、控制盤內捲 |
| C3 | 時間機器（底部浮層） | 歷史/即時/預測比較 | Segmented Past/Live/Predict：用既有 temporal mock 產站點快照，重算 usage/status；僅少數站有歷史/預測樣本，其餘顯示即時（明確標注） | 可切時間看分析變化，不假造 |
| C4 | 集水區半徑可調 | 探索服務範圍 | catchment 啟用時顯示 Slider（0.2–2km） | 即時調整半徑 |
| C5 | Gi\* 圖例 | 看懂顯著性著色 | voronoi 啟用時顯示熱/冷點圖例 | 顏色對照清楚 |
| C6 | 站點資產卡 | 點站看細節 | 點 gauge/網路節點 → 復用 `StationDrawer`（即時狀態/預測區間/天氣/特徵） | 分析與單站細節打通 |
| C7 | 導覽與路由 | 第四頁上線 | `App.jsx` 加 `/twin` 路由；`AppShell.jsx` 導覽加「數位孿生戰情室」(DeploymentUnitOutlined) | 可從選單進入 |
| C8 | 驗證 | 確保未壞 | `npm run build` | 通過 |

### D. 誠實性與邊界（守專案原則）
- Gi\*、中心性在 mock 僅約 10 站時**不具可靠推論**，全數標「方法展示」；真實全市資料進來即可切換為可靠推論、**不需改介面**。
- 集水區以直線半徑近似，UI 註明「真正等時圈需路網」。
- 流向弧線**無真實 trip OD**，僅以調度建議航段示意，標「待接」。
- 待接分析（真實 OD、公平性/2SFCA、LTS、時空熱點、Space Syntax）於 UI 誠實列出，不以假資料充數。
- 全部前端純函式、確定性、**不進後端 payload、不改後端契約**；本頁只做分析呈現，不做自動調度決策（守 ADR-004）。

### 新增檔案
- `frontend/src/config/analysisCatalog.js`、`frontend/src/utils/spatialStats.js`、`frontend/src/components/map/layers/analysisLayers.js`、`frontend/src/pages/TwinPage.jsx`。
- 研究筆記：`docs/research/交通與都市空間分析方法研究.md`。
- 依賴：`simple-statistics@7.12.0`（package.json / package-lock.json）。

### 知識落地
- 研究筆記整理交通/都市空間分析六大學科的方法族、twin 實作對照表、待接清單與取捨結論，含來源連結與合規註記，供未來擴充與交接。

### G. 語意審查與修正
- 語意審查結論：無 blocker（無捏造、無後端契約破壞、無 ADR-004 違反，Gi\* 數學正確）。
- 依審查建議補防呆（誠實性）：`analysisLayers.js` 新增 `withFiniteCoords`，在 KDE/覆蓋缺口/網路/集水區/Voronoi+Gi\*/flow 進入幾何運算前先過濾缺經緯度（NaN）的站點；避免接真實 TDX 資料時缺座標站污染 Delaunay/bounds/格點，畫出「看起來像分析、其實是壞掉的幾何」。
- 其餘為非阻斷建議（flow 笛卡兒積、滑桿全圖層重算、真實規模效能、predict 用點估計著色、時間機器為三態非時間軸、缺 spatialStats 單元測試），留待後續視需要處理。
- `npm run build` 於修正後再次通過。

---

## 頁1 再造 · 調度面板決策流（ADR-206）

- 狀態：已實作、build 通過；待 owner 瀏覽器確認後 commit。
- 依據：ADR-206（本頁資訊架構）、對齊 ADR-119（三入口組單）、ADR-114（資源模型）、ADR-118（死結警報）、ADR-004（AI 只估計、規則引擎決策）。

### 目的
把原本「工具列＋KPI＋地圖＋右側三分頁（建議/警示/缺口榜）」的發散版面，改成**服務調派員決策流的聚焦架構**：
一張地圖（舞台）＋右欄狀態機（待命態／組單態），對齊後端 ADR-119 的三入口與預覽確認，並加入執行追蹤。

### 動作

| # | 項目 | 目的 | 動作 | 結果 |
|---|---|---|---|---|
| 1 | mock 車輛 | 三入口與載運量成立 | `mock_data.json` 加 `vehicles`（對齊 ADR-114：max_capacity 15／status／current_district／is_reserve／current_location），`mockAdapter.getDashboard` 暴露 | 6 台示意車（含 1 台總站待命預備車、1 台維修中） |
| 2 | 組單演算 | 先載後放示意草稿 | 新增 `utils/tripPlanner.js`：`buildFromVehicle/buildFromStation/buildEmergency`；先載（滿站取車至載運上限）後放（缺車站補車）；候選車序（該區→鄰近→總站待命）；預估（距離/交通+作業時間/載運量/緊急度加總）。參數externalise 到 `fleetMock.js` `tripPlannerConfig` | 純函式、確定性、標示意 |
| 3 | 地圖擴充 | 車入口＋畫路線 | `StationMap` 加 `vehicles`（可點→車找站）、`draftRoute`（先載後放路線，復用 `planLayers`）、車輛/停靠點 tooltip；向後相容 | 點車組單、草稿路線上圖 |
| 4 | 待命態 | 發現＋追蹤 | 新增 `dispatch/DispatchSidePanel.jsx`：警報區（critical 可「緊急出車」）／需調度清單（緊急站排行，**缺口榜併入**，點站→站找車）／執行追蹤（狀態生命週期 pill＋逐站進度） | 平常只看「該做什麼／在做什麼」 |
| 5 | 組單態 | 右欄接管精靈 | 新增 `dispatch/OrderBuilder.jsx`：選資源（改車/改區重算）→ 路線（先載後放）→ 預估卡 → 預覽→確認；跨區示意警告 | 三入口共用一條預覽確認流 |
| 6 | 頁面狀態機 | 串起決策流 | 重寫 `DashboardPage.jsx`：三入口觸發、送出後進追蹤清單、狀態示意推進（assigned→accepted→in_progress 逐站→completed）、移除三分頁、KPI 站數改動態（`地圖顯示 N 筆`） | 一頁走完 發現→組單→預覽→送出→追蹤 |
| 7 | 樣式 | 聚焦深色 | `app.css` 加 dispatch-deck／需調度列／追蹤 pill／組單步驟／預估卡樣式 | 右欄內捲、頁面不捲 |
| 8 | 清理 | 去冗餘 | 刪除已無引用的 `RecommendationPanel.jsx`／`AlertPanel.jsx`／`DeficitRankingPanel.jsx`（功能併入 DispatchSidePanel） | 減少發散 |
| 9 | 驗證 | 確保未壞 | `npm run build`＋診斷 | 通過、0 錯誤 |

### 誠實邊界（守專案原則）
- 調度車位置、執行進度皆 mock **示意**；狀態推進是前端示意，不做假 GPS。
- 「先載後放」為前端**示意排序**，真正最優組單在後端 `dispatch_builder`（守 ADR-004）。
- 確認送出真環境需 dispatcher 權限；mock 僅本機展示，不進 payload、不寫 DB。
- **站數完全動態**：後端給幾站畫幾站（地圖／清單／KPI 皆不寫死），不提供站點增刪 UI。
- 本分支只做調度面板；跨頁「司機接走」與後端串接不在此範圍。
