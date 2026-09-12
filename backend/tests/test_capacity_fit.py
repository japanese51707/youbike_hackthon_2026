"""ADR-334：單站需求超過車容量時，不得讓整張單卡死。

實務現象：早尖峰大站在動態目標水位下，單站補車量常常就超過一台車的載運量
（預設 15 台）。_pack_supply_aware_trip 是「seed 站無條件先入趟」，之後才逐站
檢查容量，所以 seed 一進來整趟總量就爆 → total_quantity_exceeds_capacity →
整張單被丟掉。每一站都這樣，結果就是「有上百個緊急站、上百名閒置人力、
數十台閒置車，卻一張都配不出來」。
"""

import tests.test_auto_dispatch as T
from core import auto_dispatch, donor_stations, dispatch_builder


def _big_recs(n=12, qty=28):
    """每一站的補車量都超過單車容量 15 台。"""
    return [
        {"station_id": f"B{i:03d}", "station_name": f"大站{i}", "district": "板橋區",
         "action": "補車", "quantity": qty, "priority_score": 90 - i,
         "priority_level": "high", "current_available": 1, "total_docks": 60,
         "lat": 25.01 + i * 0.004, "lng": 121.46 + i * 0.004}
        for i in range(n)
    ]


def test_oversized_demand_still_places_orders(monkeypatch):
    """單站需求 28 台 > 車容量 15 台時，仍要配得出單（補到做得到的水位）。"""
    T._setup()
    monkeypatch.setattr(donor_stations, "get_all_stations", lambda *a, **k: [])
    recs = _big_recs()
    monkeypatch.setattr(auto_dispatch, "_current_dispatch_list", lambda: [dict(r) for r in recs])

    placed = auto_dispatch.scan_once()
    assert placed, (
        "單站需求超過車容量不該讓整輪掛零，診斷："
        f"{auto_dispatch._last_diagnostics}")
    assert not auto_dispatch._last_diagnostics.get("reasons"), \
        f"不應再有被擋原因：{auto_dispatch._last_diagnostics['reasons']}"


def test_trip_total_never_exceeds_vehicle_capacity(monkeypatch):
    """夾量之後，整趟搬運量一定落在車容量之內。"""
    T._setup()
    monkeypatch.setattr(donor_stations, "get_all_stations", lambda *a, **k: [])
    recs = _big_recs()
    draft = dispatch_builder.build_from_station(
        "B000", [dict(r) for r in recs], operator_id=None, created_by="OP-002")
    assert not draft.get("error")
    cap = draft["vehicle_capacity"]
    total = sum(int(s.get("quantity") or 0) for s in draft["stations"])
    assert total <= cap, f"整趟 {total} 台超過車容量 {cap} 台"
    assert draft["blocking_reasons"] == [], draft["blocking_reasons"]
    # 被夾小的站要誠實記下原始需求，讓後台知道這站只補了一部分
    clamped = [s for s in draft["stations"] if s.get("requested_quantity")]
    assert clamped, "需求被夾小時應記錄 requested_quantity"
    assert clamped[0]["requested_quantity"] > clamped[0]["quantity"]
