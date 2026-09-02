"""
資料源層（core.data）
=====================
統一資料存取入口。上層透過 get_data_source() 拿介面、用 get_stations_with_degradation()
拿有降級保護的資料，不直接碰任何特定來源。

換源只改 config.yaml 的 data_source.mode（mock / historical / tdx / youbike_official）。
"""

from .data_source import (
    DataSource,
    get_data_source,
    reset_data_source,
    classify_status,
    STANDARD_STATION_FIELDS,
)
from .degradation import (
    get_stations_with_degradation,
    degradation_status,
)

__all__ = [
    "DataSource",
    "get_data_source",
    "reset_data_source",
    "classify_status",
    "STANDARD_STATION_FIELDS",
    "get_stations_with_degradation",
    "degradation_status",
]
