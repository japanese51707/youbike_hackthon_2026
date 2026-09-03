# ADR-002：預測模型用 LightGBM

狀態：已定案（2026-08-31）

## 決策

預測模型用 **LightGBM**，並輸出不確定區間（quantile regression）。乘法權重公式降級為「可解釋 baseline」對照組。

## 脈絡

要預測每站未來可借車數。候選：手調乘法公式、LSTM、Prophet、LightGBM。第一輪審查（review_claude_回覆）指出乘法公式假設因子獨立，但「下雨×尖峰」不是相乘關係。

## 替代方案

- **手調乘法公式** — 保留當 baseline 對照，但正式模型不用（誤差複利、權重不可維護）。
- **LSTM** — 否決：資料量夠但序列結構簡單，划不來。
- **Prophet** — 否決：單序列工具，我們有 1583 站。
- **LightGBM（採用）** — 表格資料表現好、訓練快、可出 feature importance、可 quantile regression 出區間。

## 理由

- 讓模型自己學因子交互作用（天氣、事件、假期當特徵餵進去）
- feature importance 好向評審解釋
- **傳統 ML，本機運行、推論免費、毫秒級**（非生成式 AI，見 docs/模型怎麼跑的）

### ⚠️ 實測數字更正（2026-09-03，general-purpose-model 分支重跑）

> LightGBM 選型（本 ADR 核心決策）**維持不變**——它仍是表格資料 + 需區間 + 需可解釋的對的工具。
> 但下方舊數字經進訓練前審查（review_model_pretraining_v1.md F-02）發現 baseline 過弱、且未防資料洩漏，
> 已於防洩漏管線上誠實重跑。依 decision_governance「重測後更正、保留舊數字與差異」規範記錄。

**舊數字（2026-08-31，不可再對外宣稱，保留供對照）**：
- MAE 1.51 台、baseline 4.29、改善 64.7%、區間覆蓋 78.7%
- 問題：baseline 4.29 定義不明且過弱（疑為「預測 Δ=0」或全域平均）；未確認防洩漏

**新數字（2026-09-03，防洩漏管線 + seasonal naive baseline，全量 1583 站 × 6 月）**：
- **baseline（seasonal naive，站×day_type×時段歷史中位數）MAE = 1.426**（非 4.29！舊 baseline 確實過弱）
- **LightGBM P50 MAE = 1.446**，比 baseline **差 1.4%**（目前尚未贏過 baseline）
- 分區間：已空區 baseline 1.143 / LightGBM 1.469（模型在最關鍵區反而更差）
- 區間覆蓋率 45.2%（名目 80%，偏低待修）；分位數交叉率 0%

**差異說明與結論**：
- 用嚴格 baseline 後，舊「改善 64.7%」蒸發——證實舊數字虛胖（審查 F-02 命中）
- 根因：target Δ 有 78% 為 0（零膨脹重尾），MAE 被大量 0 稀釋；且空站截斷（F-03）使模型在關鍵區失準
- **這不推翻 LightGBM 選型**，而是指出「要贏 baseline 必須改目標定義/多視野/覆蓋率校準」（審查 P1/P2 後續項）
- 在做完後續改善並重跑前，**不對外宣稱任何模型優於 baseline 的數字**
- **⚠️ 超參數現況**：上述新數字是用「**未調參的起始預設值**」跑的（n_estimators=300/lr=0.05/num_leaves=31/min_child_samples=50 為常見起始值，非調校結果；分位數 P10/P90 為暫定，未依營運成本 newsvendor 校準）。超參數優化（審查 F-07 rolling CV 選參）尚未做——「模型贏不了 baseline」有一部分可能來自未調參。超參數與分位數決策待後續優化後記入 ADR。

## 影響

- 驗證用時間切分（1~5月訓、6月驗），禁止隨機切分（資料洩漏）
- 必須輸出 lower/upper_bound（規則引擎吃下界）
- 需 libomp 依賴（macOS：brew install libomp）
