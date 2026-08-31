# 開發原則（團隊共同遵守）

本檔為 YouBike 智慧調度系統的開發規範。所有程式碼（無論由誰或 AI 撰寫）都必須遵守。

---

## 一、模組化第一（最高原則）

**絕對禁止把所有功能塞進一個大檔案。** 每個功能必須是獨立、可單獨測試、可單獨修改的模組。

### 判準
- 修改一個功能時，不應該有機會弄壞另一個功能
- 一個檔案只做一件事，職責單一
- 檔案超過 ~300 行就要考慮拆分
- 如果一個函式做了超過一件事，拆開它

### 正確的結構範例
```
backend/
├── main.py                 # 只負責啟動 API 服務，不寫業務邏輯
├── api/                    # API 端點定義（路由）
│   ├── stations.py         # 站點相關端點
│   ├── dispatch.py         # 調度相關端點
│   └── kpi.py              # KPI 相關端點
├── core/                   # 核心業務邏輯
│   ├── rule_engine.py      # 規則引擎（只做判斷）
│   ├── priority.py         # 優先級計算（只算優先級）
│   └── urgency.py          # 緊急度計算（只算緊急度）
├── models/                 # 資料模型定義（格式/schema）
│   ├── station.py
│   └── dispatch.py
├── data/                   # 資料存取層
│   ├── data_source.py      # 資料源介面（可抽換：歷史/TDX）
│   └── athena_client.py    # Athena 查詢
├── prediction/             # 預測模型（B 負責）
│   └── predictor.py        # 對外只暴露 predict() 介面
└── config/
    └── config.yaml         # 所有參數集中在這，不寫死在程式碼
```

---

## 二、介面契約先行

不同模組之間、前後端之間，一律透過**事先定義好的介面**溝通。

### 規則
- 模組之間只透過定義好的函式簽名 / API 規格互動
- B 的預測模型對外只暴露一個 `predict(輸入) → 輸出` 介面，內部怎麼實作是 B 的事
- C 的前端只依賴 API 回傳的格式，不管後端怎麼算
- 改一個模組的內部實作，不能改變它對外的介面（否則會連累別人）

### 為什麼
三個人各自開發時，只要介面不變，就能獨立進行，不需要互相等待。

---

## 三、參數外部化

**任何閾值、權重、設定，都不准寫死在程式碼裡。** 一律放 `config.yaml`。

### 範例
```python
# ❌ 錯誤：寫死在程式碼
if available <= 3:
    ...

# ✅ 正確：從設定檔讀（動態判斷版，非死數字）
if adjusted_arrival <= config["trigger"]["安全緩衝_台數"]:
    ...
```

### 為什麼
- 調參不用改程式碼
- 黑客松後交通局的人能自己調
- 現場 Demo 換資料源/參數只改設定檔

---

## 四、失敗要看得見

**禁止靜默失敗。** 任何錯誤都要明確回報，不能假裝成功。

### 規則
- 函式失敗時回傳明確的錯誤狀態，不要回傳空值假裝沒事
- 任務狀態必須明確：`pending` / `in_progress` / `completed` / `retryable` / `manual_required`
- 資料異常（缺值、格式錯）要偵測並記錄，不要默默跳過

---

## 五、AI 只估計，規則引擎決策

- 預測模型（AI/ML）只輸出「預測值 + 不確定區間」
- 「要不要調度」的決策由規則引擎（確定性 if-else）做
- 規則引擎吃預測的「區間下界」觸發，不吃點估計
- 預測錯了，決策不能跟著錯

---

## 六、人在迴圈

- 所有調度指令走「預覽 → 人工確認 → 執行 → 驗證」四個閘門
- 系統不自動執行真實世界的動作
- 確認閘門不能被前端繞過

---

## 七、資料源可抽換

- 系統不綁死特定資料源
- 透過 `data_source.py` 介面，可切換「歷史 Parquet / Athena / TDX 即時 API」
- 現場 Demo 換資料源時只改設定，不改程式碼

---

