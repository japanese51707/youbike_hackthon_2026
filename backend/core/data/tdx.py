"""
TDX 即時資料源（骨架，正式現場才接）
=====================================
TDX（交通部運輸資料流通服務）提供 YouBike 即時站點資料。
現階段只留介面骨架與接入位置，實作待拿到 API key 且確認欄位格式後補。

安全備註（呼應 steering §11 出向信任）：
  - API key 只從環境變數 / config 讀，不寫死（見 config.data_source.tdx_api_key）
  - 第三方回應當「不可信輸入」：驗證欄位、設超時、限制重試次數
  - 不把 key 寫進 log 或錯誤訊息

未實作的方法明確 raise（steering §4 失敗要看得見），不回假資料混淆上層。
降級由 degradation.py 負責：即時源不可用時退回 historical。
"""

from __future__ import annotations
from typing import Optional

from .data_source import DataSource


class TDXDataSource(DataSource):
    name = "tdx"

    def __init__(self):
        from config_loader import get_config
        ds = get_config().get("data_source", {})
        self._api_key = ds.get("tdx_api_key", "")
        self._refresh = ds.get("refresh_interval_sec", 60)

    def _not_ready(self):
        raise NotImplementedError(
            "TDX 即時源尚未實作。取得 API key 並確認欄位對映後補上 _fetch()。"
            "現場若要用即時源，請先完成此模組；否則保持 config mode=mock/historical。"
        )

    def get_stations(self, district: Optional[str] = None, status: Optional[str] = None) -> list[dict]:
        self._not_ready()

    def get_station(self, station_id: str) -> Optional[dict]:
        self._not_ready()

    def get_history(self, station_id: str, start: Optional[str] = None, end: Optional[str] = None) -> list[dict]:
        # TDX 是即時源，歷史應走 historical
        raise NotImplementedError("TDX 為即時源，歷史查詢請用 historical 資料源。")

    def health(self) -> dict:
        # 尚未實作即視為不可用，讓降級機制接手（而非假裝可用）
        return {"source": self.name, "available": False,
                "detail": "未實作；有 api_key=" + ("yes" if self._api_key else "no")}
