---
status: proposed
date: YYYY-MM-DD
decision-makers:
  - project-owner
approval-evidence:
scope:
  - module-or-concern
related-commits: []
retrospective: false
supersedes:
superseded-by:
---

# ADR-XXX：決策標題

## 背景與問題

描述需要決策的問題、限制、已知事實，以及不做決策的後果。不要把解法先寫進問題。

## 決策

用可驗證的句子寫明採用什麼、不採用什麼，以及決策邊界。

## 理由與判準

列出選擇時使用的判準，例如正確性、可維護性、成本、交付時間、可逆性、資安與團隊能力。

## 考慮過的替代方案

### 方案 A

- 優點：
- 缺點：
- 未採用原因：

### 方案 B

- 優點：
- 缺點：
- 未採用原因：

## 影響與後果

### 正面

-

### 負面與代價

-

### 尚未解決

-

## 介面與相容性

說明 API、Schema、資料格式、設定、既有模組與遷移需求；若無影響，明確寫「無」。

## 資安與隱私

檢查入向與出向邊界、權限、憑證、敏感資料與第三方回應；若無影響，明確寫「無」。

## 回復或取代方式

說明如何安全撤回，以及未來應以新 ADR supersede 而非改寫歷史。

## 驗證方式

列出能證明決策可行的測試、指標、Demo 或觀測證據。

## 追溯

- 相關 commit：
- 相關 Spec／文件：
- 相關 ADR：
