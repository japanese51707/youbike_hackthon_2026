"""
資料源抽象介面 + 工廠（NFR-7 資料源可抽換）
=============================================
所有資料源（mock / 歷史 Parquet / TDX 即時 / YouBike 官方）都實作同一組介面，
上層（API、規則引擎）只依賴這個介面，不管資料實際從哪來。

換源只改 config.yaml 的 `data_source.mode`，不改任何程式碼（呼應 steering §7）。

對外暴露：
    get_data_source() -> DataSource   # 依 config 回傳對應實作（單例快取）
    DataSource                        # 抽象基底類別，定義介面契約

回傳格式契約
------------
所有實作的 get_stations() 都回傳「標準站點 dict」的 list，欄位固定為：
    station_id, station_name, district, lat, lng,
    total_docks, available_bikes, available_docks, usage_rate, status,
    service_available, timestamp, source_timestamp, data_freshness
不同來源（中文欄位的 Parquet、英文欄位的 mock、TDX 的原始格式）
各自負責在自己的實作裡轉成這個標準格式，上層永遠拿到一致的欄位。
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Optional

# 標準站點欄位（各資料源都要對齊到這組欄位）
STANDARD_STATION_FIELDS = [
    "station_id", "station_name", "district", "lat", "lng",
    "total_docks", "available_bikes", "available_docks", "usage_rate", "status",
    "service_available", "timestamp", "source_timestamp", "data_freshness",
]


def classify_status(usage_rate: float, available_bikes: int, available_docks: int) -> str:
    """依借用率/可借可還推站點狀態，讓不同來源產出一致的 status 語意。

    usage_rate 為 0~100（借用率＝可借/總數）。
    """
    # 故障/未啟用（ADR-108 資料品質）：可借與可還同時為 0＝站點離線/故障
    # （正常站可借+可還≈總柱數，不會同時 0）。標 offline，不當「空站」誤觸調度。
    if available_bikes <= 0 and available_docks <= 0:
        return "offline"
    if available_bikes <= 0:
        return "empty"
    if available_docks <= 0:
        return "full"
    if usage_rate < 20:
        return "low"
    if usage_rate > 80:
        return "high"
    return "normal"


class DataSource(ABC):
    """資料源介面。所有實作都必須提供這些方法，回傳標準格式。"""

    #: 來源標記，寫進 data_freshness 或稽核用（如 "mock" / "historical" / "tdx"）
    name: str = "abstract"

    @abstractmethod
    def get_stations(
        self,
        district: Optional[str] = None,
        status: Optional[str] = None,
    ) -> list[dict]:
        """回傳所有（或篩選後）站點的即時狀態，標準欄位格式。

        district: 只回某行政區；status: 逗號分隔的狀態白名單（如 "empty,low"）。
        """
        ...

    @abstractmethod
    def get_station(self, station_id: str) -> Optional[dict]:
        """回傳單一站點的當前狀態（找不到回 None）。"""
        ...

    @abstractmethod
    def get_history(
        self,
        station_id: str,
        start: Optional[str] = None,
        end: Optional[str] = None,
    ) -> list[dict]:
        """回傳單站的歷史序列（時間點 + 當時狀態）。給時間軸/回放/降級用。"""
        ...

    def health(self) -> dict:
        """來源健康狀態（給降級判斷用）。預設視為可用，即時源會覆寫。"""
        return {"source": self.name, "available": True, "detail": "ok"}


# ── 工廠：依 config 回傳對應實作（單例快取）──
_instance: Optional[DataSource] = None
_instance_mode: Optional[str] = None


def get_data_source(force_mode: Optional[str] = None) -> DataSource:
    """依 config.yaml 的 data_source.mode 回傳對應的資料源實作。

    force_mode: 測試/降級時可強制指定，不動 config。
    快取單例；mode 改變時自動重建。
    """
    global _instance, _instance_mode

    if force_mode is not None:
        return _build(force_mode)

    from config_loader import get_config
    mode = get_config().get("data_source", {}).get("mode", "mock")

    if _instance is None or _instance_mode != mode:
        _instance = _build(mode)
        _instance_mode = mode
    return _instance


def _build(mode: str) -> DataSource:
    """依 mode 字串建立對應實作。集中在這裡，未來加新來源只改這一處。"""
    if mode == "mock":
        from .mock import MockDataSource
        return MockDataSource()
    if mode == "historical":
        from .historical import HistoricalDataSource
        return HistoricalDataSource()
    if mode == "tdx":
        from .tdx import TDXDataSource
        return TDXDataSource()
    if mode == "youbike_official":
        from .youbike_official import YouBikeOfficialDataSource
        return YouBikeOfficialDataSource()
    raise ValueError(
        f"未知的 data_source.mode：'{mode}'（可用：mock / historical / tdx / youbike_official）"
    )


def reset_data_source() -> None:
    """清掉快取單例（測試或切換 mode 後用）。"""
    global _instance, _instance_mode
    _instance = None
    _instance_mode = None
    from . import observations, degradation
    observations.reset()
    degradation.reset()
