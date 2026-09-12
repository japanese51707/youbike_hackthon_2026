"""第三批 B（ADR-123／304）：路線載量守恆、逐站到達視野、工時與重疊、預覽＝確認。"""

import datetime as dt

import pytest

from core import dispatch_builder, task_execution
from core.dispatch_errors import DispatchConflict
from config_loader import get_config
from core.dispatch_feasibility import evaluate_feasibility, first_blocking_message
from db import operators_repo, tasks_repo, vehicles_repo
from tests.conftest import OP_DISPATCHER, put_drivers_on_duty

# 固定平日早班離峰（大夜班允許跨區，會讓跨區測試失效）
NOW = dt.datetime(2026, 6, 15, 11, 0)


def _stop(sid, action, qty, current, lat=25.01, lng=121.46, district="板橋區"):
    target = current + qty if action == "補車" else current - qty
    return {"station_id": sid, "station_name": sid, "district": district,
            "action": action, "quantity": qty, "current_available": current,
            "target_available": target, "total_docks": 40,
            "priority_score": 80, "lat": lat, "lng": lng}


def _vehicle(onboard=5, capacity=15, vid="CAR-001"):
    return {"vehicle_id": vid, "max_capacity": capacity, "onboard_bikes": onboard,
            "onboard_source": "manual_report",
            "onboard_observed_at": NOW.isoformat(timespec="seconds")}


def _operator(worked=0, oid="OP-004"):
    return {"operator_id": oid, "today_work_minutes": worked}


def _codes(result):
    return {r["code"] for r in result["blocking_reasons"]}


# ── 1. 車輛初始載量 ──

def test_unknown_onboard_is_blocked_not_assumed_zero():
    result = evaluate_feasibility([_stop("A", "取車", 3, 30)],
                                  {"vehicle_id": "CAR-001", "max_capacity": 15},
                                  _operator(), now=NOW, check_resources=False)
    assert "vehicle_onboard_unknown" in _codes(result)
    assert result["load_plan"][0]["onboard_after"] is None   # 不以 0 起算


def test_stale_onboard_report_is_blocked():
    vehicle = _vehicle()
    vehicle["onboard_observed_at"] = (NOW - dt.timedelta(hours=9)).isoformat()
    result = evaluate_feasibility([_stop("A", "取車", 3, 30)], vehicle, _operator(),
                                  now=NOW, check_resources=False)
    assert "vehicle_onboard_stale" in _codes(result)


def test_report_onboard_rejects_bad_values():
    vehicles_repo.seed_default_vehicles(1, 15)
    with pytest.raises(ValueError):
        vehicles_repo.report_onboard("CAR-001", 16, "manual_report")     # 超過容量
    with pytest.raises(ValueError):
        vehicles_repo.report_onboard("CAR-001", -1, "manual_report")     # 負數
    with pytest.raises(ValueError):
        vehicles_repo.report_onboard("CAR-001", 3, "guess")              # 來源不可追溯
    vehicles_repo.clear_onboard("CAR-001")
    assert vehicles_repo.get_vehicle("CAR-001")["onboard_bikes"] is None


# ── 2. 逐站載量守恆 ──

def test_total_within_capacity_but_midway_overflow_is_blocked():
    """總量 12 ≤ 容量 15，但先取三站就爆量——舊的總量檢查抓不到。"""
    stops = [_stop("M1", "取車", 6, 30), _stop("M2", "取車", 6, 30),
             _stop("M3", "補車", 12, 1)]
    result = evaluate_feasibility(stops, _vehicle(onboard=5), _operator(),
                                  now=NOW, check_resources=False)
    assert "load_exceeds_capacity" in _codes(result)
    assert result["load_plan"][1]["onboard_after"] == 17


def test_supply_without_enough_onboard_delivers_partially(): 
    """ADR-322：車上不夠不是失敗——放多少算多少，不阻擋。

    取代舊的 test_supply_without_enough_onboard_is_blocked：先取後放本來就可能
    放不滿安全水位，有補到就是完成。原本判 load_below_zero 會讓這種單全部配不出去。
    """
    stops = [_stop("S1", "補車", 8, 1)]
    result = evaluate_feasibility(stops, _vehicle(onboard=5), _operator(),
                                  now=NOW, check_resources=False)
    assert result["blocking_reasons"] == []
    entry = result["load_plan"][0]
    assert entry["delivered_quantity"] == 5      # 車上只有 5 台，就補 5 台
    assert entry["shortfall_quantity"] == 3      # 差額誠實記錄下來
    assert entry["onboard_after"] == 0
    assert result["onboard_end"] == 0


