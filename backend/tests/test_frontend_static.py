"""ADR-314：有 frontend_dist 才出 SPA；API 路徑不被靜態檔吃掉。"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.frontend_static import mount_frontend


def _app_with_dist(tmp_path: Path) -> FastAPI:
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "app.js").write_text("console.log(1)", encoding="utf-8")
    (tmp_path / "index.html").write_text("<html>spa</html>", encoding="utf-8")
    (tmp_path / "favicon.ico").write_text("ico", encoding="utf-8")
    app = FastAPI()

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/api/v1/kpi")
    def kpi():
        return {"ok": True}

    assert mount_frontend(app, tmp_path) is True
    return app


def test_mount_skipped_without_index(tmp_path):
    app = FastAPI()
    assert mount_frontend(app, tmp_path) is False


def test_spa_index_and_deep_link(tmp_path):
    client = TestClient(_app_with_dist(tmp_path))
    home = client.get("/")
    assert home.status_code == 200
    assert "spa" in home.text
    deep = client.get("/dashboard")
    assert deep.status_code == 200
    assert "spa" in deep.text


def test_api_and_health_still_json(tmp_path):
    client = TestClient(_app_with_dist(tmp_path))
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/api/v1/kpi").json() == {"ok": True}


def test_packaged_asset_and_root_file(tmp_path):
    client = TestClient(_app_with_dist(tmp_path))
    js = client.get("/assets/app.js")
    assert js.status_code == 200
    assert "console.log" in js.text
    assert client.get("/favicon.ico").status_code == 200
