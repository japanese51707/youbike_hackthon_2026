---
status: superseded
date: 2026-09-02
decision-makers:
  - project-owner
approval-evidence: "2026-09-02 Kiro session：owner 明確核准採用 JavaScript/JSX、React/Vite、React Router、Ant Design、React-Leaflet/Leaflet、ECharts、Mock adapter 與三個固定路由"
scope:
  - frontend
  - dependencies
  - data-adapter
related-commits:
  - 98d3e8e
retrospective: false
supersedes:
superseded-by: ADR-202
---

# ADR-201：React／Vite Mock-first 前端架構

> **取代註記（2026-09-02）**：本決策已由 ADR-202 完整取代。Leaflet 保留為當時已核准並已實作的歷史；ADR-202 改採 MapLibre／Deck.gl／OpenFreeMap，並明確承接本 ADR 的 React／Vite／JSX／Router／Ant Design／ECharts／Mock adapter 與三路由決策。

## 背景與問題

前端目前只有符合 API 契約的 `mock_data.json`，尚無可執行骨架、路由、頁面或資料存取層。黑客松需要先完成 Dashboard、Operator App 與 Overview 三個可互動頁面，同時避免頁面直接依賴 JSON 結構，否則未來改接 FastAPI 時會散落修改。現階段使用者明確要求不連後端與資料庫。

## 決策

- 使用 JavaScript／JSX、React 與 Vite 建立單頁應用。
- 使用 React Router，固定提供 `/dashboard`、`/operator`、`/overview`；根路由導向 `/dashboard`。
- 使用 Ant Design 建立操作介面，React-Leaflet／Leaflet 顯示站點與路線，ECharts 顯示歷史及比較圖表。
- 所有 npm 直接依賴使用精確版本並提交 `package-lock.json`，不使用開放版本範圍。
- 頁面只經由 hooks 與 domain API modules 取得資料；API modules 再呼叫共用 Mock adapter 與 in-memory Mock store。頁面不得直接 import `mock_data.json`。
- Mock adapter 保持非同步介面，使未來 FastAPI adapter 可以在不改頁面的前提下替換。
- 確認建議、警示確認與任務進度只修改記憶體；重新整理後回到原始 Mock，不使用瀏覽器儲存空間假裝正式持久化。
- 不建立登入流程；角色與頁面切換只供 Demo 導覽，不能宣稱為授權控制。
- 所有頁面明確標示 `Mock Demo`，不得將 Mock 的 `data_freshness: live` 宣稱為真實即時資料。
- 本決策不修改 backend、資料庫、API Schema、Docker Compose、AWS 或正式部署方式。

## 理由與判準

- Vite 能以最小設定快速建立黑客松可展示的 React 應用。
- JavaScript／JSX符合現有 Spec 命名並縮短交付時間。
- adapter 邊界延續 ADR-005 的契約先行原則，避免頁面與資料來源耦合。
- Ant Design、Leaflet 與 ECharts 能覆蓋表格、抽屜、地圖與視覺化需求，降低自製元件成本。
- 記憶體 mutation 清楚表達 Demo 性質，不製造已有正式資料庫或同步機制的錯覺。

## 考慮過的替代方案

### TypeScript

- 優點：跨模組契約與重構具有較強的靜態檢查。
- 缺點：目前需要額外建立完整型別層，增加黑客松交付範圍。
- 未採用原因：owner 本階段明確核准 JavaScript／JSX；未來若全面遷移需建立新 ADR。

### 頁面直接 import Mock JSON

- 優點：初始程式碼最少。
- 缺點：資料 shape、查詢與 mutation 會散落在頁面，切換 FastAPI 時需逐頁修改。
- 未採用原因：違反 ADR-005 的穩定契約與可替換邊界。

### 現在直接串接 FastAPI

- 優點：可提早發現端到端整合問題。
- 缺點：會把目前任務擴大到後端啟動、身分與資料庫生命週期。
- 未採用原因：owner 明確要求此階段為 Mock-only。

### 使用 localStorage 持久化 Demo 操作

- 優點：重新整理後仍保留操作結果。
- 缺點：容易讓展示者誤認為已有正式持久化與多使用者一致性。
- 未採用原因：記憶體重置更能清楚呈現目前能力邊界。

## 影響與後果

### 正面

- 三個角色視角可以獨立開發、展示並共用一致資料層。
- 未來新增 FastAPI adapter 時，頁面與大部分 hooks 不需修改。
- 操作狀態與錯誤處理集中，不會由各頁自行猜測資料格式。

### 負面與代價

- Ant Design、Leaflet 與 ECharts 會增加初始 bundle 大小。
- JavaScript 缺少 TypeScript 的編譯期契約檢查。
- Mock mutation 不會跨重新整理或跨瀏覽器分頁保存。
- OpenStreetMap 圖磚需要網路；斷網時業務資料可顯示但底圖可能不可用。

### 尚未解決

- FastAPI base URL、身分 token、錯誤映射與重試策略。
- Production build 的 CDN／Nginx／容器部署方式。
- 完整帳號登入、session 與後端授權整合。
- 全量站點下的地圖效能、marker clustering 與 bundle 分割。

## 介面與相容性

頁面依賴 domain API modules 回傳的 Promise，不依賴資料來自 JSON 或 HTTP。Mock adapter 以既有 `frontend/src/mock/mock_data.json` 作為單一初始資料。未來 FastAPI adapter 必須維持相同方法語意與錯誤可見性；若 API 契約需要改動，依 ADR-005 另行協調並記錄。

## 資安與隱私

- 前端導覽與按鈕不構成授權；敏感操作仍須依 ADR-007、ADR-010 由後端驗證。
- 不加入 API key、密碼、token、PII 或真實操作員資料。
- OpenStreetMap 圖磚請求只包含公開地圖範圍；Google Maps 導航連結只使用公開站點座標，不附帶帳號或任務身分。
- 未來 HTTP adapter 必須把第三方與後端回應視為不可信輸入，並限制錯誤資訊外洩。

## 回復或取代方式

可刪除新增的 `frontend` 骨架回復到只有 Mock JSON 的狀態，不影響 backend。若要改用 TypeScript、其他 UI／地圖框架或直接服務端渲染，建立新 ADR supersede 本決策，不直接改寫歷史。

## 驗證方式

- 使用精確依賴安裝並產生 lockfile。
- `npm run build` 成功產生 production bundle。
- 三個固定路由可載入，根路由會導向 Dashboard。
- Dashboard、Operator、Overview 的資料皆可追溯至 Mock JSON，且瀏覽器不呼叫 FastAPI。
- 確認建議、確認警示與完成停靠點會更新記憶體畫面，重新整理後重置。
- 手動檢查桌面與手機寬度、地圖、圖表、錯誤與空狀態。

## 追溯

- 相關 commit：`98d3e8e`（React／Vite Mock-first 三頁前端與可替換 adapter 實作）。
- 相關 Spec：`.kiro/specs/youbike-dispatch-system/design.md`、`.kiro/specs/youbike-dispatch-system/api_contract.md`、`.kiro/specs/youbike-dispatch-system/tasks.md`。
- 相關 ADR：ADR-005（契約先行與 Mock）、ADR-007（API 邊界）、ADR-008（依賴釘選）、ADR-010（Demo 身分限制）。
