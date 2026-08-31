# Repository Instructions

給在此 repo 工作的 AI coding agent（Codex、Kiro 等）的指令。

## 專案脈絡
- 動架構或實作決策前，先讀 `.kiro/specs/youbike-dispatch-system/` 的四份 Spec + `design.md`
- 讀 `.kiro/steering/development_principles.md`（開發規範）
- 標為「待決策 / 待團隊定義」的選項視為未定，**不要靜默鎖定**某個框架/AWS 服務/部署方式
- 團隊選定架構時，在 `docs/decisions/` 記錄 ADR
- **LLM/AI 只做估計，確定性規則引擎才能做調度決策**（核心約束，不可違反）
- 所有站點資料應可追溯來源（TDX / YouBike 官方源）

## 安全（本 repo 若公開）
- 絕不加入真實憑證、PII、私人使用者資料
- 每次 `git push` 前跑 secrets 掃描（見 CONTRIBUTING.md / steering §12.1）
- 大型原始資料（Parquet、PDF）不進 Git，除非團隊明確決定
- 資安雙向考量：入向（別人打我）+ 出向（我打別人/別人回我），見 steering §11

## 與既有變更協作
- 編輯或 stage 前先 `git status`
- 把既有修改當成使用者所有，除非是當前任務造成的
- 保留無關的變更，不要 stage/revert/刪除它們
- 每次改動聚焦單一任務

## 核准閘門
除了單純文件/樣板，動任何檔案前保持唯讀，先說明計畫（目標、影響檔案、架構影響、風險、驗證指令），等使用者核准。詳見 steering §12.2。

## 驗證
- 跑最窄的相關測試/linter/formatter
- commit 前跑 `git diff --check`
- 沒實際跑過的檢查，不宣稱通過

## Commit
- Conventional Commits 格式（見 CONTRIBUTING.md）
- 未經明確要求不 commit/push
- 不直接改 `main` 分支
