# 歸檔區（archive）

存放已被取代或已完成的舊檔案，分類保存供日後回查。**這裡的東西不再更新**，現行版本在根目錄或 `.kiro/`。

## diagrams_old/ — 舊架構圖
被 `design_dataflow_v2.drawio`（現行，在根目錄）取代。
- `design_dataflow.drawio` — 資料流圖 v1
- `system_architecture.drawio` — 最早的系統架構圖 v1
- `system_architecture_v2.drawio` — 系統架構圖 v2

## reviews_round1/ — 第一輪審查與交接（已完成）
第一輪審查 → 交接 → 實作的完整紀錄。第二輪審查（`review_architecture_v2.md`）在根目錄。
- `review_prompt.md` — 第一輪給審查者的提問稿
- `review_claude_回覆.md` — 第一輪審查回覆
- `handoff_to_kiro.md` — 第一輪交接指令
- `kiro_實作回報.md` — 第一輪實作回報

## poc_backup/ — PoC 回滾備份
動態版遷移前的死數字版本，保留供回滾。現行版在根目錄（`config.yaml` / `rule_engine.py`）。
- `config.poc_v1.yaml`
- `rule_engine.poc_v1.py`
