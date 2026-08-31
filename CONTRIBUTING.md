# 貢獻指南（Contributing）

本文件記錄協作與 commit 規範。三人協作，請遵守以避免互相踩線。

---

## 分支策略

```
main              # 穩定版，只接 merge（PR），不直接 push
dev               # 整合開發分支
feature/A-xxx     # A 的功能分支（例：feature/A-rule-engine）
feature/B-xxx     # B 的功能分支（例：feature/B-predictor）
feature/C-xxx     # C 的功能分支（例：feature/C-dashboard）
```

規則：
- **不直接 push 到 main**
- 各自在 `feature/角色-功能` 分支開發，完成發 Pull Request
- 由 **A（PM）** review + merge，解決衝突
- 一個 feature 分支聚焦一個任務（對應 tasks.md 的一個項目）

---

## Commit 訊息規範（Conventional Commits）

格式：
```
<type>(<scope>): <summary>

<body>（可選，說明為什麼）
```

### type
| type | 用途 |
|------|------|
| feat | 新功能 |
| fix | 修 bug |
| docs | 只改文件 |
| refactor | 重構，不改行為 |
| test | 測試 |
| chore | 工具/設定/依賴 |
| data | 資料、fixtures、seed |

### scope（用最窄的模組）
```
repo / frontend / backend / api / schemas / core / prediction /
params / rules / data / infra / docs
```

### summary 規則
- 英文、祈使句、≤72 字、結尾不加句號、描述單一改動

### 範例
```
feat(prediction): add quantile interval to predictor
feat(api): add emergency override endpoint
fix(rule_engine): use lower_bound instead of point estimate
docs(model): clarify LightGBM is not generative AI
data(s3): upload raw csv to raw_csv prefix
```

避免：`update files` / `fix bug` / `finish frontend` 這類模糊訊息。

---

## Push 前檢查（必做）

### 1. Secrets 掃描（本 repo 雖 private，仍禁止 commit 密鑰）
```bash
git diff --cached --name-only | xargs grep -lE \
  '(AKIA[0-9A-Z]{16}|sk-[a-zA-Z0-9]{20,}|AWS_SECRET_ACCESS_KEY|PRIVATE.KEY)' \
  2>/dev/null && echo "BLOCKED: secrets detected" && exit 1 || echo "OK: no secrets"
```
有 match 就不 push，改用 `.env`（已 gitignore）。

### 2. 不 commit 的東西
- 密鑰、`.env`、憑證
- 大型資料（`output/`、`youbike資料集/`、`*.parquet`、`*.csv`）→ 放 S3
- `.venv/`、`node_modules/`

### 3. commit 前
```bash
git status              # 確認只改了該改的
git diff --check        # 檢查空白/衝突標記
```

---

## 核准閘門（AI agent 或大改動）

除了單純文件/樣板，動架構/API/schema 前先說明計畫、列出影響檔案、等 owner 核准。詳見 `AGENTS.md`。

---

## 架構決策（ADR）

在文件標為「待決策」的選項中做出選擇時，於 `docs/decisions/` 記一份 ADR（決策、理由、替代方案）。避免決策只存在某人腦中。

---

## 核心約束（不可違反）

- **LLM/AI 只做估計，確定性規則引擎才做調度決策**
- 規則引擎吃預測**區間下界**，不吃點估計
- 所有調度指令走「預覽 → 確認 → 執行 → 驗證」閘門
- 所有閾值/權重放 `config.yaml`，不寫死在程式碼
