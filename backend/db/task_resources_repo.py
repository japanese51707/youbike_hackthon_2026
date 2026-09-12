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
    # ADR-323：任務結束回到「值勤中」（busy → on_duty），不是下工。
    # 剛跑完一趟的司機是在班上、可以接下一趟，不是下班了。原本設成 off_duty
    # 會讓他從 available_operators()（要求 on_duty）消失，儀表板在線人數少算，
    # 班別在線狀態也對不上。真正的下班由司機自己按「下班」（/operators/me/duty），
    # 這才是「派到才上工」的正確對稱：系統只負責把他從忙碌放回待命。
    # ADR-308：司機 + 隨車兩名都要釋放（各自只在仍屬本任務時才放回待命）。
    for person_id in (task.get("assigned_operator"), task.get("assigned_escort")):
        if not person_id:
            continue
        conn.execute(
            """UPDATE operators SET current_task_id = NULL,
            status = CASE WHEN status = 'busy' THEN 'on_duty' ELSE status END,
            updated_at = CURRENT_TIMESTAMP WHERE operator_id = ? AND current_task_id = ?""",
            (person_id, task["task_id"]),
        )
    commit(conn)