def test_supply_with_zero_onboard_is_still_blocked():
    """一台都沒有時仍要擋：那趟真的白跑，不該讓它出車。"""
    stops = [_stop("S1", "補車", 8, 1)]
    result = evaluate_feasibility(stops, _vehicle(onboard=0), _operator(),
                                  now=NOW, check_resources=False)
    assert "no_bikes_to_deliver" in _codes(result)


def test_partial_delivery_can_be_disabled_by_config():
    """關掉 允許部分補車 時回到舊行為（載量守恆嚴格模式）。"""
    cfg = dict(get_config())
    cfg["fleet"] = {**cfg.get("fleet", {}), "允許部分補車": False}
    stops = [_stop("S1", "補車", 8, 1)]
    result = evaluate_feasibility(stops, _vehicle(onboard=5), _operator(),
                                  now=NOW, check_resources=False, config=cfg)
    assert "load_below_zero" in _codes(result)


def test_feasible_collect_then_supply_passes():
    stops = [_stop("C1", "取車", 6, 30), _stop("S1", "補車", 8, 1)]
    result = evaluate_feasibility(stops, _vehicle(onboard=5), _operator(),
                                  now=NOW, check_resources=False)
    assert result["blocking_reasons"] == []
    assert [e["onboard_after"] for e in result["load_plan"]] == [11, 3]
    assert result["onboard_start"] == 5 and result["onboard_end"] == 3


# ── 3. 逐站到達時間與對應視野 ──

def test_each_stop_uses_its_own_horizon():
    """三站相隔約 5 公里，到達時間各不同 → 不得整趟共用同一視野。"""
    stops = [_stop("H1", "取車", 2, 30, lat=25.00, lng=121.40),
             _stop("H2", "取車", 2, 30, lat=25.10, lng=121.40),
             _stop("H3", "補車", 4, 1, lat=25.25, lng=121.40)]
    result = evaluate_feasibility(stops, _vehicle(onboard=2), _operator(),
                                  now=NOW, check_resources=False,
                                  start_lat=24.98, start_lng=121.40)
    offsets = [e["arrival_offset_min"] for e in result["load_plan"]]
    horizons = [e["horizon_used_min"] for e in result["load_plan"]]
    assert offsets == sorted(offsets) and offsets[0] < offsets[-1]
    assert len(set(horizons)) > 1, f"各站視野不應相同：{horizons}"


def test_stop_beyond_longest_horizon_is_blocked_not_extrapolated():
    stops = [_stop("F1", "取車", 2, 30, lat=25.00, lng=121.40),
             _stop("F2", "取車", 2, 30, lat=25.90, lng=121.40)]   # 約 100 公里外
    result = evaluate_feasibility(stops, _vehicle(onboard=2), _operator(),
                                  now=NOW, check_resources=False,
                                  start_lat=25.00, start_lng=121.40)
    assert "stop_beyond_forecast_horizon" in _codes(result)
    assert result["load_plan"][-1]["horizon_used_min"] is None


# ── 4. 班別、工時與任務重疊 ──

def test_cross_district_allowed_in_all_modes():
    """ADR-316：所有時段/模式皆允許跨區（同區優先由排序達成，非硬性禁止）。
    原「早晚班擋跨區」規則已移除，任何模式都不再回 cross_district_not_allowed。"""
    stops = [_stop("D1", "取車", 2, 30, district="板橋區"),
             _stop("D2", "補車", 2, 1, district="新莊區")]
    for mode in ("offpeak", "peak_shuttle", "night", "emergency"):
        result = evaluate_feasibility(stops, _vehicle(), _operator(), mode=mode,
                                      now=NOW, check_resources=False)
        assert "cross_district_not_allowed" not in _codes(result)


