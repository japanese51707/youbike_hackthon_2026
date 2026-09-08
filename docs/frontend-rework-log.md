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
