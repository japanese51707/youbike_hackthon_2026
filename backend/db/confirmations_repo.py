"""ADR-302：已確認草稿的冪等收據，與派工共用交易。"""

from db.connection import get_connection, commit


def get(draft_id):
    row = get_connection().execute(
        "SELECT * FROM dispatch_confirmations WHERE draft_id = ?", (draft_id,)
    ).fetchone()
    return dict(row) if row else None


def insert(receipt):
    conn = get_connection()
    conn.execute(
        """INSERT INTO dispatch_confirmations
        (draft_id, version, fingerprint, task_id, confirmed_by, confirmed_at)
        VALUES (:draft_id, :version, :fingerprint, :task_id, :confirmed_by, :confirmed_at)""",
        receipt,
    )
    commit(conn)