def test_labor_hours_block_dispatch():
    stops = [_stop("L1", "取車", 2, 30)]
    over = evaluate_feasibility(stops, _vehicle(), _operator(worked=250),
                                now=NOW, est_total_min=20)
    assert "labor_hours_exceeded" in _codes(over)
    near = evaluate_feasibility(stops, _vehicle(), _operator(worked=230),
                                now=NOW, est_total_min=30)   # 230+30 > 240
    assert "labor_hours_exceeded" in _codes(near)
    ok = evaluate_feasibility(stops, _vehicle(), _operator(worked=60),
                              now=NOW, est_total_min=30)
    assert "labor_hours_exceeded" not in _codes(ok)


def test_existing_task_time_overlap_is_blocked(client):
    vehicles_repo.seed_default_vehicles(1, 15)
    operators_repo.seed_dispatch_operators(4)
    put_drivers_on_duty()
    tasks_repo.insert({
        "task_id": "TRIP-EXISTING", "task_type": "normal", "task_status": "assigned",
        "assigned_operator": "OP-004", "assigned_vehicle": "CAR-001",
        "district": "板橋區", "route": [],
        "assigned_at": dt.datetime.now().isoformat(timespec="seconds"),
        "estimated_total_minutes": 120, "resources_released": 0,
    })
    result = evaluate_feasibility([_stop("O1", "取車", 2, 30)],
                                  _vehicle(), _operator(), est_total_min=30)
    assert "task_time_overlap" in _codes(result)


# ── 5. 預覽與確認共用同一份驗證（ADR-304 §1）──

@pytest.fixture
def pool(monkeypatch):
    from copy import deepcopy
    vehicles_repo.seed_default_vehicles(2, 15)
    operators_repo.seed_dispatch_operators(4)
    put_drivers_on_duty()
    recs = [_stop("P1", "補車", 9, 1), _stop("P2", "補車", 9, 1)]
    monkeypatch.setattr("api.dispatch._current_dispatch_list", lambda: deepcopy(recs))
    monkeypatch.setattr(task_execution, "_demand_resolved", lambda sid: False)
    return recs


def test_preview_reports_blocking_and_confirm_refuses_the_same(client, pool):
    """預覽看得到阻擋原因，確認被同一個原因擋下（不是預覽正常、按下才 409）。"""
    draft = dispatch_builder.build_emergency(["P1", "P2"], pool, vehicle_id="CAR-001",
                                             operator_id="OP-004", created_by="OP-002")
    assert draft["blocking_reasons"], "預覽就該回報阻擋原因"
    codes = {r["code"] for r in draft["blocking_reasons"]}
    # ADR-322：載量不足改判部分補車，不再產生 load_below_zero。
    # 這趟兩站都是補車：第一站把車上 7 台放完，第二站抵達時一台都沒有
    # → no_bikes_to_deliver（真的白跑，該擋）。總量超過車容量的硬限制也不變。
    assert codes == {"no_bikes_to_deliver", "total_quantity_exceeds_capacity"}
    assert draft["load_plan"][0]["onboard_before"] == 7     # conftest 慣例：半載
    result = client.post("/api/v1/dispatch/confirm-trip",
                         json={"draft_id": draft["draft_id"], "version": draft["version"]},
                         headers=OP_DISPATCHER)
    assert result.status_code == 409
    # 確認回的原因必須是預覽已經顯示過的其中一個（不得是預覽看不到的新理由）
    previewed = {r["message"] for r in draft["blocking_reasons"]}
    assert result.json()["message"] in previewed
    assert tasks_repo.list_tasks() == []


def test_preview_clean_then_confirm_succeeds_and_persists_plan(client, pool):
    vehicles_repo.report_onboard("CAR-001", 15, "manual_report")
    draft = dispatch_builder.build_emergency(["P1"], pool, vehicle_id="CAR-001",
                                             operator_id="OP-004", created_by="OP-002")
    assert draft["blocking_reasons"] == []
    result = client.post("/api/v1/dispatch/confirm-trip",
                         json={"draft_id": draft["draft_id"], "version": draft["version"]},
                         headers=OP_DISPATCHER)
    assert result.status_code == 200, result.text
    task = tasks_repo.get(result.json()["trip_id"])
    assert task["onboard_start"] == 15
    stop = task["route"][0]
    assert stop["horizon_used_min"] in (30, 60, 90, 120)
    assert stop["onboard_after"] == 6
    assert stop["arrival_offset_min"] is not None


