"""ADR-302：僅釋放仍屬於該任務的人車，保留歷史指派欄位。"""

from db.connection import get_connection, commit


def release(task):
    conn = get_connection()
    conn.execute(
        """UPDATE vehicles SET current_task_id = NULL,
        status = CASE WHEN status = 'dispatched' THEN ? ELSE status END,
        updated_at = CURRENT_TIMESTAMP WHERE vehicle_id = ? AND current_task_id = ?""",
        (task.get("vehicle_return_status") or "available", task.get("assigned_vehicle"), task["task_id"]),
    )
    conn.execute(
        """UPDATE operators SET current_task_id = NULL,
        status = CASE WHEN status = 'busy' THEN 'on_duty' ELSE status END,
        updated_at = CURRENT_TIMESTAMP WHERE operator_id = ? AND current_task_id = ?""",
        (task.get("assigned_operator"), task["task_id"]),
    )
    commit(conn)
