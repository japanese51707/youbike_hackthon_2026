"""
任務管理器（core.task_manager）— 狀態機 + 動態轉派 + 可續跑
=============================================================
職責：管理調度任務的生命週期，維護合法的狀態轉換，支援緊急任務轉派。
不做：產生建議（dispatcher）、觸發判斷（rule_engine）。

狀態機（對齊 dispatch.py TaskStatus）：
    pending ──assign──> assigned ──start──> in_progress ──complete──> completed
                          │                     │
                          │                     ├──fail──> retryable ──retry──> in_progress
                          │                     └──block─> manual_required
                          └──reassign──> assigned（僅 emergency 任務、未 in_progress 前）

規則（呼應核心決策）：
  - assigned 狀態是「動態轉派」的前提：任務已指派但未開始，emergency 型可轉給別人
  - 一旦 in_progress（執行中）就鎖定，不可轉派（避免兩人搶同一任務）
  - normal 型任務綁定調度員，不可轉派；emergency 型未開始前可轉派
  - 失敗要看得見（steering §4）：非法轉換 raise，不靜默

可續跑：狀態存在 store（先記憶體版，A5 接 SQLite 後換持久化），
        重啟後可從 store 恢復未完成任務，繼續處理。

對外暴露：
    TaskManager（狀態機操作）
    ILLEGAL_TRANSITION（例外類別）
"""

from __future__ import annotations
from typing import Optional

from db.connection import atomic


# 合法狀態轉換表：{現狀態: {可轉往的狀態}}
# 注意：只有「未開始」的任務（pending/assigned）能被取消；in_progress 執行中不可取消
# （保護正在路上的調度員，呼應覆寫到期規則：執行中不受影響）。
_TRANSITIONS = {
    "pending": {"assigned", "cancelled"},
    "assigned": {"assigned", "in_progress", "cancelled"},  # assigned→assigned = 轉派
    "in_progress": {"completed", "retryable", "manual_required"},
    "retryable": {"in_progress", "manual_required"},
    "manual_required": {"in_progress", "completed"},
    "completed": set(),                                # 終態
    "cancelled": set(),                                # 終態
}


class IllegalTransition(Exception):
    """非法狀態轉換（例：completed 想改回 pending）。"""


