"""
Mock 資料源（讀 mock_data.json）
=================================
把 A0 的 mock_store 包成 DataSource 介面，讓上層用統一介面取假資料。
mock_data.json 的欄位本來就是標準英文欄位，這裡幾乎直接回傳，只做篩選。

mode="mock" 時（開發/Demo 預設）由工廠回傳本類別。
"""

from __future__ import annotations
from typing import Optional

from .data_source import DataSource


class MockDataSource(DataSource):
    name = "mock"

    def _all(self) -> dict:
        # 沿用既有 mock_store 的載入與快取，不重造輪子
        from mock_store import get_mock
        return get_mock()

    def get_stations(
        self,
        district: Optional[str] = None,
        status: Optional[str] = None,
    ) -> list[dict]:
        stations = self._all()["stations"]
        if district:
            stations = [s for s in stations if s["district"] == district]
        if status:
            wanted = set(status.split(","))
            stations = [s for s in stations if s["status"] in wanted]
        return stations

    def get_station(self, station_id: str) -> Optional[dict]:
        for s in self._all()["stations"]:
            if s["station_id"] == station_id:
                return s
        return None

    def get_history(
        self,
        station_id: str,
        start: Optional[str] = None,
        end: Optional[str] = None,
    ) -> list[dict]:
        # mock 只有 station_detail 內含一段 history 範例
        detail = self._all().get("station_detail", {})
        if detail.get("current", {}).get("station_id") == station_id:
            hist = detail.get("history", [])
        else:
            hist = []
        if start:
            hist = [h for h in hist if h["timestamp"] >= start]
        if end:
            hist = [h for h in hist if h["timestamp"] <= end]
        return hist

    def health(self) -> dict:
        try:
            n = len(self._all()["stations"])
            return {"source": self.name, "available": True, "detail": f"{n} stations"}
        except Exception as e:
            return {"source": self.name, "available": False, "detail": str(e)}
