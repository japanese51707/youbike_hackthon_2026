"""
YouBike 智慧調度系統 — FastAPI 入口
====================================
只負責：啟動、掛路由、CORS/中介層、統一錯誤格式。無業務邏輯（在 core/）。
A0 階段所有端點回 mock，之後 A1~A5 逐步接真實邏輯。

啟動：
    cd backend && uvicorn main:app --reload
文件：http://127.0.0.1:8000/docs
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from core.data.observations import DataUnavailable
from config_loader import get_config
from middleware import RateLimitMiddleware
from api import (
    stations, dispatch, operators, alerts,
    optimization, overrides, kpi, events, audit, weather, accounts,
)

cfg = get_config()
_sec = cfg.get("security", {})


@asynccontextmanager
async def lifespan(app: FastAPI):
    """啟動時初始化 SQLite schema 並種入預設帳號（A5）。"""
    from db import init_db
    from db.operators_repo import seed_default_operators
    init_db()
    seed_default_operators()
    yield


app = FastAPI(
    title="YouBike 智慧調度系統 API",
    version="0.1.0-A0",
    description="A0 骨架：所有端點回 mock 資料。核心約束：AI 只估計、規則引擎決策。",
    lifespan=lifespan,
)

# Rate limit（入向 DoS 防護，NFR-8）。先掛（外層），CORS 後掛（內層先跑）。
app.add_middleware(
    RateLimitMiddleware,
    limit_per_min=_sec.get("rate_limit_per_min", 120),
    exempt_paths=_sec.get("rate_limit_exempt_paths", ["/health"]),
)

# CORS 白名單（NFR-8：只允許我們的前端網域 + 收斂方法/標頭，不用 *）
app.add_middleware(
    CORSMiddleware,
    allow_origins=_sec.get("allowed_origins", ["http://localhost:5173"]),
    allow_credentials=True,
    allow_methods=_sec.get("allowed_methods", ["GET", "POST", "PUT", "DELETE", "OPTIONS"]),
    allow_headers=_sec.get("allowed_headers", ["Content-Type", "X-Operator-Id"]),
)


# ── 統一錯誤格式（NFR-8：不外洩內部路徑/框架版本/堆疊）──

@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """4xx（含權限 401/403、找不到 404）：保留可讀 detail，但用統一結構。"""
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": "request_error", "message": exc.detail},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """輸入驗證失敗（422）：回欄位層級錯誤，但不含內部型別/堆疊。"""
    errors = [{"field": ".".join(str(x) for x in e["loc"][1:]), "msg": e["msg"]}
              for e in exc.errors()]
    return JSONResponse(
        status_code=422,
        content={"error": "validation_error", "message": "輸入資料驗證失敗", "details": errors},
    )


@app.exception_handler(DataUnavailable)
async def data_unavailable_handler(request: Request, exc: DataUnavailable):
    return JSONResponse(status_code=503, content={"error": "data_unavailable", "message": str(exc)})


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """未預期例外（500）：一律通用訊息，絕不外洩內部細節。"""
    return JSONResponse(
        status_code=500,
        content={"error": "internal_error", "message": "系統發生錯誤，請稍後再試"},
    )


# 掛載所有路由
for module in (stations, dispatch, operators, alerts,
               optimization, overrides, kpi, events, audit, weather, accounts):
    app.include_router(module.router)


@app.get("/health")
def health():
    return {"status": "ok", "version": "0.1.0-A0"}
