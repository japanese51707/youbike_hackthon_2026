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
    # 司機不常態待命：任務結束即下工（busy → off_duty），與「派到才上工」對稱。
    # ADR-308：司機 + 隨車兩名都要釋放（各自只在仍屬本任務時才下工）。
    for person_id in (task.get("assigned_operator"), task.get("assigned_escort")):
        if not person_id:
            continue
        conn.execute(
            """UPDATE operators SET current_task_id = NULL,
            status = CASE WHEN status = 'busy' THEN 'off_duty' ELSE status END,
            updated_at = CURRENT_TIMESTAMP WHERE operator_id = ? AND current_task_id = ?""",
            (person_id, task["task_id"]),
        )
    commit(conn)
