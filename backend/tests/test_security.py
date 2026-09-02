"""資安測試（A4）：出向 SSRF 防護、rate limit 429、/health 豁免。"""

import importlib

import pytest

from core.alert_service import _is_safe_callback_url
from config_loader import get_config


@pytest.mark.parametrize("url", [
    "http://gov.tw/hook",              # 非 https
    "https://localhost/hook",          # 本機
    "https://127.0.0.1/hook",          # loopback
    "https://169.254.169.254/latest",  # AWS metadata（經典 SSRF 目標）
    "https://10.0.0.1/hook",           # 內網
    "https://192.168.1.1/hook",        # 內網
    "https://172.16.0.1/hook",         # 內網
    "file:///etc/passwd",              # 非 http scheme
])
def test_ssrf_blocks_dangerous_callbacks(url):
    """webhook callback SSRF 防護：擋內網/metadata/非https。"""
    safe, _ = _is_safe_callback_url(url)
    assert safe is False


@pytest.mark.parametrize("url", [
    "https://gov.example.com/hook",
    "https://api.ntpc.gov.tw/webhook",
])
def test_ssrf_allows_legit_https(url):
    """合法的 gov https 應放行。"""
    safe, _ = _is_safe_callback_url(url)
    assert safe is True


def test_subscribe_endpoint_rejects_unsafe_callback(client):
    """訂閱端點：不安全 callback → 400。"""
    r = client.post("/api/v1/alerts/subscribe",
                    json={"callback_url": "https://169.254.169.254/x", "levels": ["critical"]})
    assert r.status_code == 400


def _build_app_with_rate_limit(limit):
    """建一個 rate limit 指定上限的獨立 app（避免污染其他測試的計數）。"""
    get_config()["security"]["rate_limit_per_min"] = limit
    import main
    importlib.reload(main)
    from fastapi.testclient import TestClient
    return TestClient(main.app), main


def test_rate_limit_blocks_over_limit():
    """超過每分鐘上限 → 429；/health 豁免不限流。"""
    client, main = _build_app_with_rate_limit(5)
    try:
        codes = [client.get("/api/v1/stations").status_code for _ in range(7)]
        assert codes[:5] == [200] * 5     # 前 5 次放行
        assert 429 in codes[5:]           # 之後被擋
        # /health 豁免：多次仍 200
        assert all(client.get("/health").status_code == 200 for _ in range(10))
    finally:
        # 還原設定並重載 main，避免影響後續測試
        get_config()["security"]["rate_limit_per_min"] = 120
        importlib.reload(main)
