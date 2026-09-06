---
status: superseded
date: 2026-09-02
decision-makers:
  - project-owner
approval-evidence: "2026-09-02 Kiro session：owner 核准三頁由 Leaflet 改 MapLibre + Deck.gl，OpenFreeMap 為唯一免費遠端底圖，不使用需帳務／信用卡／按量計費／可能超額扣款的地圖 provider 或 API key；底圖失敗或斷網切換本地 empty MapLibre style／no-basemap，資料層與控制面板繼續運作；並承接 ADR-201 的 React／Vite／JSX／Router／Ant Design／ECharts／Mock adapter／三路由決策"
scope:
  - frontend
  - map-architecture
  - dependencies
  - outbound-security
  - availability
related-commits:
  - d1fdb16
retrospective: false
supersedes: ADR-201
superseded-by: ADR-204
---

> **取代註記（2026-09-04）**：本 ADR 的地圖架構已於 commit `d1fdb16` 實作。底圖 style 來源決策（固定載入遠端 liberty）已由 ADR-204 取代為「自帶暗色 style JSON、資料仍鎖 OpenFreeMap 同源」；其餘決策（MapLibre／Deck.gl、無 key／零計費、no-basemap 降級、attribution、出向信任邊界、承接自 ADR-201 的決策）由 ADR-204 完整承接。保留本文件為歷史，不改寫。

# ADR-202：MapLibre／Deck.gl／OpenFreeMap 地圖架構

## 背景與問題

ADR-201 已建立 React／Vite Mock-first 三頁前端，但其 Leaflet 地圖架構不足以支撐三頁共用的數位孿生視覺層、較大量的站點／路線資料層與一致的降級行為。遠端底圖也形成出向信任與可用性邊界；若 provider 要求帳務、信用卡、API key、按量計費或可能超額扣款，會引入本專案不接受的成本與憑證風險。即使遠端底圖失效，業務資料、控制面板及錯誤狀態仍必須可用，不能以空白地圖靜默失敗。

## 決策

- 三個固定路由 `/dashboard`、`/operator`、`/overview` 的地圖全部改用共用 MapLibre GL JS 地圖模組；大量站點、熱點、路線與其他資料視覺層使用 Deck.gl，資料層與地圖控制面板不得綁在底圖生命週期內。
- 唯一允許的免費遠端底圖為 OpenFreeMap，host style 固定為 `https://tiles.openfreemap.org/styles/liberty`，且必須保留 OpenFreeMap／其資料來源要求的 attribution。
- 不使用任何需要帳務、信用卡、API key、按量計費或可能超額扣款的地圖 provider／API。此限制是架構邊界，不以「有免費額度」視為符合。
- OpenFreeMap style、tile、glyph、sprite 與相關第三方回應一律視為不可信輸入；限制可接受來源、處理載入錯誤，不讓第三方內容控制業務資料或控制面板。
- 不得把任務、預測、使用者資料、operator／task 識別碼或其他內部狀態放入底圖 style／tile／glyph／sprite URL、query string 或 request header。底圖請求只使用顯示地圖所需的公開範圍資訊。
- 遠端 style 或其資源載入失敗、逾時或斷網時，必須明確顯示底圖不可用，並切換至內建的 local empty MapLibre style（`no-basemap`）。Deck.gl 資料層、站點／路線資訊、控制面板與非地圖操作繼續運作；不得靜默留下空白或永久 loading。
- Google Maps 路線導航 URL 繼續保留，因其為使用公開座標組成的 plain navigation URL，不使用 Google Maps API key 或計費 API；不得附帶任務、使用者或預測資料。
- 完整承接 ADR-201 未被地圖選型取代的決策：JavaScript／JSX、React、Vite、React Router、Ant Design、ECharts、精確釘選直接依賴、Mock-first adapter、in-memory Demo mutation、Mock Demo 標示，以及 `/dashboard`、`/operator`、`/overview` 三路由。
- 本 ADR 是文件與架構定案；MapLibre／Deck.gl／OpenFreeMap、no-basemap 與三頁改版尚未在前端實作，backend／prediction 本輪不修改。

## 理由與判準

- MapLibre 提供可程式化 style 與 WebGL 地圖生命週期，Deck.gl 可將大量資料視覺層與底圖解耦，適合三頁共用的數位孿生視角。
- 單一共用 map 模組可集中處理來源白名單、attribution、載入錯誤、resize、layer lifecycle 與 no-basemap，避免三頁各自實作。
- OpenFreeMap provider 不產生直接費用且不需 API key；但本專案不保證其可用性、效能或第三方 SLA。
- local empty style 讓遠端故障不會遮蔽業務資料或阻斷控制操作，符合失敗可見與可降級原則。
- Google Maps plain navigation URL 保留既有外勤流程，同時不引入計費 API 或憑證。

## 考慮過的替代方案

### 延續 Leaflet

- 優點：既有三頁基線已可運作，遷移成本最低。
- 缺點：資料層、底圖與三頁共用生命週期較難形成一致的 WebGL 數位孿生架構。
- 未採用原因：owner 已核准改用 MapLibre + Deck.gl；ADR-201 因狀態不支援 partial supersede，須由本 ADR 完整取代並承接其保留決策。

