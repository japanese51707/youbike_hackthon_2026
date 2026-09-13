"""
ADR-309 緊急調度案件升級追蹤
==============================
守住三件事（這三件是整個機制有沒有意義的關鍵）：
  1. 時鐘掛在案件上——警示重建、按已讀都不得重置 opened_at。
  2. 關案只認確定性事件——有未結案任務涵蓋該站，或站況恢復。人按按鈕不關案。
  3. 階段與靜音的交互——靜音只是暫時不打擾，時鐘照走，到期回到應在的階段。
"""
from __future__ import annotations

import datetime as _dt

import pytest

from core import escalation
from db import escalation_repo


def _station(station_id="S1", status="empty", district="板橋區"):
    return {"station_id": station_id, "station_name": f"測試站{station_id}",
            "district": district, "status": status, "lat": 25.0, "lng": 121.4}


def _rec(station_id="S1", level="high", tier="censored"):
    return {"station_id": station_id, "priority_level": level, "urgency_tier": tier,
            "action": "補車", "quantity": 10, "reason": "已空站仍將持續流出"}


def _task(station_id="S1", status="assigned", operator="OP-004"):
    return {"task_id": "T1", "task_status": status, "assigned_operator": operator,
            "route": [{"station_id": station_id, "station_name": "測試站",
                       "station_status": "pending"}]}


CFG = {"escalation": {"階段": [30, 45], "靜音分鐘": 10,
                      "值班聯絡": {"預設": {"姓名": "值班", "電話": "02-0000-0000"}}}}
T0 = _dt.datetime(2026, 9, 12, 9, 0, 0)


# ── 開案與關案 ──

def test_empty_station_opens_a_case():
    cases = escalation.sync_cases([_station()], [_rec()], [], CFG, now=T0)
    assert len(cases) == 1
    assert cases[0]["station_id"] == "S1"
    assert cases[0]["opened_at"] == T0.isoformat(timespec="seconds")


def test_normal_station_never_opens_a_case():
    assert escalation.sync_cases([_station(status="normal")], [], [], CFG, now=T0) == []


def test_only_top_urgency_opens_a_case():
    """警示有三級，案件只追最緊急那層——否則管理後台會被黃色案件淹沒。"""
    mid = _rec(level="medium", tier="warning")
    assert escalation.needs_case(_station(status="low"), mid) is False
    assert escalation.needs_case(_station(status="low"), _rec()) is True


def test_reopening_does_not_reset_the_clock():
    """★核心：警示重建、反覆同步都不得改變 opened_at。"""
    escalation.sync_cases([_station()], [_rec()], [], CFG, now=T0)
    later = escalation.sync_cases([_station()], [_rec()], [], CFG,
                                  now=T0 + _dt.timedelta(minutes=20))
    assert later[0]["opened_at"] == T0.isoformat(timespec="seconds")
    assert later[0]["waited_minutes"] == pytest.approx(20.0, abs=0.2)


def test_dispatch_does_not_close_the_case():
    """ADR-335：派工只代表有人承辦，不代表問題解除——案件不關、時計不重設。

    取代 ADR-309 的 test_case_closes_when_a_task_covers_the_station。舊規則一派工就
    關案，等於停止催辦；司機還沒到、到了車不夠、補完又被借光，站其實一直是空的。
    """
    escalation.sync_cases([_station()], [_rec()], [], CFG, now=T0)
    after = escalation.sync_cases([_station()], [_rec()], [_task()], CFG,
                                  now=T0 + _dt.timedelta(minutes=5))
    assert len(after) == 1, "派工後案件必須繼續存在"
    assert after[0]["opened_at"] == T0.isoformat(timespec="seconds"), "時計不得重設"
    assert after[0]["waited_minutes"] == pytest.approx(5.0, abs=0.2)
    # 承辦責任要指出來，讓提醒送得到人
    assert after[0]["responsibility_status"] == "assigned"
    assert after[0]["responsible_operator"] == _task()["assigned_operator"]
    assert escalation_repo.get_open_case_by_station("S1") is not None


def test_only_confirmed_recovery_closes_the_case():
    """唯一的關案路徑：新鮮可信觀測確認不再緊急。"""
    escalation.sync_cases([_station()], [_rec()], [], CFG, now=T0)
    after = escalation.sync_cases([_station(status="normal")], [], [_task()], CFG,
                                  now=T0 + _dt.timedelta(minutes=5))
    assert after == []
    closed = escalation_repo.get_open_case_by_station("S1")
    assert closed is None


