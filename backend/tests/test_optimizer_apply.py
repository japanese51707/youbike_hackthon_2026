"""第三批 C（ADR-304）：optimizer 狀態語意、review_id 綁定、全成或全退、回滾驗證。

不依賴 S3／歷史資料：以 monkeypatch 注入 compute_daily_review 的輸出，
專門驗證「套用契約」本身。狀態分類的真實計算另由 test_optimizer_status 覆蓋。
"""

import pytest

from tests.conftest import OP_DISPATCHER, OP_MAINTAINER


def _review(review_id="REV-TEST-1", status="ok", stations=("S-A", "S-B")):
    return {
        "review_id": review_id,
        "review_date": "2026-09-11",
        "lookback_days": 3,
        "summary": {"total_stations_adjusted": len(stations), "avg_change_pct": 5.0,
                    "significant_count": 0},
        "station_changes": [
            {"station_id": sid, "station_name": f"站{sid}", "is_significant": False,
             "params": [{"param": "base_outflow_coef", "old": 1.0, "new": 1.05,
                         "change_pct": 5.0, "scenario": "平日基礎", "samples": 20,
                         "reason": f"{sid} 近三日流出偏高"}]}
            for sid in stations
        ],
        "status": status,
        "reason": "test",
        "diagnostics": {},
        "effective_note": "做法Y",
    }


@pytest.fixture
def stub_review(monkeypatch):
    """把 compute_daily_review 換成固定輸出；回傳可改寫的 holder。"""
    holder = {"value": _review()}
    import optimization.param_optimizer as po
    monkeypatch.setattr(po, "compute_daily_review",
                        lambda *a, **k: dict(holder["value"]))
    return holder


def _fetch(client, stub_review):
    r = client.get("/api/v1/optimization/daily-review")
    assert r.status_code == 200
    return r.json()


# ── review_id 綁定與冪等 ──

def test_approve_requires_review_id(client, stub_review):
    _fetch(client, stub_review)
    r = client.post("/api/v1/optimization/daily-review/approve", headers=OP_MAINTAINER)
    assert r.status_code == 422


def test_approve_unknown_review_id_409(client, stub_review):
    _fetch(client, stub_review)
    r = client.post("/api/v1/optimization/daily-review/approve",
                    json={"review_id": "REV-NOT-EXIST"}, headers=OP_MAINTAINER)
    assert r.status_code == 409


def test_approve_is_idempotent(client, stub_review):
    review = _fetch(client, stub_review)
    body = {"review_id": review["review_id"]}
    first = client.post("/api/v1/optimization/daily-review/approve",
                        json=body, headers=OP_MAINTAINER)
    assert first.status_code == 200
    second = client.post("/api/v1/optimization/daily-review/approve",
                         json=body, headers=OP_MAINTAINER)
    assert second.status_code == 200
    assert second.json() == first.json()
    # 重送不得重複寫版本
    from params import get_history
    assert len(get_history("S-A")) == 1


def test_approve_still_requires_maintainer(client, stub_review):
    review = _fetch(client, stub_review)
    r = client.post("/api/v1/optimization/daily-review/approve",
                    json={"review_id": review["review_id"]}, headers=OP_DISPATCHER)
    assert r.status_code == 403


# ── 狀態語意 ──

@pytest.mark.parametrize("status", ["no_data", "insufficient_samples", "failed"])
def test_non_ok_status_cannot_be_applied(client, stub_review, status):
    stub_review["value"] = _review(status=status)
    review = _fetch(client, stub_review)
    assert review["status"] == status
    r = client.post("/api/v1/optimization/daily-review/approve",
                    json={"review_id": review["review_id"]}, headers=OP_MAINTAINER)
    assert r.status_code == 409


