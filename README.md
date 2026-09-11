# YouBike 智慧調度系統

第二批真實資料／前後端整合已完成，啟動方式、驗證與目前限制見 [服務整合說明](docs/analysis/service_integration_phase2_20260911.md)。

新北市交通局黑客松（2026/09/12）參賽專案。以歷史資料建立**預測 + 規則引擎 + 智慧調度**系統，讓 YouBike 站點調度從「事後補救」變成「事前預防」。

> 本專案目前處於規劃/開發期。技術棧與部分參數仍在調整，見各文件標註的「待定」項。

---

## 問題

YouBike 調度員常常在站點已經空/滿後才發現，被動反應、依賴個人經驗，尖峰時多站同時出問題也不知道先處理哪站。現行機關系統**沒有主動警示功能**。

## 解法

1. **預測**每站未來（調度員到得了的時間點）的可借車數 + 不確定區間
2. **規則引擎**用預測區間下界判斷是否觸發調度（AI 只估計，規則做決策）
3. **智慧調度**排優先級、位置導向派車、動態轉派
4. **即時視覺化**熱點地圖 + 多維度切換 + 時間軸
5. **警示通知**（★題目明確要求，現行系統沒有）

---

## 核心設計原則

- **AI 只做估計，規則引擎做決策，人在迴圈確認** — 預測可失手，判斷不跟著失手
- **單一模型 + 分層參數** — 一個 LightGBM 模型 + 每站條件參數（非 1583 個模型）
- **模型是傳統 ML（LightGBM），非生成式 AI** — 本機運行、推論免費、毫秒級（見 `docs/模型怎麼跑的（給隊友）.md`）
- **模組化** — 一個檔案一件事，改一處不毀他處
- **所有閾值外部化** — 集中在 `config.yaml`

---

## 架構

```
資料源（歷史Parquet / TDX即時 / 天氣）  ← data_source 可抽換
        ↓
執行平面（B）：預測模型 + 緊急度 + 調度辨識 + 每日最適化
        ↓
控制平面（A）：規則引擎 + 調度 + 任務管理 + 警示 + 覆寫
        ↓
API 層（A，FastAPI）
        ↓
前端（C，React）：後台儀表板 / 調度員 App / 長官總覽
```

視覺化架構圖：`design_dataflow_v2.drawio`（用 draw.io 開）

---

## 技術棧

| 層 | 技術 |
|----|------|
| 後端 | FastAPI (Python) |
| 預測模型 | LightGBM |
| 前端 | React + Vite + Leaflet + ECharts + Ant Design |
| 資料 | AWS S3 + Glue + Athena |
| 部署 | Docker + docker-compose；EC2 Free Tier |

---

## 文件導覽

| 文件 | 內容 |
|------|------|
| `.kiro/specs/youbike-dispatch-system/requirements.md` | 需求規格（13 FR + 10 NFR） |
| `.kiro/specs/youbike-dispatch-system/api_contract.md` | API 契約（12 Schema + 端點 + 三人分工） |
| `.kiro/specs/youbike-dispatch-system/model_architecture.md` | 模型三層參數架構 |
| `.kiro/specs/youbike-dispatch-system/parameter_groups.md` | 五大參數群組 + 因子角色 |
| `.kiro/specs/youbike-dispatch-system/design.md` | 系統設計（檔案結構/資料流/資安/schema） |
| `.kiro/specs/youbike-dispatch-system/tasks.md` | **三人任務清單（先看這個開工）** |
| `AGENTS.md` | 給 AI agent 的 repo 規則 |
| `CONTRIBUTING.md` | commit 規範 + 分支策略 |
| `docs/資料存放說明.md` | 資料在 S3 哪裡、怎麼拿 |
| `docs/模型怎麼跑的（給隊友）.md` | 模型白話說明 |
| `docs/decisions/` | 架構決策紀錄（ADR） |

---

## 三人分工

| 角色 | 負責 |
|------|------|
| **A**（PM） | 後端 API + 控制平面（規則引擎/調度/警示）+ 整合 + Git |
| **B**（空間工程師） | 預測模型 + 緊急度 + 地理參數 + 每日最適化 |
| **C**（品質工程師） | 前端三頁面（儀表板/調度員/總覽）+ 視覺化 |

詳見 `tasks.md`。開發鐵則：介面契約先行，各自用 mock 開發不互相等。

---

## 快速開始（開發環境）

> 目前後端/前端骨架尚未建立（Task A0/C0），以下為預計流程。

```bash
# 1. 取得程式碼
git clone https://github.com/japanese51707/youbike_hackthon_2026.git
cd youbike_hackthon_2026

# 2. 環境變數（跟 A 拿臨時憑證）
cp .env.example .env   # 填入 AWS/API 憑證

# 3. 取得資料（從 S3，見 docs/資料存放說明.md）
aws s3 sync s3://youbike-hackathon-2026/youbike_data/ ./data/youbike_parquet/

# 4. 後端（A0 完成後）
cd backend && pip install -r requirements.txt && uvicorn main:app --reload

# 5. 前端（C0 完成後）
cd frontend && npm install && npm run dev
```

---

## 資料

- 不進 Git（太大）。原始 CSV + 整合 Parquet 都在 **S3**：`s3://youbike-hackathon-2026/`
- 詳見 `docs/資料存放說明.md`

---

## 安全

- 本 repo **private**。仍禁止 commit 密鑰（見 `AGENTS.md` / `CONTRIBUTING.md`）
- push 前跑 secrets 掃描
- 大型資料、`.env`、`.venv` 已 gitignore