def test_missing_station_is_not_treated_as_recovery():
    """這輪沒看到這個站（缺站／查詢失敗）不能當成恢復。"""
    escalation.sync_cases([_station()], [_rec()], [], CFG, now=T0)
    after = escalation.sync_cases([], [], [], CFG, now=T0 + _dt.timedelta(minutes=5))
    assert len(after) == 1, "資料不知道不等於問題解決了"
    assert after[0]["observation_status"] == escalation.OBS_UNVERIFIED
    assert after[0]["waited_minutes"] == pytest.approx(5.0, abs=0.2)


def test_stale_observation_is_not_treated_as_recovery():
    """過期／離線的觀測同樣不得關案。"""
    escalation.sync_cases([_station()], [_rec()], [], CFG, now=T0)
    stale = {**_station(status="normal"), "data_freshness": "stale"}
    cfg = {**CFG, "data_source": {"mode": "youbike_official"}}
    after = escalation.sync_cases([stale], [], [], cfg, now=T0 + _dt.timedelta(minutes=5))
    assert len(after) == 1
    assert after[0]["observation_status"] == escalation.OBS_UNVERIFIED


def test_out_of_order_observation_cannot_reverse_state():
    """比上次確認更舊的觀測不得反轉案件狀態。"""
    fresh = {**_station(), "data_freshness": "live",
             "observed_at": (T0 + _dt.timedelta(minutes=10)).isoformat()}
    cfg = {**CFG, "data_source": {"mode": "youbike_official"}}
    escalation.sync_cases([fresh], [_rec()], [], cfg, now=T0)
    stale_recovery = {**_station(status="normal"), "data_freshness": "live",
                      "observed_at": (T0 + _dt.timedelta(minutes=2)).isoformat()}
    after = escalation.sync_cases([stale_recovery], [], [], cfg,
                                  now=T0 + _dt.timedelta(minutes=15))
    assert len(after) == 1, "舊觀測不得關掉已被較新觀測確認的案件"


def test_completed_task_does_not_count_as_handled():
    """已結案的任務不算在處理中——站還空著就該重新開案。"""
    escalation.sync_cases([_station()], [_rec()], [], CFG, now=T0)
    after = escalation.sync_cases([_station()], [_rec()], [_task(status="completed")],
                                  CFG, now=T0 + _dt.timedelta(minutes=5))
    assert len(after) == 1


def test_case_closes_when_station_recovers():
    escalation.sync_cases([_station()], [_rec()], [], CFG, now=T0)
    after = escalation.sync_cases([_station(status="normal")], [], [], CFG,
                                  now=T0 + _dt.timedelta(minutes=5))
    assert after == []


# ── 階段 ──

@pytest.mark.parametrize("minutes,stage", [(0, 0), (29, 0), (30, 1), (44, 1), (45, 2), (600, 2)])
def test_stage_thresholds(minutes, stage):
    case = {"opened_at": T0.isoformat(timespec="seconds")}
    assert escalation.stage_of(case, T0 + _dt.timedelta(minutes=minutes), CFG) == stage


def test_describe_reports_next_stage_and_flags():
    escalation.sync_cases([_station()], [_rec()], [], CFG, now=T0)
    at31 = escalation.sync_cases([_station()], [_rec()], [], CFG,
                                 now=T0 + _dt.timedelta(minutes=31))[0]
    assert at31["stage"] == 1
    assert at31["should_banner"] is True
    assert at31["should_prompt"] is False
    assert at31["next_stage_at"] == (T0 + _dt.timedelta(minutes=45)).isoformat(timespec="seconds")

    at46 = escalation.sync_cases([_station()], [_rec()], [], CFG,
                                 now=T0 + _dt.timedelta(minutes=46))[0]
    assert at46["stage"] == 2
    assert at46["should_prompt"] is True
    assert at46["next_stage_at"] is None
    assert at46["contact"]["電話"] == "02-0000-0000"


def test_stage_config_must_be_increasing():
    """設定寫錯（遞減）時退回預設，不能算出往回走的下一階段。"""
    bad = {"escalation": {"階段": [45, 30]}}
    case = {"opened_at": T0.isoformat(timespec="seconds")}
    assert escalation.stage_of(case, T0 + _dt.timedelta(minutes=46), bad) == 2