class TaskManager:
    """任務狀態機。任務以 dict 表示（對齊 DispatchTask schema）。

    儲存：SQLite（db.tasks_repo）。重啟後未完成任務仍在，可續跑。
    """

    # ── 查詢 ──
    def get(self, task_id: str) -> Optional[dict]:
        from db import tasks_repo
        return tasks_repo.get(task_id)

    def list_tasks(self, status: Optional[str] = None,
                   operator: Optional[str] = None) -> list[dict]:
        from db import tasks_repo
        return tasks_repo.list_tasks(status=status, operator=operator)

    def pending_or_active(self) -> list[dict]:
        """未完成任務（可續跑的目標）。重啟後用來恢復進度。"""
        from db import tasks_repo
        return tasks_repo.not_completed()

    # ── 狀態轉換核心 ──
    def _transition(self, task_id: str, to_status: str) -> dict:
        from db import tasks_repo
        task = tasks_repo.get(task_id)
        if task is None:
            raise KeyError(f"找不到任務 {task_id}")
        if task.get("resources_released") and to_status in {"assigned", "in_progress"}:
            raise IllegalTransition("任務資源已釋放，請重新預覽派工")
        cur = task.get("task_status", "pending")
        if to_status not in _TRANSITIONS.get(cur, set()):
            raise IllegalTransition(
                f"任務 {task_id} 不可從 '{cur}' 轉到 '{to_status}'"
                f"（合法：{sorted(_TRANSITIONS.get(cur, set())) or '無（終態）'}）"
            )
        task["task_status"] = to_status
        if to_status in {"completed", "cancelled"}:
            from db.task_resources_repo import release
            release(task)
            task["resources_released"] = 1
            for stop in task.get("route", []):
                if isinstance(stop, dict):
                    stop["claimed_by"] = None
        tasks_repo.update(task)
        return task

    # ── 生命週期操作 ──
    @atomic
    def create(self, task: dict) -> dict:
        """建立任務（pending）。task 需含 task_id、task_type。"""
        from db import tasks_repo
        tid = task["task_id"]
        if tasks_repo.exists(tid):
            raise ValueError(f"任務 {tid} 已存在")
        task.setdefault("task_status", "pending")
        tasks_repo.insert(task)
        return tasks_repo.get(tid)

    @atomic
    def assign(self, task_id: str, operator_id: str) -> dict:
        """指派給調度員（pending→assigned）。"""
        from db import tasks_repo
        existing = tasks_repo.get(task_id)
        if existing and existing.get("assigned_vehicle") and existing.get("task_status") != "pending":
            raise IllegalTransition("已指派的人車任務請使用轉派或退回流程")
        task = self._transition(task_id, "assigned")
        task["assigned_operator"] = operator_id
        tasks_repo.update(task)
        return task

    @atomic
    def reassign(self, task_id: str, new_operator_id: str) -> dict:
        """動態轉派（assigned→assigned，換人）。僅 emergency 型、未開始前可轉。"""
        from db import tasks_repo
        task = tasks_repo.get(task_id)
        if task is None:
            raise KeyError(f"找不到任務 {task_id}")
        if task.get("task_status") != "assigned":
            raise IllegalTransition(
                f"任務 {task_id} 狀態為 '{task.get('task_status')}'，"
                f"只有 assigned（未開始）的任務可轉派"
            )
        if task.get("task_type") != "emergency":
            raise IllegalTransition(
                f"任務 {task_id} 為 '{task.get('task_type')}' 型，"
                f"只有 emergency 型可動態轉派（normal 綁定調度員）"
            )
        if task.get("assigned_vehicle"):
            from core.dispatch_guards import occupied_tasks
            from core.dispatch_errors import DispatchConflict
            from db import operators_repo
            op = operators_repo.get_operator(new_operator_id)
            if (not op or not op["is_active"] or op.get("status") != "on_duty"
                    or op.get("role_type") not in {"driver", "depot_standby"}
                    or op.get("current_task_id")
                    or any(t.get("assigned_operator") == new_operator_id
                           for t in occupied_tasks(task_id))):
                raise DispatchConflict("新執行人員不可派遣")
            from db.task_resources_repo import release
            release({**task, "assigned_vehicle": None})
            operators_repo.assign_district(new_operator_id, task.get("district"), task_id)
            for stop in task.get("route", []):
                if isinstance(stop, dict) and stop.get("station_status", "pending") == "pending":
                    stop["claimed_by"] = new_operator_id
        task["assigned_operator"] = new_operator_id
        tasks_repo.update(task)   # assigned→assigned，狀態不變只換人
        return task

    @atomic
    def start(self, task_id: str) -> dict:
        """開始執行（assigned→in_progress，鎖定不可轉派）。"""
        return self._transition(task_id, "in_progress")

    @atomic
    def complete(self, task_id: str) -> dict:
        """完成（in_progress→completed）。"""
        task = self.get(task_id)
        if task and any(not isinstance(s, dict) or s.get("station_status", "pending") == "pending"
                        for s in task.get("route", [])):
            raise IllegalTransition("仍有未回報站點，不可結案")
        return self._transition(task_id, "completed")

    @atomic
    def fail(self, task_id: str, retryable: bool = True) -> dict:
        """失敗：可重試→retryable，否則→manual_required。"""
        return self._transition(task_id, "retryable" if retryable else "manual_required")

    @atomic
    def retry(self, task_id: str) -> dict:
        """重試（retryable→in_progress）。"""
        return self._transition(task_id, "in_progress")

    @atomic
    def cancel(self, task_id: str, reason: str = "", operator: str = "system") -> dict:
        """取消任務（pending/assigned→cancelled）。in_progress 不可取消（會 raise）。

        記錄取消原因到任務本身，供稽核與前端顯示。
        """
        from db import tasks_repo
        task = self._transition(task_id, "cancelled")   # in_progress 會在此被擋
        task["cancel_reason"] = reason
        task["cancelled_by"] = operator
        tasks_repo.update(task)
        return task

    @atomic
    def cancel_by_override_source(
        self, station_id: str, reason: str = "", operator: str = "system"
    ) -> list[dict]:
        """取消「因某站③覆寫而產生、且仍在 pending/assigned」的任務。

        用於覆寫到期/取消時的連動（規則：來源覆寫消失 → 未開始的任務一併取消，
        in_progress 執行中的不受影響，見 spec / api_contract 3.20）。
        回傳被取消的任務清單。
        """
        from db import tasks_repo
        affected = tasks_repo.find_by_override_source(station_id, ["pending", "assigned"])
        cancelled = []
        for t in affected:
            cancelled.append(self.cancel(t["task_id"], reason=reason, operator=operator))
        return cancelled


# ── 模組級單例（跨模組共用同一份任務狀態；A5 換 SQLite backend）──
_manager: Optional[TaskManager] = None


def get_task_manager() -> TaskManager:
    global _manager
    if _manager is None:
        _manager = TaskManager()
    return _manager


def reset_task_manager() -> None:
    """測試用：清空單例。"""
    global _manager
    _manager = None
