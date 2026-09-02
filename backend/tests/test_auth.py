"""權限閘門測試（A4）：固定「無身分401、越權403、正確角色200」的行為。"""

from tests.conftest import OP_OPERATOR, OP_DISPATCHER, OP_MAINTAINER


def test_confirm_requires_identity(client):
    """派發確認：無身分 → 401。"""
    r = client.post("/api/v1/dispatch/confirm", json={"recommendation_ids": ["X"]})
    assert r.status_code == 401


def test_confirm_rejects_operator_role(client):
    """派發確認：operator 角色越權 → 403。"""
    r = client.post("/api/v1/dispatch/confirm",
                    json={"recommendation_ids": ["X"]}, headers=OP_OPERATOR)
    assert r.status_code == 403


def test_confirm_allows_dispatcher(client):
    """派發確認：dispatcher 角色 → 200。"""
    r = client.post("/api/v1/dispatch/confirm",
                    json={"recommendation_ids": ["X"]}, headers=OP_DISPATCHER)
    assert r.status_code == 200


def test_fake_operator_id_rejected(client):
    """偽造 X-Operator-Id → 401。"""
    r = client.post("/api/v1/dispatch/confirm",
                    json={"recommendation_ids": ["X"]},
                    headers={"X-Operator-Id": "OP-FAKE"})
    assert r.status_code == 401


def test_optimization_approve_only_maintainer(client):
    """②最適化 approve：只有 maintainer 能過，dispatcher 越權 403。"""
    r_disp = client.post("/api/v1/optimization/daily-review/approve", headers=OP_DISPATCHER)
    assert r_disp.status_code == 403
    r_maint = client.post("/api/v1/optimization/daily-review/approve", headers=OP_MAINTAINER)
    assert r_maint.status_code == 200


def test_readonly_endpoints_no_auth(client):
    """唯讀端點不需身分。"""
    for path in ["/api/v1/stations", "/api/v1/alerts", "/health"]:
        assert client.get(path).status_code == 200