# ── 動作與靜音 ──

def test_acknowledge_mutes_but_does_not_close_or_reset():
    """★核心：按已讀不關案、不重置時鐘，只是暫時不打擾。"""
    case = escalation.sync_cases([_station()], [_rec()], [], CFG, now=T0)[0]
    at46 = T0 + _dt.timedelta(minutes=46)
    escalation.sync_cases([_station()], [_rec()], [], CFG, now=at46)
    after = escalation.record_action(case["case_id"], "acknowledged", "OP-1",
                                     config=CFG, now=at46)
    assert after["muted"] is True
    assert after["should_prompt"] is False          # 靜音中不跳彈窗
    assert after["stage"] == 2                      # 但階段沒有退回
    assert after["opened_at"] == T0.isoformat(timespec="seconds")
    assert escalation_repo.get_open_case_by_station("S1") is not None   # 沒關案

    # 靜音到期後照樣回到 L2
    revived = escalation.describe(escalation_repo.get_case(case["case_id"]),
                                  at46 + _dt.timedelta(minutes=11), CFG)
    assert revived["muted"] is False
    assert revived["should_prompt"] is True


def test_defer_requires_a_reason():
    case = escalation.sync_cases([_station()], [_rec()], [], CFG, now=T0)[0]
    with pytest.raises(ValueError):
        escalation.record_action(case["case_id"], "deferred", "OP-1", note="  ", config=CFG)


def test_called_requires_a_contact():
    case = escalation.sync_cases([_station()], [_rec()], [], CFG, now=T0)[0]
    with pytest.raises(ValueError):
        escalation.record_action(case["case_id"], "called", "OP-1", contact="", config=CFG)
    ok = escalation.record_action(case["case_id"], "called", "OP-1",
                                  contact="值班 02-0000-0000", config=CFG, now=T0)
    assert ok["muted"] is True


def test_actions_are_audited():
    case = escalation.sync_cases([_station()], [_rec()], [], CFG, now=T0)[0]
    escalation.record_action(case["case_id"], "deferred", "OP-9",
                             note="車隊全數出勤中", config=CFG, now=T0)
    actions = escalation_repo.list_actions(case["case_id"])
    assert len(actions) == 1
    assert actions[0]["actor"] == "OP-9"
    assert actions[0]["note"] == "車隊全數出勤中"


def test_unknown_action_and_missing_case_are_rejected():
    with pytest.raises(ValueError):
        escalation.record_action("CASE-X", "explode", "OP-1", config=CFG)
    with pytest.raises(LookupError):
        escalation.record_action("CASE-X", "acknowledged", "OP-1", config=CFG)


def test_describe_accepts_aware_opened_at_against_naive_now():
    """官方觀測帶時區、本機 now 常是 naive，兩者相減不得整頁 500。"""
    opened = _dt.datetime(2026, 9, 13, 2, 14, tzinfo=_dt.timezone.utc)
    case = {
        "case_id": "CASE-TZ",
        "station_id": "S1",
        "opened_at": opened.isoformat(),
        "district": "板橋區",
    }
    row = escalation.describe(case, now=T0, config=CFG)
    assert row["waited_minutes"] >= 0
    assert row["next_stage_at"]
    assert row["stage"] == 0


def test_next_stage_uses_taipei_wall_clock_not_container_utc():
    """naive 09:19 是台北牆上時間；10:20 台北不該算出還有 450 分。"""
    now = _dt.datetime(2026, 9, 13, 10, 20, tzinfo=_dt.timezone(_dt.timedelta(hours=8)))
    row = escalation.describe(
        {"case_id": "CASE-TZ2", "station_id": "S1",
         "opened_at": "2026-09-13T09:19:00", "district": "土城區"},
        now=now, config=CFG)
    assert 50 < row["waited_minutes"] < 70
    assert row["next_stage_in_minutes"] is not None
    assert abs(row["next_stage_in_minutes"]) < 60


def test_one_open_case_per_station():
    """同一站重複同步不得長出第二個未結案案件。"""
    for _ in range(3):
        escalation.sync_cases([_station()], [_rec()], [], CFG, now=T0)
    assert len([c for c in escalation_repo.list_open_cases() if c["station_id"] == "S1"]) == 1
