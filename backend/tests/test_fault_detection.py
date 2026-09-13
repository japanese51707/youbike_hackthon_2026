"""
ADR-336 熱門站設備故障偵測測試
==============================
守住：熱門站近半小時卡在下限借不到全空→疑似車故障；卡在下限還不到全滿→疑似柱故障；
非熱門站不判；序列不足不判；有碰到極值（借到空/還到滿）不判；扣除故障後重算空滿率。
純函式為主，monkeypatch 掉序列來源與熱門判斷，不依賴 clock DB。
"""
from __future__ import annotations

import pytest

from core import fault_detection as fd


def _series(bikes_docks):
    """[(bikes, docks), ...] → snapshot 序列（total 固定 20）。"""
    return [{"available_bikes": b, "available_docks": d, "total_docks": 20}
            for b, d in bikes_docks]


@pytest.fixture(autouse=True)
def _hot(monkeypatch):
    # 預設把待測站當熱門站（熱門判斷另有測試）
    monkeypatch.setattr(fd, "is_hot_station", lambda s: True)


def _patch_series(monkeypatch, series):
    monkeypatch.setattr(fd, "_series_since", lambda sid, minutes: series)


def test_vehicle_fault_when_stuck_above_empty(monkeypatch):
    """可借車數半小時卡在 3~4 台、從沒借到空 → 疑似 3 台車故障。"""
    _patch_series(monkeypatch, _series([(3, 17), (4, 16), (3, 17), (3, 17), (4, 16), (3, 17)]))
    r = fd.detect_fault({"station_id": "H1"})
    assert r and r["fault_type"] == "vehicle" and r["fault_count"] == 3


def test_dock_fault_when_stuck_above_full(monkeypatch):
    """可還位半小時卡在 2~3 個、從沒還到滿 → 疑似 2 個柱故障。"""
    _patch_series(monkeypatch, _series([(17, 3), (18, 2), (17, 3), (18, 2), (17, 3), (18, 2)]))
    r = fd.detect_fault({"station_id": "H2"})
    assert r and r["fault_type"] == "dock" and r["fault_count"] == 2


def test_no_fault_when_reaches_empty(monkeypatch):
    """有借到全空（bikes 觸 0）→ 正常熱門站，不判故障。"""
    _patch_series(monkeypatch, _series([(5, 15), (0, 20), (3, 17), (0, 20), (4, 16), (1, 19)]))
    assert fd.detect_fault({"station_id": "H3"}) is None


def test_no_fault_when_varies_widely(monkeypatch):
    """可借車數變化大（1~12）→ 車有在流動，不算卡住。"""
    _patch_series(monkeypatch, _series([(1, 19), (12, 8), (3, 17), (10, 10), (2, 18), (8, 12)]))
    assert fd.detect_fault({"station_id": "H4"}) is None


def test_no_fault_when_series_too_short(monkeypatch):
    """序列不足最小筆數 → 不判（避免剛開機誤判）。"""
    _patch_series(monkeypatch, _series([(3, 17), (3, 17)]))
    assert fd.detect_fault({"station_id": "H5"}) is None


def test_non_hot_station_not_judged(monkeypatch):
    """非熱門站一律不判故障。"""
    monkeypatch.setattr(fd, "is_hot_station", lambda s: False)
    _patch_series(monkeypatch, _series([(3, 17)] * 6))
    assert fd.detect_fault({"station_id": "N1"}) is None
