"""ADR-302：後台增減站、覆寫取消、舊資料及重啟相容性。"""

import pytest

from core import dispatch_builder, task_execution
from core.task_manager import get_task_manager, IllegalTransition
from core.override_service import get_override_service
from db import tasks_repo, vehicles_repo, operators_repo
from db.connection import get_connection, init_db
from tests.conftest import OP_DISPATCHER
from tests.test_dispatch_safety import pool, draft, confirm, report


def test_api_build_then_reference_confirm(client, pool):
    # ADR-123：這趟是三站純補車，出車前須有足夠載量（測試情境宣告滿載出車）
    vehicles_repo.report_onboard("CAR-001", 15, "manual_report")
    response = client.post("/api/v1/dispatch/build/from-vehicle",
                           json={"vehicle_id": "CAR-001", "operator_id": "OP-004", "district": "板橋區"},
                           headers=OP_DISPATCHER)
    assert response.status_code == 200
    preview = response.json()
    assert preview["created_by"] == "OP-002"
    assert preview["version"] == 1 and preview["expires_at"]
    result = client.post("/api/v1/dispatch/confirm-trip",
                         json={"draft_id": preview["draft_id"], "version": preview["version"]},
                         headers=OP_DISPATCHER)
    assert result.status_code == 200
    assert len(tasks_repo.list_tasks()) == 1


def test_browser_numeric_roundtrip_is_not_tampering(client, pool):
    preview = draft(pool)
    # 模擬 JSON.stringify 將 integral float 轉為整數。
    def browser(value):
        if type(value) is float and value.is_integer():
            return int(value)
        if isinstance(value, dict):
            return {k: browser(v) for k, v in value.items()}
        if isinstance(value, list):
            return [browser(v) for v in value]
        return value
    assert confirm(client, browser(preview)).status_code == 200
    assert confirm(client, preview).status_code == 200
    assert len(tasks_repo.list_tasks()) == 1


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_report_rejected_before_writes(client, pool, value):
    tid = confirm(client, draft(pool)).json()["trip_id"]
    before = tasks_repo.get(tid)
    with pytest.raises(ValueError):
        task_execution.report_station(tid, "A", value, "OP-004")
    assert tasks_repo.get(tid) == before


def test_override_expiry_audit_failure_rolls_back_cancel_and_release(client, pool, monkeypatch):
    from db import audit_repo, overrides_repo
    tid = confirm(client, draft(pool, ids=("A",))).json()["trip_id"]
    task = tasks_repo.get(tid)
    task["source_override_station_id"] = "A"
    tasks_repo.update(task)
    ov = get_override_service()
    ov.apply("A", "活動", "OP-002", expire_minutes=-1)
    original = audit_repo.insert

    def fail_cascade(log):
        original(log)
        if log["type"] == "task_transfer":
            raise RuntimeError("cascade audit failed")

    monkeypatch.setattr(audit_repo, "insert", fail_cascade)
    with pytest.raises(RuntimeError):
        ov.active_station_ids()
    assert tasks_repo.get(tid)["task_status"] == "assigned"
    assert vehicles_repo.get_vehicle("CAR-001")["current_task_id"] == tid
    assert overrides_repo.get("A") is not None


def test_another_controller_cannot_confirm_preview(client, pool):
    response = confirm(client, draft(pool), headers={"X-Operator-Id": "OP-003"})
    assert response.status_code == 403
    assert tasks_repo.list_tasks() == []


@pytest.mark.parametrize("field,value", [("status", "off_duty"), ("is_active", 0),
                                         ("role_type", "controller"), ("status", "resting")])
def test_resource_changes_after_preview_rejected(client, pool, field, value):
    preview = draft(pool)
    conn = get_connection()
    conn.execute(f"UPDATE operators SET {field} = ? WHERE operator_id = 'OP-004'", (value,))
    conn.commit()
    assert confirm(client, preview).status_code == 409
    assert tasks_repo.list_tasks() == []


def test_reduced_vehicle_capacity_rejected(client, pool):
    preview = draft(pool)
    vehicles_repo.update_vehicle("CAR-001", max_capacity=5)
    assert confirm(client, preview).status_code == 409