def test_failed_is_not_reported_as_no_data(monkeypatch):
    """計算失敗必須回 failed，不得偽裝成 no_data（ADR-304）。"""
    import optimization.param_optimizer as po
    monkeypatch.setattr(po, "_analyze_stations",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    out = po.compute_daily_review("2026-09-11", 3)
    assert out["status"] == "failed"
    assert "RuntimeError" in out["reason"]


def test_empty_source_is_no_data(monkeypatch):
    import optimization.param_optimizer as po
    monkeypatch.setattr(po, "_analyze_stations",
                        lambda *a, **k: ([], {"rows": 0, "stations_considered": 0}))
    out = po.compute_daily_review("2026-09-11", 3)
    assert out["status"] == "no_data"


def test_all_stations_below_threshold_is_insufficient(monkeypatch):
    import optimization.param_optimizer as po
    monkeypatch.setattr(po, "_analyze_stations", lambda *a, **k: (
        [], {"rows": 500, "stations_considered": 3, "skipped_insufficient": 3}))
    out = po.compute_daily_review("2026-09-11", 3)
    assert out["status"] == "insufficient_samples"


def test_review_id_is_unpredictable(monkeypatch):
    import optimization.param_optimizer as po
    monkeypatch.setattr(po, "_analyze_stations",
                        lambda *a, **k: ([], {"rows": 0, "stations_considered": 0}))
    a = po.compute_daily_review("2026-09-11", 3)["review_id"]
    b = po.compute_daily_review("2026-09-11", 3)["review_id"]
    assert a != b and len(a) > 20


# ── 全成或全退 ──

def test_partial_failure_rolls_back_everything(client, stub_review):
    """單站失敗 → 整批回滾，不留部分套用（ADR-304）。"""
    bad = _review(stations=("S-OK", "S-BAD"))
    bad["station_changes"][1]["params"][0]["reason"] = ""   # commit_optimized 要求原因非空
    stub_review["value"] = bad
    review = _fetch(client, stub_review)
    r = client.post("/api/v1/optimization/daily-review/approve",
                    json={"review_id": review["review_id"]}, headers=OP_MAINTAINER)
    assert r.status_code == 422
    from params import get_history
    assert get_history("S-OK") == []     # 前面的站也沒有留下版本
    assert get_history("S-BAD") == []


def test_keep_decision_excluded_from_apply(client, stub_review):
    review = _fetch(client, stub_review)
    rid = review["review_id"]
    assert client.post("/api/v1/optimization/daily-review/station/S-B",
                       json={"decision": "keep", "review_id": rid},
                       headers=OP_MAINTAINER).status_code == 200
    r = client.post("/api/v1/optimization/daily-review/approve",
                    json={"review_id": rid}, headers=OP_MAINTAINER)
    assert r.json()["committed_stations"] == ["S-A"]
    from params import get_history
    assert get_history("S-B") == []


# ── 回滾驗證 ──

def test_rollback_verifies_effective_version():
    """回溯後重讀實際生效參數，等於目標版本才算成功。"""
    from params import set_base, commit_optimized, rollback, get_current
    base = set_base("S-RB", {"target_level": 0.5})
    commit_optimized("S-RB", {"target_level": 0.9}, reason="測試", operator="OP-003")
    assert get_current("S-RB")["params"]["target_level"] == 0.9
    result = rollback("S-RB", base["version"], "OP-003")
    assert result["version"] == base["version"]
    assert get_current("S-RB")["version"] == base["version"]


def test_rollback_conflict_when_not_effective(monkeypatch):
    """activate 後實際生效版本不符 → 視為失敗（不靜默回成功）。"""
    from core.dispatch_errors import DispatchConflict
    from db import params_repo
    from params import set_base, rollback
    base = set_base("S-RB2", {"target_level": 0.5})
    monkeypatch.setattr(params_repo, "get_active",
                        lambda sid: {"version": "OTHER", "params": {}})
    with pytest.raises(DispatchConflict):
        rollback("S-RB2", base["version"], "OP-003")


# ── 誠實標記：係數仍未生效（ADR-120 做法 Y / ADR-304 第 7 條）──

def test_approved_coefficients_do_not_change_rule_engine(client, stub_review):
    """approve 後規則引擎輸出不變——把「係數尚未被消費」固定成可回歸的事實。"""
    from core.rule_engine import evaluate_station
    station = {"station_id": "S-A", "station_name": "站S-A", "district": "板橋區",
               "available_bikes": 1, "available_docks": 19, "total_docks": 20,
               "usage_rate": 5.0, "status": "low", "service_available": True,
               "lat": 25.0, "lng": 121.5}
    before = evaluate_station(dict(station), prediction=None)
    review = _fetch(client, stub_review)
    assert client.post("/api/v1/optimization/daily-review/approve",
                       json={"review_id": review["review_id"]},
                       headers=OP_MAINTAINER).status_code == 200
    from params import get_current
    assert get_current("S-A")["params"]["base_outflow_coef"] == 1.05   # 版本確實存了
    after = evaluate_station(dict(station), prediction=None)
    assert before == after                                             # 但調度判斷不受影響
