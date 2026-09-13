"""ADR-335：分級催辦通知的行為契約。"""

import datetime as _dt

import pytest

from core import notification_service as NS
from db import notifications_repo

NOW = _dt.datetime(2026, 9, 13, 9, 0, tzinfo=_dt.timezone.utc)
CFG = {"escalation": {"階段": [30, 45, 60], "持續提醒間隔_分鐘": 15,
                      "合併門檻_件數": 3, "靜音分鐘": 10}}


def _case(cid, waited, district="板橋區", operator=None):
    case = {"case_id": cid, "station_id": cid, "station_name": f"站{cid}",
            "district": district, "waited_minutes": waited, "closed_at": None,
            "stage_thresholds": [30, 45, 60]}
    if operator:
        case["responsibility_status"] = "assigned"
        case["assignments"] = [{"task_id": f"T{cid}", "operator_id": operator}]
    else:
        case["responsibility_status"] = "unassigned"
        case["assignments"] = []
    return case


# ── 階段界線：用精確秒數，不能用顯示的四捨五入分鐘 ──────────────────
@pytest.mark.parametrize("waited,expected", [
    (29.9, 0), (30.0, 1), (44.99, 1), (45.0, 2), (59.9, 2), (60.0, 3), (600.0, 3),
])
def test_stage_boundaries_use_exact_minutes(waited, expected):
    assert NS.stage_for(waited, [30, 45, 60]) == expected


def test_repeat_reminders_after_top_stage():
    """達最高階段後每 15 分鐘再提醒一次，直到確認解除。"""
    stages = [30, 45, 60]
    assert NS.reminder_index_for(60, stages, 3, 15) == 0
    assert NS.reminder_index_for(74.9, stages, 3, 15) == 0
    assert NS.reminder_index_for(75, stages, 3, 15) == 1
    assert NS.reminder_index_for(92, stages, 3, 15) == 2
    # 未達最高階段不重覆提醒
    assert NS.reminder_index_for(46, stages, 2, 15) == 0


# ── 收件者 ────────────────────────────────────────────────────────
def test_unassigned_case_notifies_controllers_only():
    """沒有承辦就只通知管理端，不能把所有司機都當收件者。"""
    rows = NS.build_notifications([_case("A", 31)], ["CTL-1"], now=NOW, config=CFG)
    assert {r["recipient_id"] for r in rows} == {"CTL-1"}
    assert rows[0]["recipient_role"] == "controller"


def test_assigned_case_notifies_driver_and_controller():
    rows = NS.build_notifications([_case("B", 46, operator="OP-100")], ["CTL-1"],
                                  now=NOW, config=CFG)
    by_id = {r["recipient_id"]: r for r in rows}
    assert set(by_id) == {"OP-100", "CTL-1"}
    assert by_id["OP-100"]["recipient_role"] == "driver"


def test_conflicting_assignment_goes_to_controller_only():
    """多張未結案任務涵蓋同站是資料異常，不任選一人扛。"""
    case = _case("C", 46)
    case["responsibility_status"] = "conflict"
    case["assignments"] = [{"task_id": "T1", "operator_id": "OP-1"},
                           {"task_id": "T2", "operator_id": "OP-2"}]
    rows = NS.build_notifications([case], ["CTL-1"], now=NOW, config=CFG)
    assert {r["recipient_id"] for r in rows} == {"CTL-1"}


# ── 合併：早尖峰上百站同時緊急不得逐站轟炸 ─────────────────────────
def test_same_district_same_stage_merges_into_digest():
    cases = [_case(f"D{i}", 61) for i in range(5)]   # 5 件 > 門檻 3
    rows = NS.build_notifications(cases, ["CTL-1"], now=NOW, config=CFG)
    assert len(rows) == 1, "超過合併門檻應只送一則區級摘要"
    assert rows[0]["digest_key"] == "板橋區:3"
    assert "5 站" in rows[0]["body"]


def test_under_threshold_still_sends_per_station():
    cases = [_case(f"E{i}", 61) for i in range(3)]   # 3 件 = 門檻，不合併
    rows = NS.build_notifications(cases, ["CTL-1"], now=NOW, config=CFG)
    assert len(rows) == 3
    assert all(r["digest_key"] is None for r in rows)


# ── 冪等與每人已讀 ────────────────────────────────────────────────
def test_notifications_are_idempotent():
    cases = [_case("F", 31, operator="OP-100")]
    first = NS.sync_notifications(cases, ["CTL-1"], now=NOW, config=CFG)
    second = NS.sync_notifications(cases, ["CTL-1"], now=NOW, config=CFG)
    assert len(first) == len(second) == 2
    assert len(notifications_repo.list_for_case("F")) == 2, "重複同步不得重複送"


def test_one_persons_ack_does_not_mute_the_other():
    """★司機按已讀不會替管理端消音——舊設計的全域靜音正是升級永不觸發的原因。"""
    cases = [_case("G", 46, operator="OP-100")]
    NS.sync_notifications(cases, ["CTL-1"], now=NOW, config=CFG)
    driver = [n for n in notifications_repo.list_for_case("G")
              if n["recipient_id"] == "OP-100"][0]
    notifications_repo.mark(driver["notification_id"], "acknowledged_at",
                            NOW.isoformat(), recipient_id="OP-100")
    controller = [n for n in notifications_repo.list_for_case("G")
                  if n["recipient_id"] == "CTL-1"][0]
    assert controller["acknowledged_at"] is None


def test_ack_does_not_block_the_next_stage():
    """已讀不擋下一階段：45 分的提醒照樣建立。"""
    NS.sync_notifications([_case("H", 31, operator="OP-100")], ["CTL-1"],
                          now=NOW, config=CFG)
    for row in notifications_repo.list_for_case("H"):
        notifications_repo.mark(row["notification_id"], "acknowledged_at",
                                NOW.isoformat(), recipient_id=row["recipient_id"])
    NS.sync_notifications([_case("H", 46, operator="OP-100")], ["CTL-1"],
                          now=NOW + _dt.timedelta(minutes=15), config=CFG)
    stages = {n["stage"] for n in notifications_repo.list_for_case("H")}
    assert stages == {1, 2}


def test_transfer_creates_notification_for_new_owner():
    """轉派後新承辦收得到自己的提醒，但緊急時間不重算。"""
    NS.sync_notifications([_case("I", 46, operator="OP-100")], ["CTL-1"],
                          now=NOW, config=CFG)
    NS.sync_notifications([_case("I", 47, operator="OP-200")], ["CTL-1"],
                          now=NOW + _dt.timedelta(minutes=1), config=CFG)
    owners = {n["recipient_id"] for n in notifications_repo.list_for_case("I")}
    assert {"OP-100", "OP-200", "CTL-1"} <= owners
