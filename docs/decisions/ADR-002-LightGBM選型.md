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

- 實測 MAE 1.51 台（baseline 4.29，改善 64.7%），區間覆蓋 78.7%
- 讓模型自己學因子交互作用（天氣、事件、假期當特徵餵進去）
- feature importance 好向評審解釋
- **傳統 ML，本機運行、推論免費、毫秒級**（非生成式 AI，見 docs/模型怎麼跑的）

## 影響

- 驗證用時間切分（1~5月訓、6月驗），禁止隨機切分（資料洩漏）
- 必須輸出 lower/upper_bound（規則引擎吃下界）
- 需 libomp 依賴（macOS：brew install libomp）
