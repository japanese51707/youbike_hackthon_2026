"""同源提供前端 SPA（ADR-314）。沒有 frontend_dist 時不掛載，本機純 API 不受影響。"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

RESERVED_PREFIXES = ("api", "docs", "redoc", "openapi.json", "health")


def frontend_dist_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "frontend_dist"


def mount_frontend(app: FastAPI, directory: Path | None = None) -> bool:
    """有 index.html 才掛靜態檔與 SPA fallback。回傳是否掛上。"""
    root = Path(directory) if directory else frontend_dist_dir()
    index = root / "index.html"
    if not index.is_file():
        return False

    assets = root / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="frontend-assets")

    @app.get("/")
    def frontend_index():
        return FileResponse(index)

    @app.get("/{full_path:path}")
    def frontend_spa(full_path: str):
        head = full_path.split("/", 1)[0]
        if head in RESERVED_PREFIXES:
            raise HTTPException(status_code=404, detail="Not found")
        candidate = (root / full_path).resolve()
        try:
            candidate.relative_to(root.resolve())
        except ValueError:
            return FileResponse(index)
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(index)

    return True
