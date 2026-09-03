---
status: accepted
date: 2026-09-02
decision-makers:
  - project-owner
approval-evidence: "2026-09-02 Kiro session：owner 核准前端先以 Mock 實作 Past／Live／Predict、固定展示 +30／+60 並保留 dynamic ETA；後續明確要求只把前端可獨立修改的內容列入修改範圍，API／Schema／prediction／Alert／fallback／dispatch 契約改列待決策"
scope:
  - frontend
  - temporal-presentation
  - mock-data
related-commits: []
retrospective: false
supersedes:
superseded-by:
---

# ADR-013：Past／Live／Predict 前端呈現與 Mock-first

## 背景與問題

三個前端頁面需要用一致方式呈現已發生、目前狀態與短期預測，並讓 C 能在不等待 A／B 修改共同契約的情況下先完成 Demo。固定 +30／+60 適合畫面比較，但既有調度流程另有 dynamic ETA；若前端混用兩者，可能讓展示資料被誤認為正式派遣依據。

本次只決定前端呈現與 frontend-local Mock 行為。共同 API、Schema、B 的模型介面、Alert、fallback 與 dispatch 行為會影響其他 owner，尚未取得逐項核准，不在本 ADR 中定案。

## 決策

- `/dashboard`、`/operator`、`/overview` 可用 **frontend-local Mock** 呈現 **Past／Live／Predict** 三段視圖：
  - **Past**：本地 Mock 提供的歷史觀測資料。
  - **Live**：本地 Mock 中目前選定的最新站況；畫面必須標示 `Mock Demo`，不得宣稱為真實即時資料。
  - **Predict**：本地 Mock 提供固定 `+30`、`+60` 兩個展示點。
- 固定 `+30`／`+60` 僅是 UI 展示網格，不取代既有 dynamic ETA，也不得被前端送入確認派發、任務建立或其他真實世界操作。
- frontend-local Mock／view model 與正式共同 API 契約分離。欄位名稱、資料正規化與 mapping 可由 C 在前端模組內調整，但不得宣稱該 shape 已是 A／B 必須實作的 API 或模型介面。
- 固定展示點缺值或 Mock 模擬失敗時，UI 必須明確顯示「不可用」，不得插值、複製前一點或用 dynamic ETA 補洞；本 ADR 不規定共同 `error_code` Schema。
- 前端 Demo 的本地 Mock 可使用 `Asia/Taipei`／`+08:00` 產生可重現的時間範例；這只約束 Mock fixture 與顯示測試，不決定 backend timestamp 格式、欄位 ownership 或全系統時區契約。
- 沿用 ADR-012 的 MapLibre／Deck.gl／OpenFreeMap 與 `no-basemap`；預測資料不得被送往底圖 provider 或 Google Maps navigation URL。
- 本輪只更新文件，不修改 backend、prediction、共同 Schema、正式 API 或現有調度規則。

## 理由與判準

- C 可以先完成畫面流程，不需替 A／B 鎖定尚未核准的跨人介面。
- 固定展示點與 dynamic ETA 明確分離，可避免 UI convenience 反向改變派遣決策。
- frontend-local view model 保留 mapping 空間；未來共同契約定案時，前端可在 adapter 層轉換，而不是假設兩者天然相同。
- 缺值直接顯示不可用，符合失敗可見且不捏造資料的原則。

## 考慮過的替代方案

### 立即定義 v4 API／Schema 與 prediction interface

- 優點：A／B／C 可直接依同一新格式實作。
- 缺點：會同時改動其他 owner 的工作邊界，且多項欄位、錯誤與 fallback 語意尚未核准。
- 未採用原因：owner 要求本輪只保留前端可獨立修改範圍。

### 只保留 dynamic ETA，不做固定展示點

- 優點：不需新增前端展示 view model。
- 缺點：不同站點的 horizon 不一致，不利三頁用同一視覺網格比較。
- 未採用原因：owner 已核准前端固定展示 +30／+60，並要求保留 dynamic ETA。

### 缺值時由前端插值