def test_remove_final_station_closes_task_and_rejects_later_changes(client, pool):
    tid = confirm(client, draft(pool, ids=("A",))).json()["trip_id"]
    response = client.delete(f"/api/v1/dispatch/tasks/{tid}/stations/A", headers=OP_DISPATCHER)
    assert response.status_code == 200
    assert response.json()["back_to_pool"] is True
    assert tasks_repo.get(tid)["task_status"] == "completed"
    assert vehicles_repo.get_vehicle("CAR-001")["current_task_id"] is None
    assert client.post(f"/api/v1/dispatch/tasks/{tid}/stations", json={"station_id": "B"},
                       headers=OP_DISPATCHER).status_code == 409


def test_add_station_uses_server_instruction_and_rejects_claimed_station(client, pool):
    tid = confirm(client, draft(pool, ids=("A",))).json()["trip_id"]
    second = confirm(client, draft(pool, "CAR-002", "OP-005", ("C",)))
    assert second.status_code == 200
    assert client.post(f"/api/v1/dispatch/tasks/{tid}/stations", json={"station_id": "C"},
                       headers=OP_DISPATCHER).status_code == 409
    response = client.post(f"/api/v1/dispatch/tasks/{tid}/stations",
                           json={"station": {"station_id": "B", "target_available": -99,
                                              "station_status": "completed"}}, headers=OP_DISPATCHER)
    assert response.status_code == 200
    assert response.json()["station"]["target_available"] == 5
    assert response.json()["station"]["station_status"] == "pending"


def test_override_cancellation_releases_only_not_started_task(client, pool):
    tid = confirm(client, draft(pool, ids=("A",))).json()["trip_id"]
    task = tasks_repo.get(tid)
    task["source_override_station_id"] = "A"
    tasks_repo.update(task)
    ov = get_override_service()
    ov.apply("A", "活動結束", "OP-002", expire_minutes=-1)
    assert "A" not in ov.active_station_ids()
    assert tasks_repo.get(tid)["task_status"] == "cancelled"
    assert vehicles_repo.get_vehicle("CAR-001")["current_task_id"] is None
    assert operators_repo.get_operator("OP-004")["current_task_id"] is None
    assert task_execution.station_claim_map() == {}


def test_old_task_cannot_release_resources_now_owned_by_another_task(client, pool):
    tid = confirm(client, draft(pool, ids=("A",))).json()["trip_id"]
    # 模擬既有不一致資料：舊任務仍未结案，人車已指向新任務。
    vehicles_repo.assign_district("CAR-001", "三重區", "NEW-TASK")
    operators_repo.assign_district("OP-004", "三重區", "NEW-TASK")
    get_task_manager().cancel(tid, reason="清理舊任務", operator="OP-002")
    assert vehicles_repo.get_vehicle("CAR-001")["current_task_id"] == "NEW-TASK"
    assert operators_repo.get_operator("OP-004")["current_task_id"] == "NEW-TASK"


def test_returned_task_cannot_resume_without_new_confirmation(client, pool):
    tid = confirm(client, draft(pool)).json()["trip_id"]
    assert report(client, tid, "A", 5).status_code == 200
    task_execution.cancel_by_executor(tid, "OP-004", "退回")
    with pytest.raises(IllegalTransition):
        get_task_manager().start(tid)


def test_old_schema_migration_is_idempotent_and_preserves_tasks(monkeypatch, tmp_path):
    import sqlite3
    path = tmp_path / "legacy.sqlite"
    with sqlite3.connect(path) as conn:
        conn.execute("""CREATE TABLE tasks (task_id TEXT PRIMARY KEY, task_type TEXT,
                     task_status TEXT, assigned_operator TEXT, source_override_station_id TEXT)""")
        conn.execute("INSERT INTO tasks VALUES ('OLD', 'normal', 'assigned', 'OP-004', NULL)")
    monkeypatch.setenv("YOUBIKE_DB_PATH", str(path))
    init_db()
    init_db()
    conn = get_connection()
    row = dict(conn.execute("SELECT * FROM tasks WHERE task_id = 'OLD'").fetchone())
    assert row["task_status"] == "assigned"
    assert row["resources_released"] == 0
    assert row["vehicle_return_status"] is None
    conn.close()
