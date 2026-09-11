"""
站點參數對外介面（params.station_params）
==========================================
整合 param_layers（生效參數組裝）與 versioning（版本管理），
作為 API 層與其他模組取用站點參數的統一入口。

對外暴露：
    get_current(station_id)          # 當前生效參數（含 override_active、target_usage_rate）
    get_history(station_id)          # 版本歷史（回溯檢視）
    rollback(station_id, ver, op)    # 回溯
    (set_base / commit_optimized 由 versioning 提供，這裡轉出)
"""

from __future__ import annotations
from typing import Optional

from .param_layers import get_effective_params
from .versioning import (set_base, commit_optimized, commit_optimized_batch,
                         list_history, rollback)


def get_current(station_id: str) -> Optional[dict]:
    """當前生效參數（三層疊加後的結果）。找不到回 None。"""
    return get_effective_params(station_id)


def get_history(station_id: str) -> list[dict]:
    """版本歷史（新到舊）。"""
    return list_history(station_id)


__all__ = [
    "get_current", "get_history", "rollback",
    "set_base", "commit_optimized", "commit_optimized_batch",
]
