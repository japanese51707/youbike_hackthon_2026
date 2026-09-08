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

---

## 頁2 · 司機面板（桌機輕整理）＋ 司機手機端 `/driver`（新）

- 狀態：已實作，build 通過、語意審查 APPROVED。
- 依據：ADR-205（司機雙載具）、ADR-004（示意排程非派工決策）。

| # | 修改項 | 目的 | 動作 | 結果 |
|---|---|---|---|---|
| 1 | 桌機司機頁輕整理 | 先保留桌機版、去雜訊 | `OperatorPage.jsx` 移除時序面板（移交戰情室），其餘保留 | 桌機任務台維持原功能、較精簡 |
| 2 | 新增司機手機端 | 行動情境卡片式操作 | 新增 `pages/DriverPage.jsx`（手機優先、固定視窗、卡片式），路由 `/driver` | 手機端可接單、看路線、逐站作業 |
| 3 | 任務池資料來源 | 免造資料、誠實 | 以現有調度建議當任務池（`api/driverApi.js` 併 dashboard+operator） | 任務卡＝真實建議，含站名/取補數量/優先度/理由/距離 |
| 4 | 接單後自動排程 | 幫司機排停靠序 | `dispatchPlanner.js` 新增 `sequenceDriverRoute`（先取車後補車、就近串接） | 產生示意路線＋總距離，逐站導航 |
| 5 | 逐站導航與回報 | 行動作業閉環 | Google Maps 導航（僅公開座標）＋完成/故障/異常（本機狀態推進） | 完成即跳下一站；不送派遣指令 |
| 6 | 決策邊界標示 | 守 ADR-004 | 全頁標「示意 Mock」，接單/完成僅本機工作階段 | 不冒充最佳化、不進 payload、不 mutate mock |
| 7 | 導覽新增手機端 | 可達性 | `AppShell.jsx` 選單加「司機手機端」 | 四面板＋手機端皆可由選單進入 |
| 8 | 驗證 | 確保未壞 | `npm run build`＋語意審查 | 通過，4627 模組；審查 APPROVED |

**待處理／下一步**
- 桌機司機頁尚未做完整無捲動化（本輪僅輕整理，依你「桌機先保留」）。
- 手機端接單/完成為前端暫存，重整即重置（Demo 性質）。
- 下一頁：`/overview` 長官導覽面板無捲動化、`/twin` 戰情室（炫技集中）。

### 頁2 修訂（2026-09-05）：移除桌機司機頁，司機僅手機端

- 決策：owner 核准移除桌機 `/operator`。理由：桌機司機情境不成立；若改為車隊監控會與調度面板重疊，且 mock 規模過小不值得獨立成頁。
- 動作：
  - ADR-205 加修訂註記；README 索引同步。
  - 移除 `/operator` 路由與導覽項；刪除 `OperatorPage.jsx`、`TaskQueue.jsx`、`RouteMap.jsx`、`useOperatorData.js`；清除 operator 版面 CSS。
  - 司機僅保留手機端 `/driver`。
- 結果：`npm run build` 通過（模組 4621）；四面板導覽＝調度面板／司機手機端／長官導覽面板（戰情室待建）。
- 備註：`routeLayers.js`／`arcLayers.js` 暫留（戰情室可能重用），目前未被引用。
