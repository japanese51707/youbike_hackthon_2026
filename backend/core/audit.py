"""
稽核服務（core.audit）— 誰、何時、做了什麼
============================================
職責：記錄所有「人為關鍵動作」的留痕（覆寫、轉派、參數編輯、最適化套用、任務回報）。
是覆寫/警示/調度等模組共用的底層，讓每個決策都可回溯（NFR 可稽核）。

對齊 common.py AuditLog schema 與 AuditType。

儲存：先記憶體版（append-only list），A5 接 SQLite 後換持久化。
      介面不變（record / query），換儲存不影響上層。

對外暴露：
    AuditService（record / query / all）
    get_audit_service()  # 模組級單例，跨模組共用同一份留痕
"""

from __future__ import annotations
import datetime as _dt
from typing import Optional

# 合法稽核類型（對齊 common.py AuditType）
_VALID_TYPES = {
    "emergency_override",  # ③即時覆寫
    "task_transfer",       # 動態轉派
    "optimization",        # ②每日最適化套用
    "param_edit",          # 參數人工編輯
    "task_report",         # 任務回報
}


def _now_iso() -> str:
    return _dt.datetime.now().isoformat(timespec="seconds")


class AuditService:
    """append-only 稽核留痕。不可修改、不可刪除既有紀錄（稽核完整性）。"""

    def __init__(self, store: Optional[list] = None):
        self._logs: list[dict] = store if store is not None else []
        self._seq = 0

    def record(
        self,
        type: str,
        operator: str,
        action: str,
        station_id: Optional[str] = None,
        reason: Optional[str] = None,
        expired_at: Optional[str] = None,
        task_duration_minutes: Optional[int] = None,
    ) -> dict:
        """寫一筆稽核。type 非法直接 raise（失敗要看得見）。"""
        if type not in _VALID_TYPES:
            raise ValueError(
                f"未知的稽核類型 '{type}'（合法：{sorted(_VALID_TYPES)}）"
            )
        self._seq += 1
        ts = _now_iso()
        log = {
            "log_id": f"LOG-{ts.replace(':', '').replace('-', '')}-{self._seq:04d}",
            "type": type,
            "station_id": station_id,
            "operator": operator,
            "action": action,
            "reason": reason,
            "timestamp": ts,
            "expired_at": expired_at,
            "task_duration_minutes": task_duration_minutes,
        }
        self._logs.append(log)
        return log

    def query(
        self,
        type: Optional[str] = None,
        station_id: Optional[str] = None,
        operator: Optional[str] = None,
    ) -> list[dict]:
        logs = self._logs
        if type:
            logs = [x for x in logs if x["type"] == type]
        if station_id:
            logs = [x for x in logs if x.get("station_id") == station_id]
        if operator:
            logs = [x for x in logs if x.get("operator") == operator]
        return list(logs)

    def all(self) -> list[dict]:
        return list(self._logs)


# ── 模組級單例（跨模組共用同一份留痕）──
_service: Optional[AuditService] = None


def get_audit_service() -> AuditService:
    global _service
    if _service is None:
        _service = AuditService()
    return _service


def reset_audit_service() -> None:
    """測試用：清空單例。"""
    global _service
    _service = None
