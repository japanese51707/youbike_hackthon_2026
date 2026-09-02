"""
YouBike 官方即時資料源（骨架，預留）
=====================================
若現場改用 YouBike 公司自己的即時 API（非 TDX），走這個實作。
與 tdx.py 平行，介面相同，差在來源 URL 與回應格式。

實作待確認官方端點與欄位後補。安全備註同 tdx.py（金鑰/URL 從 config 讀、
第三方回應當不可信輸入、不外洩憑證）。
"""

from __future__ import annotations
from typing import Optional

from .data_source import DataSource


class YouBikeOfficialDataSource(DataSource):
    name = "youbike_official"

    def __init__(self):
        from config_loader import get_config
        ds = get_config().get("data_source", {})
        self._url = ds.get("youbike_official_url", "")
        self._refresh = ds.get("refresh_interval_sec", 60)

    def _not_ready(self):
        raise NotImplementedError(
            "YouBike 官方即時源尚未實作。確認官方端點與欄位格式後補上。"
            "現場未接前請維持 config mode=mock/historical。"
        )

    def get_stations(self, district: Optional[str] = None, status: Optional[str] = None) -> list[dict]:
        self._not_ready()

    def get_station(self, station_id: str) -> Optional[dict]:
        self._not_ready()

    def get_history(self, station_id: str, start: Optional[str] = None, end: Optional[str] = None) -> list[dict]:
        raise NotImplementedError("官方源為即時源，歷史查詢請用 historical 資料源。")

    def health(self) -> dict:
        return {"source": self.name, "available": False,
                "detail": "未實作；有 url=" + ("yes" if self._url else "no")}
