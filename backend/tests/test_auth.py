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


def test_confirm_dispatcher_still_requires_valid_draft(client):
    """有角色仍須有效草稿，不能用 recommendation_ids 得到 mock 成功。"""
    r = client.post("/api/v1/dispatch/confirm",
                    json={"recommendation_ids": ["X"]}, headers=OP_DISPATCHER)
    assert r.status_code == 422


def test_fake_operator_id_rejected(client):
    """偽造 X-Operator-Id → 401。"""
    r = client.post("/api/v1/dispatch/confirm",
                    json={"recommendation_ids": ["X"]},
                    headers={"X-Operator-Id": "OP-FAKE"})
    assert r.status_code == 401


def test_optimization_approve_only_maintainer(client):
    """②最適化 approve：只有 maintainer 能過，dispatcher 越權 403。

    ADR-304：approve 改為必帶 review_id，故 maintainer 不帶 body 是 422（通過授權、輸入不合法），
    與 dispatcher 的 403（授權就被擋）語意不同。
    """
    r_disp = client.post("/api/v1/optimization/daily-review/approve", headers=OP_DISPATCHER)
    assert r_disp.status_code == 403
    r_maint = client.post("/api/v1/optimization/daily-review/approve", headers=OP_MAINTAINER)
    assert r_maint.status_code == 422


def test_readonly_endpoints_no_auth(client):
    """唯讀端點不需身分。"""
    for path in ["/api/v1/stations", "/api/v1/alerts", "/health"]:
        assert client.get(path).status_code == 200


# ── A5 帳號系統 ──

def test_login_success(client):
    """正確帳密登入 → 200，回帳號不含密碼雜湊。"""
    r = client.post("/api/v1/auth/login",
                    json={"operator_id": "OP-002", "password": "youbike-dp"})
    assert r.status_code == 200
    assert "password_hash" not in r.json()["operator"]


def test_login_wrong_password(client):
    """密碼錯 → 401。"""
    r = client.post("/api/v1/auth/login",
                    json={"operator_id": "OP-002", "password": "wrong"})
    assert r.status_code == 401


def test_create_account_requires_maintainer(client):
    """建帳號：dispatcher 越權 403、maintainer 成功 200。"""
    body = {"operator_id": "OP-NEW", "name": "新人", "role": "operator", "password": "pw12345"}
    assert client.post("/api/v1/accounts", json=body, headers=OP_DISPATCHER).status_code == 403
    assert client.post("/api/v1/accounts", json=body, headers=OP_MAINTAINER).status_code == 200


def test_deactivate_account_blocks_login(client):
    """停用帳號後，該帳號無法登入、也無法通過 auth。"""
    body = {"operator_id": "OP-TMP", "name": "臨時", "role": "operator", "password": "pw12345"}
    client.post("/api/v1/accounts", json=body, headers=OP_MAINTAINER)
    # 停用前能登入
    assert client.post("/api/v1/auth/login",
                       json={"operator_id": "OP-TMP", "password": "pw12345"}).status_code == 200
    # 停用
    assert client.delete("/api/v1/accounts/OP-TMP", headers=OP_MAINTAINER).status_code == 200
    # 停用後登入失敗
    assert client.post("/api/v1/auth/login",
                       json={"operator_id": "OP-TMP", "password": "pw12345"}).status_code == 401
