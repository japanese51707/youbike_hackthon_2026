"""
站點端點（3.1, 3.2, 3.9, 3.10, 3.19）
薄層：A0 回 mock。注意路由順序 — 靜態路徑(heatmap/timeline)先於動態路徑(/{id})。
"""

from fastapi import APIRouter, HTTPException, Depends
from mock_store import get_mock
from core.data import get_data_source, get_stations_with_degradation
from auth import require_role
from models_schema.params_ops import ParamsRollbackRequest

router = APIRouter(prefix="/api/v1", tags=["stations"])


@router.get("/stations")
def list_stations(district: str | None = None, status: str | None = None):
    """3.1 所有站點即時狀態（前端畫地圖）

    走 data_source 層 + 降級保護：即時源掛掉會自動退回歷史，並標 data_freshness。
    換源只改 config.data_source.mode（mock / historical / tdx / youbike_official）。
    """
    return get_stations_with_degradation(district=district, status=status)


# 靜態路徑要先於 /stations/{station_id} 註冊，否則會被當成 station_id
@router.get("/stations/heatmap")
def heatmap(dimension: str = "area_type"):
    """3.9 多維度熱點聚合"""
    return get_mock()["heatmap"]


@router.get("/stations/timeline")
def timeline(district: str = "中和區", date: str = "2026-06-02", interval: int = 30):
    """3.10 時間軸序列（讀預存歷史）"""
    return get_mock()["timeline"]


@router.get("/stations/{station_id}")
def station_detail(station_id: str, history_range: str = "7d"):
    """3.2 單站詳情 + 預測 + 參數 + 歷史

    current/history 走 data_source 層；prediction/params 仍為 mock（待 B 的模型接上）。
    """
    ds = get_data_source()
    current = ds.get_station(station_id)
    if current is None:
        raise HTTPException(status_code=404, detail=f"找不到站點 {station_id}")
    history = ds.get_history(station_id)
    # prediction / params 目前仍用 mock 範例（B 的預測模型 A6 接上後取代）
    mock_detail = get_mock()["station_detail"]
    return {
        "current": current,
        "history": history,
        "prediction": mock_detail.get("prediction"),
        "params": _with_target_usage_rate(mock_detail.get("params")),
    }


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
    return _with_target_usage_rate(get_mock()["station_detail"]["params"])


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
    return {"message": "mock：新站已建立，鄰近站群已重算", "station_id": "NEW-MOCK"}


@router.delete("/stations/{station_id}")
def delete_station(station_id: str):
    """3.19 刪除站別（+ 連動重算）— A0 骨架"""
    return {"message": f"mock：站點 {station_id} 已移除，鄰近站群已重算"}
