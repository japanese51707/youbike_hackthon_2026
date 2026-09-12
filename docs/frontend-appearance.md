# YouBike 前端外觀交付（2026-09-12）

右上方可選日光、夜間與跟隨系統；偏好僅存瀏覽器 localStorage。重新整理或換頁後保留。瀏覽器拒絕儲存時，本次畫面仍可切換，並提示偏好無法儲存。

- 品牌 Logo：`frontend/src/assets/brand/youbike-logo.png`，由 owner 圖庫原檔複製，保留比例與原色。
- 色票：`frontend/src/theme/palettes.js`；Ant Design 與 CSS token 由 `ThemeProvider.jsx` 套用。
- 版面細節：`frontend/src/styles/brand.css`；既有 `app.css` 保留結構，固定色替換成日夜 token。
- 站點配色：`config/presentation.json`；租借語意由 `utils/stationAppearance.js` 映射，不改後端狀態或調度排序。
- 電輔車：僅有確定的正數 `available_electric_bikes` 才顯示閃電。現行 API 未供應此數，不由站名或一般可借數推測。
- 地圖：切換外觀只修改 paint，保留視角、站點抽屜、組單草稿；底圖仍是 OpenFreeMap，自動離線降級保留資料圖層與操作區。

## 驗證

建置與測試指令（在 frontend 執行）：

```sh
npm run build
node --test src/theme/*.test.js src/utils/*.test.js src/api/*.test.js
```

已完成 18 項單元測試，涵蓋原派工閘門／HTTP／文字 escape，加上外觀偏好、文字對比、站況映射、電輔車缺值、SVG 快取與底圖色彩切換。

瀏覽器以明確 Mock 模式檢查 1440 × 1000 桌機、390 × 844 手機的日夜畫面；五個路由在桌機皆可開啟，手機驗證調度、司機、長官、孿生頁。無頁面橫向溢出、無 JavaScript runtime exception；確認切換／重新整理偏好、系統模式、地圖 canvas 保留、抽屜／Mock 組單草稿保留與離線降級。

範圍限制：瀏覽器未送出真實派工；最適化審核採服務不可用狀態檢查。電輔車即時數仍待後端資料；地圖與圖表的大型 bundle 警告仍存在，本次未調整依賴或拆包。

維護由前端 owner 接手；設計依據見 `docs/decisions/ADR-208-YouBike品牌識別與日夜主題.md`。
