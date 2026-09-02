"""
參數版本管理（params.versioning）
==================================
對齊 model_architecture ② 的「版本控制 + 回溯」：
  - 每次最適化 approve 後存一份新版本（reject 不留版本，見 design §4.3）
  - 調整需備註原因
  - 可回溯到前一版（rollback）

與 A3 的稽核整合：版本存檔/回溯都寫稽核（optimization / param_edit）。

對外暴露：
    commit_optimized(station_id, params, reason, operator)  # ②approve 後存版本
    set_base(station_id, params, conditions, reason)         # ①基礎參數（建置時）
    list_history(station_id)                                 # 版本歷史（回溯檢視）
    rollback(station_id, version, operator)                  # 回溯到指定版本
"""

from __future__ import annotations
from typing import Optional

from db import params_repo
from core.audit import get_audit_service


def set_base(
    station_id: str,
    params: dict,
    conditions: Optional[list] = None,
    reason: str = "①基礎參數（建置時設定）",
) -> dict:
    """設定①基礎參數（param_source=base），設為生效版本。"""
    return params_repo.save_version(
        station_id, params, param_source="base",
        conditions=conditions, reason=reason, make_active=True)


def commit_optimized(
    station_id: str,
    params: dict,
    reason: str,
    operator: str,
    conditions: Optional[list] = None,
) -> dict:
    """②每日最適化 approve 後存新版本（param_source=ai_optimized）。

    reason 必填（model_architecture 要求調整需備註原因）。寫稽核。
    """
    if not reason:
        raise ValueError("最適化版本必須備註調整原因（model_architecture ② 要求）")
    version = params_repo.save_version(
        station_id, params, param_source="ai_optimized",
        conditions=conditions, reason=reason, make_active=True)
    get_audit_service().record(
        type="optimization",
        operator=operator,
        action=f"套用②最適化參數，新版本 {version['version']}",
        station_id=station_id,
        reason=reason,
    )
    return version


def list_history(station_id: str) -> list[dict]:
    """該站參數版本歷史（新到舊），供 GET /params/history。"""
    return params_repo.list_versions(station_id)


def rollback(station_id: str, version: str, operator: str) -> Optional[dict]:
    """回溯到指定版本（設為生效）。找不到版本回 None。寫稽核。"""
    result = params_repo.activate_version(station_id, version)
    if result is None:
        return None
    get_audit_service().record(
        type="param_edit",
        operator=operator,
        action=f"回溯站點參數到版本 {version}",
        station_id=station_id,
        reason="人工回溯（rollback）",
    )
    return result
