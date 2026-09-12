---
status: accepted
date: 2026-09-12
decision-makers:
  - project-owner
approval-evidence: "2026-09-12 Codex 對話：owner 要求依圖庫改品牌風格及日夜模式，閱讀含修改範圍／新設計 ADR／驗證方式的計畫後回覆『好』。"
scope:
  - frontend
  - design-language
  - map-presentation
related-commits: []
retrospective: false
supersedes: ADR-205
superseded-by:
---

# ADR-208：YouBike 品牌識別、日式柔和介面與日夜主題

## 背景與問題

owner 提供 `圖庫/` 的 Logo、黃白橘配色、四類站點圖釘與電輔車閃電參考，要求目前前端對標品牌並呈現日式、柔和、精練的日光／夜間模式。原 ADR-205 承接的深藍灰／亮綠暗色限定設計與本需求不同。

## 決策

- 以本 ADR 取代 ADR-205 的設計語言，承接其角色導向資訊架構、預設調度頁、無頁面捲動與其餘未變約束；ADR-206 決策流、ADR-207 API 整合及後續有效契約繼續適用。
- 使用 owner 提供的 Logo 原檔，保持比例與原色；白底容器提供夜間清晰度。參考截圖的黃／橘作品牌基準，衍生暖白與暖炭灰介面，並非宣稱截圖取色是正式品牌規範色碼。
- 全站共用 ThemeProvider 與 `theme/palettes.js`，包括 Ant Design、CSS、圖表、地圖與提示框。支援日光、夜間、跟隨系統；預設跟隨系統，localStorage 僅儲存外觀偏好，儲存失敗時顯示提醒。
- 地圖更新既有 style 的 paint 顏色；切換不重新建立 Map、不改視角、篩選、抽屜或派工草稿。OpenFreeMap 同源限制、attribution、離線降級保持有效。
- 用專案 SVG 圖釘對齊參考圖：正常租借綠、無車可借橘、車位滿載紅、停運灰，弧線數代表可借比例。low／high 在租借狀態圖層仍屬可租借，原欄位與調度排序維持不變；使用率分析另有量尺與圖例。
- 電輔車左上閃電僅在有確定正數 `available_electric_bikes` 時呈現。此為可選前端呈現能力，現行 API 未供應，不能由一般車數、站名、車種支援或總容量推測；不新增後端欄位或偽造展示數字。
- 維持 React／Vite／Ant Design／ECharts／MapLibre／Deck.gl；不新增套件或遠端字型。

## 理由與替代方案

採用完整共用主題可避免卡片變亮但地圖、浮層或圖表仍固定深色。僅調 CSS 的方案維護成本低但無法涵蓋 canvas/WebGL。直接裁切參考截圖作圖釘會包含背景、放大模糊，因此使用程式繪製的 SVG；Logo 保留原檔。

## 影響與後果

正面：品牌與站況識別一致；日夜外觀可切換；減少發光、強漸層與過重陰影。
代價：必須一併驗證兩種主題、地圖資源失效與手機尺寸。飽和站況色保留識別，但一般文字使用符合對比的深／淺色。
限制：目前沒有電輔車可借數；本次提供圖示及條件渲染，不宣称已接入即時電輔車資料。

## 介面、資安與隱私

只調整前端呈現；後端 API、Schema、派工 payload、規則引擎、權限與部署不變。地圖第三方資源沿用來源 allowlist；文字提示持續視為不可信輸入並 escape。偏好儲存不含身分或站點資料。

## 回復方式

按本次任務差異回復前端檔案及素材；不得覆蓋 owner 原有未提交修改。未來改變設計方向以新 ADR 取代本記錄。外觀維護由前端 owner 負責，色票入口是 `frontend/src/theme/palettes.js`。

## 驗證方式

`npm run build`；`node --test src/theme/*.test.js src/utils/*.test.js src/api/*.test.js`；`git diff --check`。瀏覽器檢查桌機／手機、模式切換持久化、系統外觀、四種標記、地圖視角保留、站點抽屜及既有流程。實際執行結果另見前端外觀交付紀錄。

## 追溯

- owner 本次對話提出需求，收到具體範圍與驗證計畫後回覆「好」。
- 相關 ADR：ADR-205、ADR-206、ADR-207、ADR-303；不新增實作 commit。
