"""ADR-302：以實際 API／SQLite 重現派工漏洞及交易失敗，不依賴外部資料。"""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import Barrier

import pytest

from core import dispatch_builder, dispatch_drafts, task_execution
from core.dispatch_errors import DispatchConflict
from db import tasks_repo, vehicles_repo, operators_repo, audit_repo, confirmations_repo
from db.connection import get_connection, init_db
from tests.conftest import OP_DISPATCHER, OP_OPERATOR, put_drivers_on_duty


@pytest.fixture
def pool(monkeypatch):
    vehicles_repo.seed_default_vehicles(3, 15)
    operators_repo.seed_dispatch_operators(6)
    put_drivers_on_duty()
    recs = [{"station_id": sid, "station_name": sid, "district": "板橋區",
             "action": "補車", "quantity": 3, "current_available": 2,
             "target_available": 5, "total_docks": 20, "priority_score": 80,
             "lat": 25.01, "lng": 121.46} for sid in ("A", "B", "C")]
    monkeypatch.setattr("api.dispatch._current_dispatch_list", lambda: deepcopy(recs))
    monkeypatch.setattr(task_execution, "_demand_resolved", lambda sid: False)
    return recs


def draft(pool, car="CAR-001", driver="OP-004", ids=("A", "B")):
    return dispatch_builder.build_emergency(list(ids), pool, vehicle_id=car,
                                           operator_id=driver, created_by="OP-002")


def confirm(client, preview, headers=OP_DISPATCHER, path="confirm-trip"):
    return client.post(f"/api/v1/dispatch/{path}", json={"draft": preview}, headers=headers)


def report(client, tid, sid, value, driver="OP-004"):
    return client.post(f"/api/v1/dispatch/tasks/{tid}/report",
                       json={"station_id": sid, "actual_available": value},
                       headers={"X-Operator-Id": driver})


@pytest.mark.parametrize("path,body", [
    ("/dispatch/build/from-vehicle", {"vehicle_id": "CAR-001", "operator_id": "OP-004"}),
    ("/dispatch/build/from-station", {"station_id": "A"}),
    ("/dispatch/build/emergency", {"station_ids": ["A"]}),
    ("/dispatch/confirm-trip", {"draft_id": "fake", "version": 1}),
    ("/dispatch/confirm", {"draft_id": "fake", "version": 1}),
    ("/emergency/check", {"persist": True}),
])
def test_all_dispatch_gates_require_role(client, pool, path, body):
    assert client.post("/api/v1" + path, json=body).status_code == 401
    assert client.post("/api/v1" + path, json=body, headers=OP_OPERATOR).status_code == 403
    assert tasks_repo.list_tasks() == []


def test_emergency_check_cannot_persist_even_with_role(client, pool):
    before = vehicles_repo.list_vehicles()
    assert client.post("/api/v1/emergency/check", json={"persist": True},
                       headers=OP_DISPATCHER).status_code == 422
    assert vehicles_repo.list_vehicles() == before
    assert tasks_repo.list_tasks() == []


@pytest.mark.parametrize("field,value", [
    ("assigned_vehicle", "CAR-003"), ("assigned_operator", "OP-006"),
    ("mode", "normal"), ("stations", [{"station_id": "FAKE"}]), ("version", 2),
])
def test_tampered_preview_rejected(client, pool, field, value):
    preview = draft(pool)
    preview[field] = value
    assert confirm(client, preview).status_code == 409
    assert tasks_repo.list_tasks() == []
    assert vehicles_repo.get_vehicle("CAR-001")["status"] == "available"


def test_unknown_and_expired_draft_rejected(client, pool, monkeypatch):
    assert client.post("/api/v1/dispatch/confirm-trip", json={"draft_id": "FAKE", "version": 1},
                       headers=OP_DISPATCHER).status_code == 409
    preview = draft(pool)
    now = dispatch_drafts.time.monotonic()
    monkeypatch.setattr(dispatch_drafts.time, "monotonic", lambda: now + 10000)
    assert confirm(client, preview).status_code == 409


def test_preview_has_no_claims_and_retries_survive_draft_reset(client, pool):
    preview = draft(pool)
    assert tasks_repo.list_tasks() == []
    assert task_execution.station_claim_map() == {}
    first = confirm(client, preview)
    assert first.status_code == 200
    dispatch_drafts.reset_drafts()
    assert confirm(client, preview, path="confirm").json() == first.json()
    assert len(tasks_repo.list_tasks()) == 1
    assert audit_repo.count() == 1
    assert tasks_repo.get(first.json()["trip_id"])["task_type"] == "emergency"


@pytest.mark.parametrize("car,driver,ids", [
    ("CAR-001", "OP-005", ("C",)),
    ("CAR-002", "OP-004", ("C",)),
    ("CAR-002", "OP-005", ("A",)),
])
def test_two_drafts_cannot_share_resources_or_station(client, pool, car, driver, ids):
    a, b = draft(pool), draft(pool, car, driver, ids)
    assert confirm(client, a).status_code == 200
    assert confirm(client, b).status_code == 409
    assert len(tasks_repo.list_tasks()) == 1
    assert confirmations_repo.get(b["draft_id"]) is None


