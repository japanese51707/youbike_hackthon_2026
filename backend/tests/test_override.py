"""③覆寫測試（A3）：置頂不改分數、到期自動恢復、到期連動取消未開始任務。"""

from core.override_service import OverrideService
from core.task_manager import TaskManager, IllegalTransition
from core.audit import AuditService
from core.dispatcher import build_dispatch_list
from config_loader import get_config


def _stations():
    """兩個都會觸發的站（一空一滿），讓建議清單有 ≥2 筆可測排序。"""
    return [
        {"station_id": "A", "station_name": "空站", "district": "區", "total_docks": 40,
         "available_bikes": 1, "usage_rate": 2.5, "lat": 25, "lng": 121},
        {"station_id": "B", "station_name": "滿站", "district": "區", "total_docks": 40,
         "available_bikes": 39, "usage_rate": 97.5, "lat": 25, "lng": 121},
    ]


def test_override_moves_to_front_without_changing_score():
    """覆寫站排到最前，且 priority_score 不被竄改。"""
    cfg = get_config()
    stations = _stations()
    base = build_dispatch_list(stations, cfg)
    # 找一個「非第一名」的站來覆寫
    assert len(base) >= 2
    target = base[-1]["station_id"]
    target_score = base[-1]["priority_score"]

    with_ov = build_dispatch_list(stations, cfg, override_station_ids={target})
    assert with_ov[0]["station_id"] == target
    assert with_ov[0]["override_active"] is True
    # 分數不變（覆寫只改排序，不動 urgency）
    assert with_ov[0]["priority_score"] == target_score


def test_override_expires_and_auto_recovers():
    """覆寫到期後，生效清單自動移除（惰性恢復）。"""
    audit = AuditService()
    ov = OverrideService(audit=audit)
    ov.apply("A", reason="測試", operator="OP-002", expire_minutes=-1)  # 立即過期
    assert "A" not in ov.active_station_ids()


def test_expire_cancels_assigned_task_keeps_in_progress():
    """覆寫到期：assigned 任務取消、in_progress 保留、無關任務不動。"""
    audit = AuditService()
    tm = TaskManager()
    ov = OverrideService(audit=audit, task_manager=tm)
    ov.apply("A", reason="活動", operator="OP-002", expire_minutes=-1)

    tm.create({"task_id": "T1", "task_type": "emergency", "source_override_station_id": "A"})
    tm.assign("T1", "OP-001")
    tm.create({"task_id": "T2", "task_type": "emergency", "source_override_station_id": "A"})
    tm.assign("T2", "OP-001")
    tm.start("T2")   # 執行中
    tm.create({"task_id": "T3", "task_type": "normal", "source_override_station_id": None})
    tm.assign("T3", "OP-001")

    ov.active_station_ids()   # 觸發到期 → 連動取消

    assert tm.get("T1")["task_status"] == "cancelled"      # assigned 被取消
    assert tm.get("T2")["task_status"] == "in_progress"    # 執行中保留
    assert tm.get("T3")["task_status"] == "assigned"       # 無關任務不動


def test_in_progress_cannot_be_cancelled():
    """狀態機保護：in_progress 不能被 cancel。"""
    tm = TaskManager()
    tm.create({"task_id": "T", "task_type": "emergency"})
    tm.assign("T", "OP-001")
    tm.start("T")
    try:
        tm.cancel("T")
        assert False, "in_progress 不該可取消"
    except IllegalTransition:
        pass


def test_override_and_cascade_both_audited():
    """覆寫與連動取消都留稽核。"""
    audit = AuditService()
    tm = TaskManager()
    ov = OverrideService(audit=audit, task_manager=tm)
    ov.apply("A", reason="活動", operator="OP-002", expire_minutes=-1)
    tm.create({"task_id": "T1", "task_type": "emergency", "source_override_station_id": "A"})
    tm.assign("T1", "OP-001")
    ov.active_station_ids()

    types = [log["type"] for log in audit.all()]
    assert "emergency_override" in types   # 覆寫本身
    assert "task_transfer" in types        # 連動取消
