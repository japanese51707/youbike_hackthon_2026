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
| 2 | 捲動頁維持置中限寬 | 司機桌機/長官頁排版不跑掉 | `.page-stack` 加 `width:min(1500px,100%)`＋`margin:auto`；新增 `.scroll-page` | operator/overview 仍置中限寬、正常捲動 |
| 3 | 調度面板改固定視窗 | 一眼看完、細節點開 | 重寫 `DashboardPage.jsx`：`.fixed-page` → 精簡工具列＋KPI 條＋`.dashboard-main`（左地圖 1.7fr／右操作 1fr） | 調度面板填滿視窗、不捲動 |
| 4 | 右側操作分頁化 | 不捲動下容納三塊操作 | 右欄用 `Tabs`：調度建議／即時警示／缺口榜，清單於分頁內自捲 | 三塊操作共存、頁面不捲 |
| 5 | 面板可內嵌 | 放進單一 Card+Tabs 不卡中卡 | `RecommendationPanel`/`AlertPanel`/`DeficitRankingPanel` 新增 `embedded` prop，省略自身 Card 外框 | 分頁內乾淨呈現、無重複標題 |
| 6 | 站況地圖乾淨化 | 調度面板不放炫技 | `StationMap.jsx` 新增 `showLayerControl`（預設 `false`）、地圖填滿容器 | 只顯示站點狀態環，無 Voronoi/Hexagon 圖層控制 |
| 7 | 移出非調度內容 | 聚焦操作、去雜訊 | 調度面板移除時序面板、區域壓力表格、冗長安全提示 | 畫面聚焦「發現問題→建議→確認」 |
| 8 | 導覽改名 | 對齊四面板命名 | `AppShell.jsx`：調度面板／司機面板／長官導覽面板 | 選單語意對齊（戰情室、司機手機端待建立後再加） |
| 9 | 驗證 | 確保未壞 | `npm run build` | 通過，4624 模組；JS 3,878 kB／gzip 1,178 kB |

**待處理／下一步**
- `/driver` 司機手機端、`/twin` 戰情室尚未建立。
- 站點抽屜目前仍是完整版；ADR-205 建議調度面板用精簡版，後續可再瘦身。
- 矮螢幕若被切到，需再壓縮 KPI／工具列高度。