def test_parallel_confirmations_have_one_winner(pool, monkeypatch, tmp_path):
    # 檔案 SQLite 使用獨立連線，驗證實際部署的交易行為。
    monkeypatch.setenv("YOUBIKE_DB_PATH", str(tmp_path / "dispatch.sqlite"))
    init_db()
    operators_repo.seed_default_operators()
    operators_repo.seed_dispatch_operators(6)
    vehicles_repo.seed_default_vehicles(3)
    put_drivers_on_duty()
    a, b = draft(pool), draft(pool)
    barrier = Barrier(2)

    def run(preview):
        barrier.wait(timeout=5)
        try:
            dispatch_builder.confirm_trip(preview, "OP-002")
            return "confirmed"
        except DispatchConflict:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(run, [a, b]))
    assert sorted(results) == ["confirmed", "conflict"]
    assert len(tasks_repo.list_tasks()) == 1


@pytest.mark.parametrize("failure_point", ["operator", "receipt", "audit"])
def test_confirm_failure_rolls_back_every_write(pool, monkeypatch, failure_point):
    preview = draft(pool)
    target, method = {"operator": (operators_repo, "assign_district"),
                      "receipt": (confirmations_repo, "insert"),
                      "audit": (audit_repo, "insert")}[failure_point]
    original = getattr(target, method)

    def fail_after_write(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("injected write failure")

    with monkeypatch.context() as patch:
        patch.setattr(target, method, fail_after_write)
        with pytest.raises(RuntimeError, match="injected"):
            dispatch_builder.confirm_trip(preview, "OP-002")
    assert tasks_repo.list_tasks() == []
    assert confirmations_repo.get(preview["draft_id"]) is None
    assert audit_repo.count() == 0
    assert vehicles_repo.get_vehicle("CAR-001")["current_task_id"] is None
    assert operators_repo.get_operator("OP-004")["status"] == "on_duty"
    assert dispatch_builder.confirm_trip(preview, "OP-002")["confirmed"]


@pytest.mark.parametrize("value", [-1, -7.5, 2.5, True, "5", None, 21])
def test_invalid_inventory_never_changes_task(client, pool, value):
    tid = confirm(client, draft(pool)).json()["trip_id"]
    before = tasks_repo.get(tid)
    assert report(client, tid, "A", value).status_code == 422
    assert tasks_repo.get(tid) == before


def test_other_operator_cannot_start_report_or_return(client, pool):
    tid = confirm(client, draft(pool)).json()["trip_id"]
    assert report(client, tid, "A", 5, "OP-005").status_code == 403
    for action, body in (("start", {}), ("return", {"reason": "退回"})):
        response = client.post(f"/api/v1/dispatch/tasks/{tid}/{action}", json=body,
                               headers={"X-Operator-Id": "OP-005"})
        assert response.status_code == 403
    assert tasks_repo.get(tid)["task_status"] == "assigned"


def test_last_report_completes_and_releases_without_replay_reassignment(client, pool):
    preview = draft(pool)
    tid = confirm(client, preview).json()["trip_id"]
    assert report(client, tid, "A", 5).json()["status"] == "in_progress"
    assert report(client, tid, "B", 5).json()["status"] == "completed"
    assert vehicles_repo.get_vehicle("CAR-001")["current_task_id"] is None
    assert operators_repo.get_operator("OP-004")["status"] == "on_duty"
    assert task_execution.station_claim_map() == {}
    assert report(client, tid, "B", 6).status_code == 409
    assert confirm(client, preview).json()["status"] == "completed"
    assert vehicles_repo.get_vehicle("CAR-001")["status"] == "available"
    # ADR-123：補車趟結案後車上剩餘不足再跑一趟，需先重新裝載並回報（結案推算已寫回載量）
    assert vehicles_repo.get_vehicle("CAR-001")["onboard_bikes"] == 1
    assert confirm(client, draft(pool)).status_code == 409
    vehicles_repo.report_onboard("CAR-001", 15, "manual_report")
    assert confirm(client, draft(pool)).status_code == 200


@pytest.mark.parametrize("start,expected", [(False, "cancelled"), (True, "manual_required")])
def test_executor_return_releases_claims_and_resources(client, pool, start, expected):
    tid = confirm(client, draft(pool)).json()["trip_id"]
    if start:
        assert client.post(f"/api/v1/dispatch/tasks/{tid}/start",
                           headers={"X-Operator-Id": "OP-004"}).status_code == 200
    response = client.post(f"/api/v1/dispatch/tasks/{tid}/return", json={"reason": "車輛故障"},
                           headers={"X-Operator-Id": "OP-004"})
    assert response.status_code == 200
    assert tasks_repo.get(tid)["task_status"] == expected
    assert task_execution.station_claim_map() == {}
    assert vehicles_repo.get_vehicle("CAR-001")["current_task_id"] is None
    assert operators_repo.get_operator("OP-004")["current_task_id"] is None


def test_reserve_vehicle_returns_to_standby(client, pool):
    vehicles_repo.set_status("CAR-001", "standby")
    tid = confirm(client, draft(pool, ids=("A",))).json()["trip_id"]
    assert report(client, tid, "A", 5).status_code == 200
    assert vehicles_repo.get_vehicle("CAR-001")["status"] == "standby"


def test_completion_audit_failure_rolls_back_route_and_resource_release(client, pool, monkeypatch):
    tid = confirm(client, draft(pool, ids=("A",))).json()["trip_id"]
    before = tasks_repo.get(tid)
    monkeypatch.setattr(audit_repo, "insert", lambda log: (_ for _ in ()).throw(RuntimeError("audit")))
    with pytest.raises(RuntimeError):
        task_execution.report_station(tid, "A", 5, "OP-004")
    assert tasks_repo.get(tid) == before
    assert vehicles_repo.get_vehicle("CAR-001")["current_task_id"] == tid
    assert operators_repo.get_operator("OP-004")["current_task_id"] == tid
