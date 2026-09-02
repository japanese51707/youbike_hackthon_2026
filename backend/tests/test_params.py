"""三層參數 + 版本管理測試（A5）：base/optimized 版本、回溯、override_active、I-10 端點。"""

from tests.conftest import OP_DISPATCHER, OP_MAINTAINER


def test_base_then_optimized_version():
    """①base → ②optimized：生效版本是最新的 optimized，param_source 正確。"""
    from params import set_base, commit_optimized, get_current
    set_base("S1", {"target_level": 0.5, "outflow_rate": 1.0})
    cur = get_current("S1")
    assert cur["param_source"] == "base"
    assert cur["params"]["target_level"] == 0.5

    commit_optimized("S1", {"target_level": 0.6, "outflow_rate": 1.2},
                     reason="近3日早高峰偏高", operator="OP-003")
    cur = get_current("S1")
    assert cur["param_source"] == "ai_optimized"
    assert cur["params"]["target_level"] == 0.6


def test_param_source_never_emergency_override():
    """param_source 只會是 base/ai_optimized，不會是 emergency_override（review #2）。"""
    from params import set_base, get_current
    set_base("S2", {"target_level": 0.5})
    assert get_current("S2")["param_source"] in ("base", "ai_optimized")


def test_optimized_requires_reason():
    """②最適化版本必須備註原因。"""
    from params import set_base, commit_optimized
    set_base("S3", {"target_level": 0.5})
    try:
        commit_optimized("S3", {"target_level": 0.6}, reason="", operator="OP-003")
        assert False, "空原因應被擋"
    except ValueError:
        pass


def test_rollback_to_previous_version():
    """回溯：optimized 後回溯到 base 版本，生效版本變回 base。"""
    from params import set_base, commit_optimized, get_history, rollback, get_current
    base = set_base("S4", {"target_level": 0.5})
    commit_optimized("S4", {"target_level": 0.9}, reason="測試", operator="OP-003")
    assert get_current("S4")["params"]["target_level"] == 0.9

    # 回溯到 base 版本
    result = rollback("S4", base["version"], "OP-003")
    assert result is not None
    assert get_current("S4")["params"]["target_level"] == 0.5
    # 歷史保留所有版本
    assert len(get_history("S4")) == 2


def test_target_usage_rate_in_current():
    """生效參數附換算好的 target_usage_rate（I-3）。"""
    from params import set_base, get_current
    set_base("S5", {"target_level": 0.5})
    assert get_current("S5")["target_usage_rate"] == 50.0


# ── I-10 端點 ──

def test_params_history_endpoint(client):
    """GET /params/history 回版本歷史。"""
    from params import set_base, commit_optimized
    set_base("500999001", {"target_level": 0.5})
    commit_optimized("500999001", {"target_level": 0.6}, reason="x", operator="OP-003")
    r = client.get("/api/v1/stations/500999001/params/history")
    assert r.status_code == 200
    assert len(r.json()) == 2


def test_params_rollback_endpoint_requires_maintainer(client):
    """POST /params/rollback 需 maintainer；dispatcher 403。"""
    from params import set_base
    base = set_base("500999002", {"target_level": 0.5})
    body = {"version": base["version"]}
    assert client.post("/api/v1/stations/500999002/params/rollback",
                       json=body, headers=OP_DISPATCHER).status_code == 403
    assert client.post("/api/v1/stations/500999002/params/rollback",
                       json=body, headers=OP_MAINTAINER).status_code == 200


def test_rollback_nonexistent_version_404(client):
    """回溯不存在的版本 → 404。"""
    from params import set_base
    set_base("500999003", {"target_level": 0.5})
    r = client.post("/api/v1/stations/500999003/params/rollback",
                    json={"version": "NOT_EXIST"}, headers=OP_MAINTAINER)
    assert r.status_code == 404
