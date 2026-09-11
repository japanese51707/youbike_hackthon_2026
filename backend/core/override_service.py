"""
③即時緊急覆寫服務（core.override_service）
=============================================
職責：管理「人為緊急覆寫」——某站被主管/調度員標為緊急，在 dispatcher 排序時
當「最前綴」置頂（不改 urgency 分數，見 A2 dispatcher）。到期或取消後自動恢復。

與 ②每日最適化分開（②改參數、③只改排序優先）。對齊 api_contract 3.20。

核心行為：
  - apply：設定覆寫，記到期時間（config.override.預設時效分鐘，可傳 expire_minutes 覆寫）
  - active_station_ids：回傳「目前生效中」的覆寫站集合，給 dispatcher 當最前綴
  - 到期自動恢復：查詢生效覆寫時，惰性過濾掉已過期的（不需背景排程）
  - cancel：手動取消
  - 每個 apply/cancel/expire 都寫稽核（誰、何時、原因、到期時間）

覆寫到期 vs 任務衝突（規則已定義，api_contract 3.20）：
  覆寫到期或被手動取消時 → 由它產生、且仍在 pending/assigned（未開始）的任務「一併取消」，
  in_progress（執行中）的不受影響（保護正在路上的調度員）。
  兩種情況（到期/取消）都留稽核：覆寫本身記 emergency_override，連動取消的任務記 task_transfer。
  實作：注入 task_manager（set_task_manager），在 _purge_expired / cancel 時呼叫 _cascade_cancel_tasks。
  任務用 source_override_station_id 標記「由哪個覆寫產生」，作為連動取消的依據。

儲存：SQLite（db.overrides_repo）。重啟後生效中的覆寫仍在。
"""

from __future__ import annotations
import datetime as _dt
from typing import Optional

from config_loader import get_config
from .audit import get_audit_service
from db.connection import atomic


def _now() -> _dt.datetime:
    return _dt.datetime.now()


class OverrideService:
    def __init__(self, audit=None, task_manager=None):
        # 覆寫狀態存 SQLite（db.overrides_repo），不再用記憶體 dict
        self._audit = audit or get_audit_service()
        # 可選：注入 task_manager，覆寫到期/取消時連動取消未開始的任務。
        # 不注入時退化為「只管覆寫狀態」（測試或無任務情境）。
        self._task_manager = task_manager

    def set_task_manager(self, task_manager) -> None:
        """事後注入 task_manager（避免建構時的循環依賴）。"""
        self._task_manager = task_manager

    @atomic
    def _cascade_cancel_tasks(self, station_id: str, cause: str) -> None:
        """連動取消：該站覆寫消失時，取消它產生且仍未開始（pending/assigned）的任務。

        in_progress 執行中的不受影響（保護正在路上的調度員）。
        每筆取消都在任務上記原因，並寫一筆稽核（task_transfer 類型，記錄流向）。
        """
        if self._task_manager is None:
            return
        cancelled = self._task_manager.cancel_by_override_source(
            station_id,
            reason=f"來源緊急覆寫{cause}，此未開始任務一併取消",
            operator="system",
        )
        for t in cancelled:
            self._audit.record(
                type="task_transfer",
                operator="system",
                action=f"覆寫{cause}，連動取消未開始任務 {t['task_id']}",
                station_id=station_id,
                reason="覆寫到期/取消時，其產生且仍在 assigned 的任務一併取消（in_progress 不受影響）",
            )

    def apply(
        self,
        station_id: str,
        reason: str,
        operator: str,
        expire_minutes: Optional[int] = None,
    ) -> dict:
        """設定覆寫。到期時間 = 現在 + expire_minutes（未給用 config 預設）。"""
        cfg = get_config().get("override", {})
        minutes = int(expire_minutes if expire_minutes is not None
                      else cfg.get("預設時效分鐘", 120))
        now = _now()
        expire_at = now + _dt.timedelta(minutes=minutes)
        entry = {
            "station_id": station_id,
            "reason": reason,
            "operator": operator,
            "applied_at": now.isoformat(timespec="seconds"),
            "expire_at": expire_at.isoformat(timespec="seconds"),
            "expire_minutes": minutes,
        }
        from db import overrides_repo
        overrides_repo.upsert(entry)
        # 稽核留痕
        self._audit.record(
            type="emergency_override",
            operator=operator,
            action=f"設定緊急覆寫（{minutes} 分鐘）",
            station_id=station_id,
            reason=reason,
            expired_at=entry["expire_at"],
        )
        return entry

    @atomic
    def _purge_expired(self) -> None:
        """惰性清理：把已過期的覆寫移除，並記一筆自動恢復稽核。"""
        from db import overrides_repo
        now = _now()
        for e in overrides_repo.all_active():
            if _dt.datetime.fromisoformat(e["expire_at"]) <= now:
                sid = e["station_id"]
                overrides_repo.delete(sid)
                self._audit.record(
                    type="emergency_override",
                    operator="system",
                    action="緊急覆寫時效到期，自動恢復",
                    station_id=sid,
                    reason=f"原因：{e.get('reason')}（由 {e.get('operator')} 設定）",
                )
                # 連動：到期時取消該覆寫產生且仍未開始的任務（in_progress 不受影響）
                self._cascade_cancel_tasks(sid, cause="到期")

    def active_overrides(self) -> list[dict]:
        """目前生效中的覆寫（已過期的自動清掉）。給 3.20 GET /overrides/active。"""
        self._purge_expired()
        from db import overrides_repo
        return overrides_repo.all_active()

    def active_station_ids(self) -> set[str]:
        """生效中的覆寫站集合，給 dispatcher 當最前綴。"""
        self._purge_expired()
        from db import overrides_repo
        return {e["station_id"] for e in overrides_repo.all_active()}

    def is_active(self, station_id: str) -> bool:
        self._purge_expired()
        from db import overrides_repo
        return overrides_repo.get(station_id) is not None

    @atomic
    def cancel(self, station_id: str, operator: str = "system") -> bool:
        """手動取消覆寫。回傳是否有取消到東西。"""
        self._purge_expired()
        from db import overrides_repo
        entry = overrides_repo.get(station_id)
        if entry is None:
            return False
        overrides_repo.delete(station_id)
        self._audit.record(
            type="emergency_override",
            operator=operator,
            action="手動取消緊急覆寫",
            station_id=station_id,
            reason=f"原覆寫由 {entry.get('operator')} 設定",
        )
        # 連動：手動取消時也取消該覆寫產生且仍未開始的任務
        self._cascade_cancel_tasks(station_id, cause="被手動取消")
        return True


# ── 模組級單例 ──
_service: Optional[OverrideService] = None


def get_override_service() -> OverrideService:
    global _service
    if _service is None:
        _service = OverrideService()
        # 注入共用的 task_manager 單例，讓覆寫到期/取消能連動取消未開始任務
        from .task_manager import get_task_manager
        _service.set_task_manager(get_task_manager())
    return _service


def reset_override_service() -> None:
    global _service
    _service = None