- 優點：曲線看起來連續。
- 缺點：會產生沒有模型或資料證據的數值。
- 未採用原因：違反失敗可見與不可捏造原則。

## 影響與後果

### 正面

- 前端可獨立完成三段時序畫面與 Mock Demo。
- 不要求 A／B 按未核准格式實作，降低跨人衝突。
- 固定展示與派遣 ETA 的用途不會混淆。

### 負面與代價

- frontend-local Mock 未必與未來正式 API 同形，之後可能需要 adapter mapping。
- 目前只能驗證畫面行為，不能宣稱 backend 或 prediction 已支援固定 +30／+60。
- 共同時間、錯誤與 fallback 契約未定，端到端整合仍有待辦。

## 待決策（不可作為 A／B 實作依據）

以下項目需要 owner／團隊另行核准 ADR 或更新共同契約；在定案前不得寫成 A／B 任務或完成條件：

- backend 是否新增 `ForecastPoint`／`StationForecast`，以及其正式欄位與驗證規則。
- `GET /stations/{id}` 未來 response shape，以及是否／如何承載 fixed forecast 與 dynamic dispatch prediction。
- B 的 `predict()` 是否改成 discriminated `PredictionEstimate`，以及 fixed／default／dynamic horizon 的呼叫方式。
- 是否新增 `Alert.error_code`、錯誤代碼 taxonomy、重試語意與 prediction unavailable 的對外方式。
- historical fallback 應選最近一筆 observation、同時段平均或其他策略。
- default alert 是否使用獨立規則，以及它與 dispatch urgency／rule engine 的分流方式。
- dynamic dispatch context 應由哪個 endpoint、request 或控制平面狀態提供。
- backend 是否強制 timestamp 帶 offset；`timestamp`、`source_timestamp`、timezone 與 freshness 的 ownership 及對齊規則。
- 固定預測失敗時 backend／prediction 是否保留 slot、回 null、回錯誤物件或採其他契約。

## 介面與相容性

- 不修改現行 `api_contract.md`、`model_architecture.md`、`parameter_groups.md`、Pydantic Schema、backend endpoint 或 B 的 `predict()`／`calc_urgency()`。
- frontend-local Mock 是 UI view model，不是共同 API contract；未來正式資料接入時可能需要 mapping，不能保證只替換 transport adapter 就完成整合。
- 既有 dynamic ETA 與人工確認閘門維持原狀。固定 +30／+60 展示資料不得進入派遣操作 payload。

## 資安與隱私

- Mock 不得包含真實 PII、operator／task 身分、token 或憑證。
- 前端不得把站點預測、任務或使用者資料送往 OpenFreeMap、Google Maps navigation URL、分析追蹤或其他第三方服務。
- 所有未來正式 API 回應仍應視為不可信輸入；具體 Schema 驗證待共同契約定案。

## 回復或取代方式

可移除 frontend-local Past／Live／Predict view model 與 UI，不影響 backend、prediction 或現有共同契約。待跨人介面定案時，建立新的 proposed ADR 或 superseding ADR，經 owner 核准後再同步 API／Schema／model 文件與 A／B／C 任務。

## 驗證方式

- 三個頁面可清楚區分 Past、Live、Predict，且 Mock 模式有可見標示。
- Predict 固定顯示 +30／+60；任一點缺值時顯示不可用，不插值或借用 dynamic ETA。
- 前端操作檢查證明固定展示資料不會進入派遣確認或任務建立 payload。
- Mock fixture／view model 測試可在不啟動 backend／prediction 的情況下執行。
- repository diff 證明本輪未修改共同 API、Schema、prediction、Alert、fallback 或 dispatch 契約文件與實作。

## 追溯

- 相關 commit：無；`related-commits: []`，目前只有文件決策。
- 相關 Spec／文件：`.kiro/specs/youbike-dispatch-system/requirements.md`、`design.md`、`tasks.md`。
- 相關 ADR：ADR-004（AI 只估計、規則引擎決策）、ADR-005（契約先行與 Mock）、ADR-012（三頁地圖架構）。
