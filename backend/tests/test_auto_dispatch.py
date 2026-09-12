"""
ADR-319 自動配單測試
====================
驗證系統為主的自動配單：依緊急度逐一配對鄰近人車直接落地，配完一張標記該站已配、
過濾後再配下一筆；避開已被任務認領的站與人工手動預覽/草稿佔用的站。

_current_dispatch_list 依賴即時資料源 + 全站規則引擎，測試以 monkeypatch 換成固定緊急
清單，聚焦驗證 scan_once 的配單/過濾/序列化行為。
"""
from __future__ import annotations

import pytest

from tests.conftest import put_drivers_on_duty
from db import vehicles_repo as vr, operators_repo as orp, tasks_repo
from core.providers import reset_providers
from core import auto_dispatch, dispatch_builder
from core.task_execution import station_claim_map


def _rec(sid, dist, act, qty, score, avail, lat, lng, level="high"):
    return {"station_id": sid, "station_name": sid, "district": dist,
            "action": act, "quantity": qty, "priority_score": score,
            "priority_level": level, "current_available": avail,
            "lat": lat, "lng": lng, "total_docks": 60}


def _setup():
    vr.seed_default_vehicles(10, 15)
    vr.seed_depot_vehicles(3, 15)
    orp.seed_dispatch_operators(20)
    orp.seed_depot_standby_operators(5)
    put_drivers_on_duty()
    reset_providers()


# 三個不同區的緊急站（分開避免一張單就吃掉多站，方便驗證逐張配）
DL = [
    _rec("板橋空", "板橋區", "補車", 6, 92, 2, 25.012, 121.462),
    _rec("三重空", "三重區", "補車", 6, 80, 2, 25.060, 121.490),
    _rec("新莊空", "新莊區", "補車", 6, 70, 2, 25.036, 121.432),
]


def _patch_list(monkeypatch, recs):
    monkeypatch.setattr(auto_dispatch, "_current_dispatch_list", lambda: [dict(r) for r in recs])


def test_scan_once_places_orders_and_claims_stations(monkeypatch):
    _setup()
    _patch_list(monkeypatch, DL)

    placed = auto_dispatch.scan_once()
    assert placed, "應至少配出一張派工單"
    # 落地的站被認領（進 station_claim_map）
    claimed = station_claim_map()
    placed_stations = {s for p in placed for s in p["stations"]}
    assert placed_stations, "配出的單應涵蓋站點"
    assert placed_stations <= set(claimed.keys()), "落地站應全部被任務認領"
    # 每張單都有指派車與人
    for p in placed:
        assert p["vehicle"] and p["operator"]


def test_second_scan_does_not_reassign_claimed_stations(monkeypatch):
    _setup()
    _patch_list(monkeypatch, DL)

    first = auto_dispatch.scan_once()
    first_seeds = {p["seed_station"] for p in first}
    assert first_seeds

    # 第二輪：同一份緊急清單。已被第一輪認領的站不應再配（station_claim_map 過濾）。
    second = auto_dispatch.scan_once()
    second_seeds = {p["seed_station"] for p in second}
    assert first_seeds.isdisjoint(second_seeds), "已認領站不應被第二輪重配"


def test_auto_dispatch_skips_manual_draft_stations(monkeypatch):
    _setup()
    _patch_list(monkeypatch, DL)

    # 模擬「人正在手動預覽/草稿」板橋空：建一張人工草稿（created_by 非系統身分）。
    draft = dispatch_builder.build_from_station("板橋空", [dict(r) for r in DL],
                                                created_by="OP-777")
    assert draft.get("draft_id")

    placed = auto_dispatch.scan_once()
    placed_seeds = {p["seed_station"] for p in placed}
    covered = {s for p in placed for s in p["stations"]}
    assert "板橋空" not in placed_seeds, "人工草稿佔用的站不應被自動配單當種子"
    assert "板橋空" not in covered, "人工草稿佔用的站不應被自動配單涵蓋"


