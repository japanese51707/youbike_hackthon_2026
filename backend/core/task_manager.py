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

    store 為外部注入的持久層；預設用記憶體 dict，A5 換 SQLite。
    """

    def __init__(self, store: Optional[dict] = None):
        # store: {task_id: task_dict}
        self._store: dict[str, dict] = store if store is not None else {}

    # ── 查詢 ──
    def get(self, task_id: str) -> Optional[dict]:
        return self._store.get(task_id)

    def list_tasks(self, status: Optional[str] = None,
                   operator: Optional[str] = None) -> list[dict]:
        tasks = list(self._store.values())
        if status:
            tasks = [t for t in tasks if t.get("task_status") == status]
        if operator:
            tasks = [t for t in tasks if t.get("assigned_operator") == operator]
        return tasks

    def pending_or_active(self) -> list[dict]:
        """未完成任務（可續跑的目標）。重啟後用來恢復進度。"""
        done = {"completed"}
        return [t for t in self._store.values() if t.get("task_status") not in done]

    # ── 狀態轉換核心 ──
    def _transition(self, task_id: str, to_status: str) -> dict:
        task = self._store.get(task_id)
        if task is None:
            raise KeyError(f"找不到任務 {task_id}")
        cur = task.get("task_status", "pending")
        if to_status not in _TRANSITIONS.get(cur, set()):
            raise IllegalTransition(
                f"任務 {task_id} 不可從 '{cur}' 轉到 '{to_status}'"
                f"（合法：{sorted(_TRANSITIONS.get(cur, set())) or '無（終態）'}）"
            )
        task["task_status"] = to_status
        return task

    # ── 生命週期操作 ──
    def create(self, task: dict) -> dict:
        """建立任務（pending）。task 需含 task_id、task_type。"""
        tid = task["task_id"]
        if tid in self._store:
            raise ValueError(f"任務 {tid} 已存在")
        task.setdefault("task_status", "pending")
        self._store[tid] = task
        return task

    def assign(self, task_id: str, operator_id: str) -> dict:
        """指派給調度員（pending→assigned）。"""
        task = self._transition(task_id, "assigned")
        task["assigned_operator"] = operator_id
        return task

    def reassign(self, task_id: str, new_operator_id: str) -> dict:
        """動態轉派（assigned→assigned，換人）。僅 emergency 型、未開始前可轉。"""
        task = self._store.get(task_id)
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
        task = self._transition(task_id, "assigned")   # 合法（assigned→assigned）
        task["assigned_operator"] = new_operator_id
        return task

    def start(self, task_id: str) -> dict:
        """開始執行（assigned→in_progress，鎖定不可轉派）。"""
        return self._transition(task_id, "in_progress")

    def complete(self, task_id: str) -> dict:
        """完成（in_progress→completed）。"""
        return self._transition(task_id, "completed")

    def fail(self, task_id: str, retryable: bool = True) -> dict:
        """失敗：可重試→retryable，否則→manual_required。"""
        return self._transition(task_id, "retryable" if retryable else "manual_required")

    def retry(self, task_id: str) -> dict:
        """重試（retryable→in_progress）。"""
        return self._transition(task_id, "in_progress")

    def cancel(self, task_id: str, reason: str = "", operator: str = "system") -> dict:
        """取消任務（pending/assigned→cancelled）。in_progress 不可取消（會 raise）。

        記錄取消原因到任務本身，供稽核與前端顯示。
        """
        task = self._transition(task_id, "cancelled")   # in_progress 會在此被擋
        task["cancel_reason"] = reason
        task["cancelled_by"] = operator
        return task

    def cancel_by_override_source(
        self, station_id: str, reason: str = "", operator: str = "system"
    ) -> list[dict]:
        """取消「因某站③覆寫而產生、且仍在 pending/assigned」的任務。

        用於覆寫到期/取消時的連動（規則：來源覆寫消失 → 未開始的任務一併取消，
        in_progress 執行中的不受影響，見 spec / api_contract 3.20）。
        回傳被取消的任務清單。
        """
        affected = [
            t for t in self._store.values()
            if t.get("source_override_station_id") == station_id
            and t.get("task_status") in ("pending", "assigned")
        ]
        cancelled = []
        for t in affected:
            self.cancel(t["task_id"], reason=reason, operator=operator)
            cancelled.append(t)
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