def test_completion_settles_onboard_from_actual_reports(client, pool):
    vehicles_repo.report_onboard("CAR-001", 15, "manual_report")
    draft = dispatch_builder.build_emergency(["P1"], pool, vehicle_id="CAR-001",
                                             operator_id="OP-004", created_by="OP-002")
    tid = client.post("/api/v1/dispatch/confirm-trip",
                      json={"draft_id": draft["draft_id"], "version": draft["version"]},
                      headers=OP_DISPATCHER).json()["trip_id"]
    # 目標 10 台，實際只補到 8 → 少放 2 台，車上應剩 15-(9-2)=8
    client.post(f"/api/v1/dispatch/tasks/{tid}/report",
                json={"station_id": "P1", "actual_available": 8},
                headers={"X-Operator-Id": "OP-004"})
    vehicle = vehicles_repo.get_vehicle("CAR-001")
    assert vehicle["onboard_bikes"] == 8
    assert vehicle["onboard_source"] == "task_completion"


def test_onboard_endpoint_requires_role_and_validates(client, pool):
    assert client.post("/api/v1/vehicles/CAR-001/onboard",
                       json={"onboard_bikes": 5}).status_code == 401
    assert client.post("/api/v1/vehicles/CAR-001/onboard", json={"onboard_bikes": 5},
                       headers=OP_DISPATCHER).status_code == 200
    assert vehicles_repo.get_vehicle("CAR-001")["onboard_bikes"] == 5
    assert client.post("/api/v1/vehicles/CAR-001/onboard", json={"onboard_bikes": 99},
                       headers=OP_DISPATCHER).status_code == 422
    assert client.post("/api/v1/vehicles/NOPE/onboard", json={"onboard_bikes": 1},
                       headers=OP_DISPATCHER).status_code == 404


def test_driver_can_report_only_own_task_vehicle(client, pool):
    """ADR-123：司機可回報自己任務中的車；不是自己的任務就 403（身分要查主檔，不能只看登入角色）。"""
    operators_repo.seed_dispatch_operators(6)
    put_drivers_on_duty()
    vehicles_repo.report_onboard("CAR-001", 15, "manual_report")
    draft = dispatch_builder.build_emergency(["P1"], pool, vehicle_id="CAR-001",
                                             operator_id="OP-004", created_by="OP-002")
    assert client.post("/api/v1/dispatch/confirm-trip",
                       json={"draft_id": draft["draft_id"], "version": draft["version"]},
                       headers=OP_DISPATCHER).status_code == 200
    mine = client.post("/api/v1/vehicles/CAR-001/onboard",
                       json={"onboard_bikes": 14, "source": "manual_report"},
                       headers={"X-Operator-Id": "OP-004"})
    assert mine.status_code == 200, mine.text
    assert vehicles_repo.get_vehicle("CAR-001")["onboard_bikes"] == 14
    other = client.post("/api/v1/vehicles/CAR-001/onboard",
                        json={"onboard_bikes": 3, "source": "manual_report"},
                        headers={"X-Operator-Id": "OP-005"})
    assert other.status_code == 403, other.text


def test_add_station_rechecks_load_conservation(client, pool):
    vehicles_repo.report_onboard("CAR-001", 9, "manual_report")
    draft = dispatch_builder.build_emergency(["P1"], pool, vehicle_id="CAR-001",
                                             operator_id="OP-004", created_by="OP-002")
    tid = client.post("/api/v1/dispatch/confirm-trip",
                      json={"draft_id": draft["draft_id"], "version": draft["version"]},
                      headers=OP_DISPATCHER).json()["trip_id"]
    # 車上只剩 0 台，再加一個要補 9 台的站 → 必須被擋
    added = client.post(f"/api/v1/dispatch/tasks/{tid}/stations",
                        json={"station_id": "P2"}, headers=OP_DISPATCHER)
    assert added.status_code == 409
    assert len(tasks_repo.get(tid)["route"]) == 1
