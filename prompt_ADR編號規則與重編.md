# 給 Kiro 的指令：建立 ADR 編號規則並重編本分支 ADR

> 用途：貼給 Kiro（或任何在此 repo 工作的 coding agent）
> 目標分支：`general-purpose-model`
> 建立日期：2026-09-04

---

## 貼給 Kiro 的內容（以下整段複製）

```
請先讀 AGENTS.md、.kiro/steering/decision_governance.md、docs/decisions/README.md，
再開始這個任務。

## 背景

本 repo 目前有兩條分支平行新增 ADR，且互不知情地從 ADR-010 之後接續編號，
造成編號撞號：

  編號        本分支（general-purpose-model）      feat/front-end-ver1 分支
  ADR-011     預測特徵因子模組化與資料源            React-Vite-Mock-first 前端架構
  ADR-012     擴充特徵時間POI事件特殊天氣           MapLibre-DeckGL-OpenFreeMap 地圖架構
  ADR-013     時序自身鄰近連動營運面因子            Past-Live-Predict 時序契約
  ADR-014     站點行為指紋與需求密度分層            數位孿生戰情室設計語言與暗色底圖

檔名不同（標題不同），所以 git merge 不會報衝突，會兩份都留下，
合併後 docs/decisions/ 會同時出現兩個 ADR-011、兩個 ADR-012、兩個 ADR-013、兩個 ADR-014。
decision_governance.md 要求「找出並讀取與任務相關的 accepted ADR」——
編號一撞，引用 ADR-013 時無法判斷是哪一份，治理即失效。

owner 已決定改用分段編號制，並要求由本分支負責：
（a）建立編號規則本身
（b）重編本分支自己的 ADR-011~020

前端分支的 ADR 由 C 自行重編，本次不處理，但規則要先把號段預留給他。

## 決定採用的編號規則

  ADR-000        編號規則本身（meta，不屬任何號段）
  ADR-001~010    已封存的基礎決策，保留原號，此號段不再新增
  ADR-1xx        模型／資料／預測              owner: A、B
  ADR-2xx        前端／視覺化／UX              owner: C
  ADR-3xx        平台／部署／資安／API 契約     owner: A

各號段從 x01 開始遞增。

### 本分支的重編對照（必須完全照這張表）

  ADR-011-預測特徵因子模組化與資料源.md      → ADR-101-...
  ADR-012-擴充特徵時間POI事件特殊天氣.md     → ADR-102-...
  ADR-013-時序自身鄰近連動營運面因子.md      → ADR-103-...
  ADR-014-站點行為指紋與需求密度分層.md      → ADR-104-...
  ADR-015-目標變數定義與截斷樣本處理.md      → ADR-105-...
  ADR-016-調度標註離線與線上分離.md          → ADR-106-...
  ADR-017-多視野預測與累積分位數.md          → ADR-107-...
  ADR-018-資料品質與站點主檔處理.md          → ADR-108-...
  ADR-019-流量加權訓練與決策層信心.md        → ADR-109-...
  ADR-020-超參數優化與時序交叉驗證.md        → ADR-110-...

標題文字一律不變，只改編號。

### ADR-000 中要預留登記（本次不建立這些檔案）

  ADR-201  React-Vite-Mock-first 前端架構        （原 ADR-011，待 C 分支落實）
  ADR-202  MapLibre-DeckGL-OpenFreeMap 地圖架構  （原 ADR-012，待 C 分支落實）
  ADR-203  Past-Live-Predict 時序契約            （原 ADR-013，待 C 分支落實）
  ADR-204  數位孿生戰情室設計語言與暗色底圖       （原 ADR-014，待 C 分支落實）

## 硬性約束

1. **ADR-001~010 一個字都不准動。** 它們是 accepted，且被 commit message、
   commit-decision-map.md 與既有文件引用。重編會讓所有既有引用變成死連結，
   也違反 decision_governance「不得自行覆寫 accepted 決策」。

2. **不准改寫 git 歷史。** 分支已推遠端，不得 rebase、不得 amend 已推的 commit。
   已推 commit message 裡的舊編號（例如「ADR-016 落地」）保持原樣，
   改為在 commit-decision-map.md 補一張「舊號 → 新號」對照表來維持可追溯性。

3. **不准碰 feat/front-end-ver1 分支的任何內容。**

4. **檔案改名一律用 `git mv`**，保留檔案歷史。

5. **未經明確要求，不 commit、不 push、不切分支。**

## 執行分兩個閘門，不要一次做完

### 閘門 1：只出計畫 + 建立 proposed ADR-000

這一步**不得修改任何既有檔案**，只新增 docs/decisions/ADR-000-ADR編號規則與號段配置.md，
status 一律先寫 `proposed`（依 decision_governance，只有 owner 核准後才能改 accepted）。

ADR-000 內容需包含：
- 背景：兩分支撞號的具體事實
- 決策：上述號段表 + 各段 owner + 「001~010 封存不動」
- 已配發登記表：101~110（本分支）、201~204（保留給 C）
- 取號流程：新增 ADR 前先查 ADR-000 的登記表取下一個可用號，並在同一次變更中登記
- 驗收指令（見下）
- 考慮過的替代方案：續用流水號（否決：多分支必撞）、依合併先後補號（否決：改的人要理解別人的決策語意）

同時在計畫中寫出：
- ADR 判斷：本任務屬「跨模組共用慣例」，依 decision_governance 第二節需新增 ADR → 即 ADR-000 本身
- 先跑 `git status`，列出既有未提交變更並保留
- 完整受影響檔案清單。請你自己 grep 確認，不要照抄我下面的數字：
  我量到本分支 ADR-011~020 共出現約 221 處、橫跨 27 個檔案，
  其中 22 個是 backend/**/*.py（多在 docstring 內）。若你查到的不同，以你查到的為準。
- 風險與回復方式
- 驗證指令

停在這裡，等 owner 核准，不要往下做。

### 閘門 2：owner 核准後才執行重編號

核准後才做，且要照這個順序：

1. ADR-000 status 改為 accepted，補上 approval-evidence
2. `git mv` 十個檔案（011~020 → 101~110）
3. 改各 ADR 檔內的 frontmatter `name` 與內文標題
4. 全 repo 掃描並更新交叉引用，範圍至少包含：
   - docs/decisions/ 內其他 ADR 的交叉引用、supersedes / superseded-by
   - docs/decisions/README.md 索引
   - docs/decisions/commit-decision-map.md（並新增舊號→新號對照表）
   - docs/CHANGELOG.md
   - .kiro/specs/youbike-dispatch-system/ 全部（api_contract.md、tasks.md 等）
   - .kiro/steering/decision_governance.md（加入「取號前先查 ADR-000」條文）
   - backend/**/*.py 的 docstring 與註解
   - config.yaml 檔頭（若有引用）
   - review_model_pretraining_v1.md（repo 根目錄，目前未納入版控，也一併更新）
5. 跑驗收指令

### 驗收指令（必須實際跑過，不得只宣稱通過）

    # 應回傳空。commit-decision-map.md 故意保留舊號做對照，所以排除
    grep -rn "ADR-0\(1[1-9]\|20\)" \
      --include="*.md" --include="*.py" --include="*.js" \
      --include="*.jsx" --include="*.yaml" --include="*.yml" . \
      | grep -v "docs/decisions/commit-decision-map.md"

    # 確認新檔名都在
    ls docs/decisions/ADR-1*.md

    # 確認 001~010 完全沒被動到
    git diff --name-only | grep "ADR-0[01][0-9]" && echo "錯誤：動到封存區" || echo "OK"

    git diff --check

跑完把結果貼給我，包含實際的替換處數與檔案數。

## 完成後回報

- 實際改了幾個檔、幾處引用
- 驗收指令的實際輸出
- 有沒有遇到跟計畫不符的地方
- 還沒 commit（等我確認後再說要不要 commit）
```

---

## 使用說明（給 owner，不用貼給 Kiro）

- 這份 prompt 只處理**本分支**。C 的前端分支要另外給一份，號段用 201~204，
  規則檔已由本次建立，C 只需 `git merge origin/main` 拿到 ADR-000 後對齊。
- 建議順序：本分支做完 → ADR-000 進 main → C 分支 merge main 後重編 → 兩分支再合併。
- ADR-000 進 main 時建議獨立成一個 commit，不夾帶模型相關變更，方便 C 快速 cherry-pick 或 merge。
