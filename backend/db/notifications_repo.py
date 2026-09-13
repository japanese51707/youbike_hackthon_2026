"""ADR-335：分級催辦的站內通知（每事件／階段／收件人／承辦版本／提醒批次各一筆）。

四件事刻意分開記，不要混成一個 bool：
  created_at       系統建立了這則提醒
  delivered_at     前端真的取走了（不是「送達手機」）
  seen_at          使用者看到了
  acknowledged_at  使用者按了已讀

舊設計把「已讀」當成全域靜音，結果現場的均衡解是「大家按已讀讓它安靜」，
30／45 分鐘的升級永遠不會觸發。這裡改成每人每階段各自一筆：
司機按已讀不會替管理端消音，管理端按已讀也不會替司機消音，
而且都不會擋住下一個階段。
"""

from typing import Optional

from db.connection import get_connection, commit


def _row(row) -> Optional[dict]:
    return dict(row) if row is not None else None


def ensure(notification: dict) -> Optional[dict]:
    """冪等建立一則通知。同一組唯一鍵重複呼叫只會有一筆。

    唯一鍵＝(case_id, stage, recipient_id, assignment_version, reminder_index)。
    assignment_version 讓「轉派後的新承辦」收得到自己的那一份，
    reminder_index 讓 60 分後每 15 分鐘的持續提醒各自成立。
    """
    conn = get_connection()
    conn.execute(
        """INSERT INTO alert_notifications
           (notification_id, case_id, stage, recipient_id, recipient_role, task_id,
            assignment_version, reminder_index, created_at, digest_key, body)
           VALUES (:notification_id, :case_id, :stage, :recipient_id, :recipient_role,
                   :task_id, :assignment_version, :reminder_index, :created_at,
                   :digest_key, :body)
           ON CONFLICT DO NOTHING""",
        {
            "notification_id": notification["notification_id"],
            "case_id": notification["case_id"],
            "stage": int(notification["stage"]),
            "recipient_id": notification["recipient_id"],
            "recipient_role": notification.get("recipient_role", "controller"),
            "task_id": notification.get("task_id"),
            "assignment_version": notification.get("assignment_version", ""),
            "reminder_index": int(notification.get("reminder_index", 0)),
            "created_at": notification["created_at"],
            "digest_key": notification.get("digest_key"),
            "body": notification.get("body", ""),
        },
    )
    commit(conn)
    return find(notification["case_id"], notification["stage"],
                notification["recipient_id"],
                notification.get("assignment_version", ""),
                int(notification.get("reminder_index", 0)))


def find(case_id: str, stage: int, recipient_id: str,
         assignment_version: str = "", reminder_index: int = 0) -> Optional[dict]:
    conn = get_connection()
    return _row(conn.execute(
        """SELECT * FROM alert_notifications
           WHERE case_id = ? AND stage = ? AND recipient_id = ?
             AND assignment_version = ? AND reminder_index = ?""",
        (case_id, int(stage), recipient_id, assignment_version, int(reminder_index)),
    ).fetchone())


def list_for_recipient(recipient_id: str, include_resolved: bool = False,
                       limit: int = 200) -> list:
    """某人目前該看到的提醒。預設只回仍未解除案件的通知。"""
    conn = get_connection()
    sql = """SELECT n.*, c.station_id, c.station_name, c.district, c.opened_at,
                    c.closed_at, c.observation_status
             FROM alert_notifications n
             JOIN alert_cases c ON c.case_id = n.case_id
             WHERE n.recipient_id = ?"""
    if not include_resolved:
        sql += " AND c.closed_at IS NULL"
    sql += " ORDER BY n.created_at DESC LIMIT ?"
    return [dict(r) for r in conn.execute(sql, (recipient_id, int(limit))).fetchall()]


def list_for_case(case_id: str) -> list:
    conn = get_connection()
    return [dict(r) for r in conn.execute(
        "SELECT * FROM alert_notifications WHERE case_id = ? ORDER BY created_at",
        (case_id,)).fetchall()]


def mark(notification_id: str, field: str, stamp: str,
         recipient_id: Optional[str] = None) -> Optional[dict]:
    """標記 delivered_at / seen_at / acknowledged_at 其中一個時間欄位。

    recipient_id 有給就一併比對，確保一個人只能標記自己的通知。
    """
    if field not in ("delivered_at", "seen_at", "acknowledged_at"):
        raise ValueError(f"不支援的通知欄位：{field}")
    conn = get_connection()
    params = [stamp, notification_id]
    sql = f"UPDATE alert_notifications SET {field} = ? WHERE notification_id = ?"
    if recipient_id is not None:
        sql += " AND recipient_id = ?"
        params.append(recipient_id)
    conn.execute(sql, params)
    commit(conn)
    return _row(conn.execute(
        "SELECT * FROM alert_notifications WHERE notification_id = ?",
        (notification_id,)).fetchone())


def mute(notification_id: str, muted_until: str, recipient_id: str) -> None:
    """個人靜音一則提醒。不遮清單、不擋下一階段、不關案。"""
    conn = get_connection()
    conn.execute(
        """UPDATE alert_notifications SET muted_until = ?
           WHERE notification_id = ? AND recipient_id = ?""",
        (muted_until, notification_id, recipient_id))
    commit(conn)


def max_reminder_index(case_id: str, stage: int, recipient_id: str) -> int:
    conn = get_connection()
    row = conn.execute(
        """SELECT MAX(reminder_index) AS m FROM alert_notifications
           WHERE case_id = ? AND stage = ? AND recipient_id = ?""",
        (case_id, int(stage), recipient_id)).fetchone()
    return int((row["m"] if row and row["m"] is not None else -1))


def find_by_id(notification_id: str) -> Optional[dict]:
    conn = get_connection()
    return _row(conn.execute(
        "SELECT * FROM alert_notifications WHERE notification_id = ?",
        (notification_id,)).fetchone())
