"""
故障/未啟用站處理測試（ADR-108 資料品質）
==========================================
可借=0 且 可還=0 = 站故障/離線，標 offline，不觸發調度/緊急度，KPI 分開計。
"""
from __future__ import annotations

from core.data.data_source import classify_status
from core.rule_engine import evaluate_station
from core import emergency


def test_classify_offline():
    assert classify_status(0, 0, 0) == "offline"          # 可借0+可還0
    assert classify_status(0, 0, 20) == "empty"           # 可借0但可還20 → 真空站
    assert classify_status(100, 20, 0) == "full"          # 可還0 → 滿站
    assert classify_status(50, 10, 10) == "normal"


def _st(sid, total, bikes, docks, status=None):
    s = {"station_id": sid, "station_name": sid, "district": "板橋區",
         "total_docks": total, "available_bikes": bikes, "available_docks": docks,
         "lat": 25.0, "lng": 121.46}
    if status:
        s["status"] = status
    return s


def test_offline_not_triggered():
    """故障站（0/0）不觸發調度建議。"""
    off = _st("故障", 20, 0, 0, status="offline")
    assert evaluate_station(off, prediction=None) is None
    # 即使沒帶 status，靠 0/0 也判定
    off2 = _st("故障2", 20, 0, 0)
    assert evaluate_station(off2, prediction=None) is None


def test_real_empty_still_triggers():
    """真空站（可借0但可還>0）仍走原邏輯（保底門檻觸發補車）。"""
    empty = _st("真空", 40, 0, 40)   # 借用率 0% < 低水位門檻
    empty["usage_rate"] = 0
    rec = evaluate_station(empty, prediction=None)
    assert rec is not None
    assert rec["action"] == "補車"


def test_offline_not_deadlock():
    """故障站不被誤判為死結。"""
    dl = emergency.detect_deadlocks([
        _st("故A", 50, 0, 0), _st("故B", 50, 0, 0), _st("故C", 50, 0, 0)])
    assert dl == []


def test_real_full_still_deadlock():
    """真滿站死結仍抓得到（不受故障排除影響）。"""
    dl = emergency.detect_deadlocks([
        _st("滿A", 50, 50, 0), _st("滿B", 48, 48, 0), _st("滿C", 45, 45, 0)])
    assert len(dl) == 1
    assert dl[0]["count"] == 3