### 商業地圖 provider 或有免費額度的計費 API

- 優點：可能提供 SLA、託管樣式、搜尋或路線服務。
- 缺點：需要帳務／信用卡／API key，可能按量計費或超額扣款，並增加憑證及成本治理。
- 未採用原因：違反零計費地圖與無 API key 的硬性限制。

### 只載入 OpenFreeMap、沒有 no-basemap

- 優點：實作較少。
- 缺點：斷網或第三方故障會造成空白、卡住或誤導，並可能連帶阻斷資料層。
- 未採用原因：違反失敗可見與業務功能持續運作要求。

## 影響與後果

### 正面

- 三頁共用一致的 MapLibre／Deck.gl 模組、圖層模型與降級策略。
- 底圖故障時仍能看見資料層、錯誤訊息並操作控制面板。
- 不需地圖 API key、帳務或信用卡，避免按量計費與憑證外洩風險。
- 底圖與 Deck.gl data／control 分離，後續可在不改 domain adapter 的情況下更換視覺層實作。

### 負面與代價

- 必須遷移既有 Leaflet 元件、事件模型、marker／route render 與測試。
- MapLibre + Deck.gl 增加 bundle、WebGL 資源管理與跨瀏覽器測試成本。
- OpenFreeMap 是外部遠端服務，**沒有本專案可依賴的 SLA**；可能有中斷、延遲、限流、樣式或資源路徑變更風險。
- provider 不產生直接費用且不需 key，不代表網路、託管、維運或第三方服務永遠無成本。

### 尚未解決

- MapLibre／Deck.gl 精確版本、bundle 分割與低階裝置效能基準。
- OpenFreeMap 來源允許清單、timeout 與錯誤 UI 的實作細節。
- local empty style 的實際檔案位置、視覺樣式與端到端斷網測試。
- 正式部署的 CSP、代理快取與第三方服務變更監測。

## 介面與相容性

- 頁面仍只透過 hooks 與 domain API modules 取得資料，Mock adapter／未來 FastAPI adapter 邊界不變；地圖元件只接收正規化後的 props。
- 新共用 map 模組對外提供底圖狀態、資料圖層、選取事件、viewport 與 no-basemap 狀態；三頁不得直接依賴 OpenFreeMap response shape。
- `/dashboard`、`/operator`、`/overview`、React Router、Ant Design、ECharts 與 Mock-first 行為維持相容。
- Google Maps `https://www.google.com/maps/dir/?api=1...` plain navigation URL 維持既有契約；不新增 Google Maps SDK 或計費 API。
- 既有 Leaflet 實作是已完成基線，但將由後續前端任務遷移；本文件不宣稱遷移已完成。

## 資安與隱私

- OpenFreeMap 遠端 style、tile、glyph、sprite 皆是不可信第三方輸入；須限制來源、驗證 URL scheme／host、設定逾時與錯誤處理，且不得動態執行其內容。
- 底圖請求不得包含任務、預測、操作員、使用者、token、內部 station payload 或其他敏感／業務資料；避免 query、path、referrer 與 log 外洩。
- 不配置地圖 API key，不把任何憑證放入前端 bundle、URL、版本庫或 log。
- attribution 必須持續可見，不得因 Deck.gl overlay、no-basemap 或控制面板遮蔽。
- Google Maps 導航只傳公開路線座標；若未來要加入 SDK、路線 API、key 或帳務，必須另立 ADR。

## 回復或取代方式

可把地圖來源切換為 local empty style 以停止依賴遠端底圖，資料層及控制面板應保持可用。若 MapLibre／Deck.gl 或 OpenFreeMap 不再適用，建立新 ADR 完整 supersede 本決策，明列保留的 React／Vite／Mock-first／三路由決策；不得回頭改寫 ADR-201 或本 ADR 的歷史。

## 驗證方式

- 三個固定路由皆只使用共用 MapLibre／Deck.gl 模組，無 Leaflet runtime 依賴。
- 正常網路下使用指定 OpenFreeMap liberty style，且 attribution 可見。
- 阻擋 style、tile、glyph、sprite 或完全斷網時，畫面顯示明確錯誤並進入 no-basemap；Deck.gl 資料層、清單、控制面板與操作仍可用。
- 網路檢查證明底圖請求沒有 API key、帳務識別、任務、預測或使用者資料。
- Google Maps navigation URL 可開啟，且沒有載入 Google Maps SDK／計費 API。
- production build、三頁 smoke test、來源白名單與降級測試通過後，才可宣稱前端遷移完成。

## 追溯

- 相關 commit：無；`related-commits: []`，目前只有文件決策。
- 相關 Spec／文件：`.kiro/specs/youbike-dispatch-system/requirements.md`、`design.md`、`tasks.md`。
- 相關 ADR：完整取代 ADR-201；沿用 ADR-005（契約先行與 Mock）、ADR-007（雙向信任邊界）、ADR-008（依賴釘選）。