def test_respects_max_orders_per_round(monkeypatch):
    _setup()
    _patch_list(monkeypatch, DL)
    monkeypatch.setitem(auto_dispatch._cfg(), "每輪最大配單數", 1)
    # _cfg() 回的是 config 的參照的 copy? 用 config 就地覆寫確保生效
    from config_loader import get_config
    monkeypatch.setitem(get_config().setdefault("auto_dispatch", {}), "每輪最大配單數", 1)

    placed = auto_dispatch.scan_once()
    assert len(placed) <= 1, "單輪配單數不應超過上限"


def test_stops_round_when_no_available_vehicle(monkeypatch):
    """ADR-319：沒有閒置車可出勤時，本輪停止自動配單（不繼續掃其他站）。"""
    # 只 seed 人力，不 seed 任何車（無一般閒置車、無總部待命車）
    orp.seed_dispatch_operators(20)
    orp.seed_depot_standby_operators(5)
    put_drivers_on_duty()
    reset_providers()
    _patch_list(monkeypatch, DL)

    placed = auto_dispatch.scan_once()
    assert placed == [], "無車可派時本輪不應配出任何單"


def test_runtime_switch_disables_dispatch(monkeypatch):
    """ADR-319：後台關閉開關後，本輪不配單；重新開啟後恢復。"""
    _setup()
    _patch_list(monkeypatch, DL)
    from core import auto_dispatch as ad

    ad.set_enabled(False)
    assert ad.scan_once() == [], "關閉自動配單後不應配出任何單"
    ad.set_enabled(True)
    assert ad.scan_once(), "重新開啟後應恢復配單"
    ad.reset_runtime_enabled()


def test_auto_dispatch_toggle_endpoint(client):
    """ADR-319：後台開關端點——GET 讀狀態、POST 需 dispatcher 權限、即時生效。"""
    from tests.conftest import OP_DISPATCHER, OP_OPERATOR

    # GET 讀狀態（免權限，供儀表板顯示）
    r = client.get("/api/v1/dispatch/auto-dispatch")
    assert r.status_code == 200
    assert "enabled" in r.json() and "interval_sec" in r.json()

    # 一般 operator 不可切換
    r = client.post("/api/v1/dispatch/auto-dispatch", json={"enabled": False}, headers=OP_OPERATOR)
    assert r.status_code == 403

    # dispatcher 可關閉
    r = client.post("/api/v1/dispatch/auto-dispatch", json={"enabled": False}, headers=OP_DISPATCHER)
    assert r.status_code == 200 and r.json()["enabled"] is False
    assert client.get("/api/v1/dispatch/auto-dispatch").json()["enabled"] is False

    # 缺 enabled 欄位 → 422
    r = client.post("/api/v1/dispatch/auto-dispatch", json={"x": 1}, headers=OP_DISPATCHER)
    assert r.status_code == 422

    # dispatcher 可重新開啟
    r = client.post("/api/v1/dispatch/auto-dispatch", json={"enabled": True}, headers=OP_DISPATCHER)
    assert r.status_code == 200 and r.json()["enabled"] is True

    from core import auto_dispatch
    auto_dispatch.reset_runtime_enabled()


def test_only_configured_levels_are_dispatched(monkeypatch):
    _setup()
    mixed = [
        _rec("板橋空", "板橋區", "補車", 6, 92, 2, 25.012, 121.462, level="high"),
        _rec("三重低", "三重區", "補車", 3, 30, 2, 25.060, 121.490, level="low"),
    ]
    _patch_list(monkeypatch, mixed)
    from config_loader import get_config
    monkeypatch.setitem(get_config().setdefault("auto_dispatch", {}), "只配緊急級別", ["high"])

    placed = auto_dispatch.scan_once()
    covered = {s for p in placed for s in p["stations"]}
    assert "三重低" not in covered, "非指定緊急級別的站不應被自動配單"
