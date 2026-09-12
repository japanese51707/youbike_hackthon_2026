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

from core.aws_local import load_local_aws_credentials

load_local_aws_credentials()

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from core.data.observations import DataUnavailable
from core.frontend_static import mount_frontend
from config_loader import get_config
from middleware import RateLimitMiddleware
from api import (
    stations, dispatch, operators, alerts,
    optimization, overrides, kpi, events, audit, weather, accounts,
    assistant, rider,
)

cfg = get_config()
_sec = cfg.get("security", {})


@asynccontextmanager
async def lifespan(app: FastAPI):
    """啟動時初始化 SQLite schema 並種入預設帳號與車隊（A5 / ADR-114）。"""
    from db import init_db
    from db.operators_repo import (
        seed_default_operators, seed_dispatch_operators,
        seed_depot_standby_operators, seed_stationed_operators,
        seed_workforce_allocation,
    )
    from db.vehicles_repo import seed_default_vehicles, set_reserve_fleet
    init_db()
    seed_default_operators()
    # ADR-114/116 調度人力 seed（開發/Demo 起始值，之後由人力 API 覆蓋）。全部預設 off_duty；
    # 司機不常態待命，被派到任務的當下才轉上工（見 dispatch 確認落地）。
    seed_dispatch_operators(total=350)      # OP-001~350，role_type=driver
    seed_depot_standby_operators(total=10)  # DEP-001~010，總站待命人力（可跨區支援）
    seed_stationed_operators(total=30)      # ST-001~030，駐點人員
    # ADR-308：依歷史數據分析（analysis_workforce_allocation.py 產出）把調度員/駐點員
    # 預設分派到各行政區（周轉量主導的工作量配額）。找不到分析檔則不預設分派。
    _alloc = seed_workforce_allocation()
    if _alloc.get("applied"):
        print(f"[seed] 人力預設分派：調度員 {_alloc['drivers_assigned']} 名、"
              f"駐點員 {_alloc['stationed_assigned']} 名依歷史工作量分配至各行政區")
    # ADR-114 車隊主檔 seed（組單三入口與緊急救火需要車輛清單，缺 seed 會回空陣列）。
    seed_default_vehicles(n=45)
    # ADR-118 靜態保留率：把車隊末端一定比例標為 standby（緊急救火用）。
    set_reserve_fleet(cfg.get("reserve", {}).get("保留率", 0.12))
    # ADR-306：背景預熱「同時段歷史代理」查表（讀 S3 1–6 月建一次，供即時預測補 lag）。
    # 用 daemon thread 不阻塞啟動；非即時源（mock）不預熱。
    if cfg.get("data_source", {}).get("mode") not in (None, "mock"):
        import threading

        def _warm_slot_table():
            try:
                from core.data.historical import HistoricalDataSource
                HistoricalDataSource().slot_median("__warmup__", 0, 0)
            except Exception:
                pass  # 預熱失敗不影響啟動；真正請求時會再建一次

        def _warm_stations():
            try:
                from core.data.degradation import get_stations_with_degradation
                get_stations_with_degradation()
            except Exception:
                pass  # 預熱失敗不影響啟動；第一個 /stations 會再打一次官方源

        threading.Thread(target=_warm_slot_table, daemon=True).start()
        threading.Thread(target=_warm_stations, daemon=True).start()

    # ADR-310：自動偵測調度完成。背景輪詢即時站況，進行中任務的待處理站達派工目標即
    # 自動標記完成、推進任務（免人工回報）。僅真實源 + config 開關開啟時啟動。
    from core import auto_detect
    if auto_detect.start_background(cfg.get("data_source", {}).get("mode")):
        print("[auto_detect] 自動偵測調度完成：背景輪詢已啟動")

    # ADR-313：需調度清單背景預算快取。顯示端點讀快取秒回，避免每次重跑全站預測。
    from core import dispatch_cache
    if dispatch_cache.start_background(cfg.get("data_source", {}).get("mode")):
        print("[dispatch_cache] 需調度清單背景預算已啟動")
    yield
    # 關機時停背景 thread（daemon 本會隨程序結束，這裡明確停止避免測試殘留）
    from core import auto_detect as _ad
    _ad.stop_background()
    from core import dispatch_cache as _dc
    _dc.stop_background()


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
               optimization, overrides, kpi, events, audit, weather, accounts,
               assistant, rider):
    app.include_router(module.router)


@app.get("/health")
def health():
    return {"status": "ok", "version": "0.1.0-A0"}


# ADR-314：有打包進 image 的 SPA 才掛。須在 API／health 之後，才能當深連結 fallback。
mount_frontend(app)