## 八、Git 協作規範

### 分支策略
```
main            # 穩定版，只接 merge，不直接 push
dev             # 整合開發分支
feature/A-xxx   # A 的功能分支
feature/B-xxx   # B 的功能分支
feature/C-xxx   # C 的功能分支
```

### 規則
- 不直接 push 到 main
- 各自在 feature 分支開發，完成後發 Pull Request
- 由 A（PM）負責 review 和 merge，解決衝突
- Commit 訊息要清楚：`[模組] 做了什麼`，例如 `[rule_engine] 加入前瞻窗口緊急度計算`
- 一次 commit 只做一件事，不要一次改一堆不相關的東西

---

## 九、命名與註解

- 檔案、函式、變數用有意義的名字
- 中文專案，註解可用繁體中文
- 每個模組開頭寫清楚：這個檔案負責什麼、對外暴露什麼介面
- 不寫顯而易見的廢註解，寫「為什麼這樣做」的註解

---

## 十、測試邊界

- 核心邏輯（規則引擎、緊急度計算）要能單獨測試
- 用假資料就能測試自己的模組，不依賴別人的模組完成
- 黑客松時間有限，優先測試「會影響決策正確性」的部分

---

## 十一、資安是雙向的（設計時的固定檢查點）

設計任何對外通訊的系統時，資安要**雙向**考量，不能只想入向：

- **入向**（別人打我）：CORS、權限（後端驗）、rate limit、輸入驗證、錯誤訊息不外洩
- **出向**（我打別人 / 別人回我）：第三方回應當不可信輸入、SSRF 防護、憑證不外洩、超時重試上限、不外流敏感資料

檢查法：資料流圖上**每一條進出邊界的箭頭**都問一次——進來的問「他能不能騙我」，出去的問「我會不會被帶壞或洩漏」。

（詳見 Obsidian：〈資安是雙向的：入向防護與出向信任〉）

---

## 十二、Git 協作嚴謹規範（參考「接住」專案的成熟做法）

### 12.1 Repo 安全（若為 public repo）
- **永遠不 commit 密鑰**：API key、AWS 憑證、token、`.env`、私鑰
- **每次 push 前跑 secrets 掃描**：
  ```bash
  git diff --cached --name-only | xargs grep -lE \
    '(AKIA[0-9A-Z]{16}|sk-[a-zA-Z0-9]{20,}|password\s*=\s*["\x27].+["\x27]|AWS_SECRET_ACCESS_KEY|PRIVATE.KEY)' \
    2>/dev/null && echo "BLOCKED: secrets detected" && exit 1 || echo "OK: no secrets found"
  ```
  有 match 就不 push，改用環境變數 / `.env`（gitignored）
- 大型原始資料（Parquet、PDF）不進 Git，除非團隊明確決定

### 12.2 核准閘門（AI 動檔案前）
除了單純文件/樣板，動任何檔案前先保持唯讀，並：
1. 用白話說明目標與預期結果
2. 列出要新增/修改/刪除的檔案與理由
3. 說明對架構/API/schema/隱私/規則/部署的影響
4. 指出未解決的決策、假設、風險、與他人工作的衝突
5. 說明會跑的最小驗證指令
6. 等使用者核准再動手

實作後：未經明確要求，不 stage/commit/push；顯示 `git status` 和 `git diff --stat`，用白話解釋每個改動。

### 12.3 Commit 規範（Conventional Commits）
格式：`<type>(<scope>): <summary>`
- **type**：feat / fix / docs / refactor / test / chore / data
- **scope**（用最窄的模組）：repo / frontend / backend / api / schemas / core / prediction / params / rules / data / infra / docs
- **summary**：英文、祈使句、≤72 字、不加句號、描述單一改動
- 範例：`feat(prediction): add quantile interval to predictor`

### 12.4 架構決策記錄（ADR）
團隊在文件標為「待決策」的選項中做出選擇時，在 `docs/decisions/` 記錄一份 ADR（決策、理由、替代方案）。避免決策只存在某人腦中。
