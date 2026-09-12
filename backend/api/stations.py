"""
站點端點（3.1, 3.2, 3.9, 3.10, 3.19）
薄層：A0 回 mock。注意路由順序 — 靜態路徑(heatmap/timeline)先於動態路徑(/{id})。
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from datetime import timedelta
from core.data.observations import parse_time
from core.data.degradation import degradation_status
from mock_store import get_mock
from core.data import get_data_source, get_stations_with_degradation
from auth import require_role
from models_schema.params_ops import ParamsRollbackRequest
from models_schema.station import StationStatus, StationDetail

router = APIRouter(prefix="/api/v1", tags=["stations"])


@router.get("/stations", response_model=list[StationStatus])
def list_stations(district: str | None = None, status: str | None = None):
    """3.1 所有站點即時狀態（前端畫地圖）

    走 data_source 層 + 降級保護：即時源掛掉會自動退回歷史，並標 data_freshness。
    換源只改 config.data_source.mode（mock / historical / tdx / youbike_official）。
    """
    return get_stations_with_degradation(district=district, status=status)


@router.get("/data/status")
def data_status():
    return degradation_status()


# 靜態路徑要先於 /stations/{station_id} 註冊，否則會被當成 station_id
@router.get("/stations/heatmap")
def heatmap(dimension: str = "district"):
    """3.9 多維度熱點聚合（接真實站點）。dimension: district / status。

    按維度聚合站數 + 空/滿站數 + 平均借用率，供熱力圖。
    """
    stations = get_stations_with_degradation()
    buckets: dict[str, dict] = {}
    for s in stations:
        key = s.get(dimension) or "未知"
        b = buckets.setdefault(key, {"key": key, "count": 0, "empty": 0, "full": 0,
                                     "_usage_sum": 0.0})
        b["count"] += 1
        if s.get("status") == "empty":
            b["empty"] += 1
        if s.get("status") == "full":
            b["full"] += 1
        b["_usage_sum"] += float(s.get("usage_rate", 0) or 0)
    out = []
    for b in buckets.values():
        b["avg_usage_rate"] = round(b.pop("_usage_sum") / b["count"], 1) if b["count"] else 0
        out.append(b)
    out.sort(key=lambda x: -x["count"])
    return {"dimension": dimension, "buckets": out}


@router.get("/stations/timeline")
def timeline(district: str = "中和區", date: str = "2026-06-02", interval: int = 30):
    """3.10 時間軸序列。Mock 回預存示範；正式模式讀歷史 Parquet，缺資料回 503。"""
    from config_loader import get_config
    mode = get_config().get("data_source", {}).get("mode", "mock")
    if mode == "mock":
        return get_mock()["timeline"]
    try:
        from core.data.historical import HistoricalDataSource
        return HistoricalDataSource().get_timeline(
            district=district, date=date, interval=interval,
        )
    except Exception:
        raise HTTPException(status_code=503, detail="歷史時間軸資料尚未提供")


def _current_station(station_id):
    current = next((s for s in get_stations_with_degradation() if s["station_id"] == station_id), None)
    if current is None:
        raise HTTPException(status_code=404, detail=f"找不到站點 {station_id}")
    return current


def _history(station_id, start, end):
    from core.data.historical import HistoricalDataSource
    from config_loader import get_config
    mode = get_config().get("data_source", {}).get("mode", "mock")
    if mode == "mock":
        return {"history": get_data_source().get_history(station_id, start, end),
                "history_status": {"status": "ready", "source": "mock"}}
    try:
        rows = HistoricalDataSource().get_history(station_id, start, end)
        return {"history": rows, "history_status": {"status": "ready" if rows else "empty",
                "source": "historical", "requested_start": start, "requested_end": end}}
    except Exception:  # source errors must not make current station details unavailable
        return {"history": [], "history_status": {"status": "unavailable", "source": "historical",
                "reason": "此日期範圍的歷史資料尚未提供", "requested_start": start, "requested_end": end}}


@router.get("/stations/{station_id}/history")
def station_history(station_id: str, start: str, end: str):
    try:
        lo, hi = parse_time(start), parse_time(end)
        if hi < lo or hi - lo > timedelta(days=31):
            raise ValueError()
    except (ValueError, TypeError):
        raise HTTPException(status_code=422, detail="需有效時間與最多 31 天的歷史查詢範圍")
    return _history(station_id, lo.isoformat(), hi.isoformat())


@router.get("/stations/{station_id}", response_model=StationDetail)
def station_detail(station_id: str, history_range: str = Query("7d", pattern="^(24h|1d|7d)$")):
    current = _current_station(station_id)
    anchor = current.get("observed_at")
    if anchor:
        end = parse_time(anchor)
        history = _history(station_id, (end - timedelta(days=1 if history_range == "24h" else int(history_range[:-1]))).isoformat(), end.isoformat())
    else:
        history = {"history": [], "history_status": {"status": "unavailable", "reason": "無有效觀測時間"}}
    return {"current": current, **history, "prediction": _build_prediction(current),
            "params": _with_target_usage_rate(_get_params(station_id))}


def _build_prediction(station):
    from core.interfaces import get_predictor
    from config_loader import get_config
    mode = get_config().get("data_source", {}).get("mode", "mock")
    base = {"station_id": station["station_id"], "predict_from": station.get("observed_at") or station.get("timestamp"),
            "horizon_source": "default", "horizons": []}
    try:
        pred = get_predictor()
        if mode != "mock" and pred.__class__.__name__ == "MockPredictor":
            return {**base, "source": "unavailable", "status": "unavailable", "reason": "真實模型尚未就緒"}
        multi = pred.predict_multi(station) if hasattr(pred, "predict_multi") else None
        intervals = multi.intervals if multi else [pred.predict(station, m) for m in (30, 60, 90, 120)]
        anchor = parse_time(base["predict_from"])
        return {**base, "source": intervals[0].source, "status": getattr(multi, "status", "ready"),
                "model_version": getattr(multi, "model_version", None),
                "missing_features": getattr(multi, "missing_features", []),
                "lag_source": getattr(multi, "lag_source", None),
                "horizons": [{**vars(iv), "predict_target_time": (anchor + timedelta(minutes=iv.horizon_minutes)).isoformat()}
                             for iv in intervals]}
    except (NotImplementedError, ValueError, OSError, KeyError, TypeError):
        return {**base, "source": "unavailable", "status": "unavailable", "reason": "預測所需模型、特徵或有效觀測尚未就緒"}


def _get_params(station_id):
    from params import get_current
    return get_current(station_id)


def _require_mock(feature):
    from config_loader import get_config
    if get_config().get("data_source", {}).get("mode", "mock") != "mock":
        raise HTTPException(status_code=501, detail=f"{feature} 尚未提供真實服務")


def _with_target_usage_rate(params: dict | None) -> dict | None:
    """在 params 回傳補上換算好的 target_usage_rate（0~100%），供前端直接與 usage_rate 比對。

    target_level 維持 0~1 比例（B 的模型參數語意，見 api_contract §2.11），
    這裡額外附上 target_level×100 的百分比版，讓 C 不必自己換算、避免直接比 0.5 vs 18.75 的誤判。
    """
    if not params:
        return params
    inner = params.get("params", {})
    target_level = inner.get("target_level")
    result = dict(params)
    if target_level is not None:
        # 放在外層，明確標為「顯示用同尺度值」，不動內層 target_level
        result["target_usage_rate"] = round(float(target_level) * 100, 1)
    return result


@router.get("/stations/{station_id}/static")
def station_static(station_id: str):
    """站點靜態/半靜態資料打包（ADR-104/113 靜態層）：位置 + 地形 + POI + 行為指紋。

    這些不常變（地形永不變、POI/位置幾乎不變、指紋每天離線算一次），前端「開場拉一次」快取即可，
    不用即時輪詢。地形/指紋回預算好的快取；POI 現算（快）。
    """
    st = _current_station(station_id)
    lat, lng = st.get("lat"), st.get("lng")

    from features.terrain import load_elevation_cache, terrain_class_of
    from features.poi_distance import get_poi_feature
    from features.station_profile import get_profile_cached

    terrain = load_elevation_cache().get(st["station_key"]) or {}
    return {
        "station_id": station_id,
        "location": {
            "station_name": st.get("station_name"), "district": st.get("district"),
            "lat": lat, "lng": lng, "total_docks": st.get("total_docks"),
        },
        "terrain": {"elevation": terrain.get("elevation"), "slope_pct": terrain.get("slope_pct"),
                    "terrain_class": terrain_class_of(terrain.get("slope_pct")),
                    "source": "cached" if terrain else "unavailable"},
        "poi": get_poi_feature(lat, lng),            # 現算（poi_data.json，快）
        "profile": get_profile_cached(station_id),   # 快取（_profile_cache，離線算）
        "note": "靜態/半靜態資料，前端開場拉一次即可，不需即時輪詢",
    }


@router.get("/stations/{station_id}/params")
def station_params(station_id: str):
    """3.12 站點參數（後台檢視）。優先回 DB 的生效版本（三層疊加），無則回 mock。

    附 target_usage_rate（0~100%）供與 usage_rate 同尺度比較。
    """
    from params import get_current
    current = get_current(station_id)
    if current is not None:
        return _with_target_usage_rate(current)
    # DB 尚無此站參數 → 回 mock 範例（開發階段）
    return None


@router.get("/stations/{station_id}/params/history")
def station_params_history(station_id: str):
    """3.12 站點參數版本歷史（回溯檢視，I-10）。新到舊，含每版來源與原因。"""
    from params import get_history
    return get_history(station_id)


@router.post("/stations/{station_id}/params/rollback")
def station_params_rollback(
    station_id: str,
    body: ParamsRollbackRequest,
    operator: dict = Depends(require_role("maintainer")),
):
    """3.12 回溯站點參數到指定版本（I-10，需 maintainer）。"""
    from params import rollback
    result = rollback(station_id, body.version, operator["operator_id"])
    if result is None:
        raise HTTPException(status_code=404,
                            detail=f"站點 {station_id} 無版本 {body.version}")
    return {"message": f"已回溯到版本 {body.version}", "params": _with_target_usage_rate(result)}


@router.post("/stations")
def create_station():
    """3.19 新增站別（冷啟動 + 連動重算）— A0 骨架"""
    _require_mock("新增站點")
    return {"message": "mock：新站已建立，鄰近站群已重算", "station_id": "NEW-MOCK"}


@router.delete("/stations/{station_id}")
def delete_station(station_id: str):
    """3.19 刪除站別（+ 連動重算）— A0 骨架"""
    _require_mock("刪除站點")
    return {"message": f"mock：站點 {station_id} 已移除，鄰近站群已重算"}
