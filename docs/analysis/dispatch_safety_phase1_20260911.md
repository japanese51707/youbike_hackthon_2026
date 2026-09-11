# 第一批：派工安全與結案交付紀錄

日期：2026-09-11。分支：`feature/A-dispatch-safety-lifecycle`。決策：[ADR-302](../decisions/ADR-302-派工確認與任務結案一致性.md)。

## 已完成

| 問題 | 修正／驗證 |
|---|---|
| 緊急檢查繞過確認 | 檢查只回建議；需後台角色；persist=true 回 422；正式派遣走 emergency 草稿確認 |
| 信任前端草稿、重複派遣 | 後端短期草稿／建立者／版本；竄改或過期回 409；確認收據與派工共同提交；重送回原任務 |
| 人車／站點重複占用 | 確認交易內重新檢查；檔案 SQLite 並行確認只有一個成功 |
| 中途寫入失敗留下半筆任務 | 任務、人車、收據、稽核共用交易；三個寫入階段注入失敗後全部回滾，可安全重試 |
| 越權／非法回報 | 指派者限制；嚴格整數、非負及已知站容量檢查；完成／移除站不得覆寫 |
| 完成或退回後未釋放 | 首次回報開始、最後一站結案；退回清除認領；預備車恢復 standby；只釋放仍屬該任務的資源 |
| 覆寫取消與任務不一致 | 覆寫到期／取消、連動取消、人車釋放及稽核共同回滾；執行中任務維持既有保護 |

## 驗證證據

- 177 項相關測試通過（3.77 秒），含新增 52 項回歸案例。
- 測試使用記憶體／暫存 SQLite；預測改注入 MockPredictor，隔離外部歷史讀取。本結果不代表模型準確度或真實資料端到端驗證。
- 唯一 warning 是既有 Starlette TestClient／httpx 棄用提示，這批未更換依賴。
- 34 個變更 Python 檔完成 AST 語法檢查；後續修改亦經 pytest 匯入執行。
- `git diff --check` 通過；未 stage、commit 或 push，保留原有兩個未追蹤檔案。

```sh
cd backend
PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 ../.venv/bin/python -B -m pytest \
  -p no:cacheprovider -o addopts='' \
  tests/test_dispatch_safety.py tests/test_task_lifecycle_safety.py \
  tests/test_dispatch_builder.py tests/test_task_execution.py \
  tests/test_dispatch_assignment.py tests/test_dispatch_extras.py \
  tests/test_emergency.py tests/test_override.py tests/test_auth.py \
  tests/test_p0_endpoints.py tests/test_p1_endpoints.py tests/test_schema.py \
  tests/test_rule_engine.py tests/test_urgency.py tests/test_target_level.py \
  tests/test_offline_stations.py tests/test_params.py tests/test_security.py -q --tb=short
git diff --check
```

## 串接與維護

- [API 契約](../../.kiro/specs/youbike-dispatch-system/api_contract.md) §3.4／3.6／3.13 已同步。後端／API owner 維護派工與交易，前端 owner 依契約接線。
- 確認使用 `{draft_id, version}` 或原樣 `{draft}`。舊 `recommendation_ids` 不再回 mock 成功。更改選項須重新 build；草稿需由建立者確認。
- `config.yaml` 的 `dispatch_drafts` 管理期限及上限。草稿未確認前只在單程序記憶體；重啟後須重新預覽，已確認收據保留。
- 人力主檔須明確為 `on_duty` 且具 `driver`／`depot_standby` 角色。正式 seed 維持 off_duty，不把尚未上班的人員自動視為可派遣。
- 啟動會冪等新增確認收據表與任務釋放／車輛恢復狀態欄位；不自動推測或修改既有任務的完成狀態。人車釋放保留最後作業區，清除目前任務關聯。
- 既有 header 身分機制仍只限受控 Demo。即時資料／歷史接線、模型、逐站載量守恆、ETA、工時完整追蹤、正式前端整合及部署，仍屬後續批次。
