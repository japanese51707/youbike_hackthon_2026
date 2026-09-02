"""
歷史資料源（讀 S3 的整合 Parquet）
===================================
資料在 s3://youbike-hackathon-2026/youbike_data/year_month=YYYY-MM/data.parquet，
每月一個 Parquet 分區，欄位為中文（主辦資料整合後的格式）。

本模組負責：
  1. 從 S3 讀 Parquet（可指定月份分區，避免讀全部 6 個月）
  2. 把中文欄位對映成 data_source 定義的「標準英文欄位」
  3. 提供 get_stations / get_station / get_history 三個介面

用途：
  - 「歷史回放」Demo（用真實 6 個月資料重現當時站點狀態）
  - 即時源掛掉時的降級來源（historical 同時段推估，見 degradation.py）
  - 注意：這是「歷史快照」，不是即時，data_freshness 一律標為 historical

依賴：boto3、pandas、pyarrow（已在 requirements）
"""

from __future__ import annotations
import io
import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Optional

from .data_source import DataSource, classify_status

# 中文欄位 → 標準英文欄位對映（對齊 S3 Parquet 實際 schema）
_COL_MAP = {
    "日期": "timestamp",
    "行政區": "district",
    "場站名稱": "station_name",
    "總車柱數": "total_docks",
    "可借車數": "available_bikes",
    "可還位數": "available_docks",
    "經度": "lng",
    "緯度": "lat",
    "借用率": "usage_rate",
}

# 站名→真實 station_id(sno) 對照表（來自新北市官方即時 API，站名比對命中 99.9%）
_LOOKUP_PATH = Path(__file__).parent / "station_id_lookup.json"


@lru_cache(maxsize=1)
def _load_station_id_lookup() -> dict:
    """載入站名→sno 對照表（快取）。找不到檔案就回空 dict，退回用站名當鍵。"""
    if not _LOOKUP_PATH.exists():
        return {}
    with open(_LOOKUP_PATH, "r", encoding="utf-8") as f:
        return json.load(f).get("stations", {})


def _resolve_station_id(station_name: str) -> str:
    """用站名查真實 station_id；查不到就退回站名本身當代理鍵（不中斷）。"""
    entry = _load_station_id_lookup().get(str(station_name).strip())
    return entry["station_id"] if entry else str(station_name)


def _cfg() -> dict:
    from config_loader import get_config
    return get_config().get("data_source", {})


def _bucket() -> str:
    # 允許環境變數覆寫（部署/測試用）
    return os.environ.get("YOUBIKE_S3_BUCKET", _cfg().get("s3_bucket", "youbike-hackathon-2026"))


def _prefix() -> str:
    return os.environ.get("YOUBIKE_S3_PREFIX", _cfg().get("s3_prefix", "youbike_data"))


class HistoricalDataSource(DataSource):
    name = "historical"

    def __init__(self, default_month: Optional[str] = None):
        # 預設月份分區（如 "2026-06"）；不給則用資料集最後一個月
        self._default_month = default_month or _cfg().get("historical_default_month", "2026-06")

    # ── S3 讀取（按月分區，lru_cache 避免重複下載）──
    @staticmethod
    @lru_cache(maxsize=6)
    def _load_month(bucket: str, prefix: str, month: str):
        """讀某月份分區的 Parquet → 已對映欄位的 DataFrame（快取）。"""
        import boto3
        import pyarrow.parquet as pq

        key = f"{prefix}/year_month={month}/data.parquet"
        s3 = boto3.client("s3")
        obj = s3.get_object(Bucket=bucket, Key=key)
        buf = io.BytesIO(obj["Body"].read())
        df = pq.read_table(buf).to_pandas()
        df = df.rename(columns=_COL_MAP)
        # 用站名→sno 對照表補真實 station_id（新北官方 API 比對，命中率 99.9%）；
        # 查不到的站退回用站名當代理鍵，不中斷。
        lookup = _load_station_id_lookup()
        df["station_id"] = df["station_name"].astype(str).str.strip().map(
            lambda n: lookup[n]["station_id"] if n in lookup else n
        )
        return df

    def _df(self, month: Optional[str] = None):
        return self._load_month(_bucket(), _prefix(), month or self._default_month)

    def _row_to_standard(self, row) -> dict:
        usage = float(row.get("usage_rate", 0) or 0)
        bikes = int(row.get("available_bikes", 0) or 0)
        docks = int(row.get("available_docks", 0) or 0)
        ts = str(row.get("timestamp", ""))
        return {
            "station_id": str(row.get("station_id", "")),
            "station_name": str(row.get("station_name", "")),
            "district": str(row.get("district", "")),
            "lat": float(row.get("lat", 0) or 0),
            "lng": float(row.get("lng", 0) or 0),
            "total_docks": int(row.get("total_docks", 0) or 0),
            "available_bikes": bikes,
            "available_docks": docks,
            "usage_rate": round(usage, 1),
            "status": classify_status(usage, bikes, docks),
            "service_available": True,
            "timestamp": ts,
            "source_timestamp": ts,
            "data_freshness": "historical",   # 歷史快照，非即時
        }

    def get_stations(
        self,
        district: Optional[str] = None,
        status: Optional[str] = None,
    ) -> list[dict]:
        """回傳「該月份分區最後一個時間點」每站一筆的快照（歷史現況近似）。"""
        df = self._df()
        if district:
            df = df[df["district"] == district]
        if df.empty:
            return []
        # 每站取最新一筆時間戳
        df = df.sort_values("timestamp").groupby("station_id", as_index=False).last()
        rows = [self._row_to_standard(r) for _, r in df.iterrows()]
        if status:
            wanted = set(status.split(","))
            rows = [r for r in rows if r["status"] in wanted]
        return rows

    def get_station(self, station_id: str) -> Optional[dict]:
        df = self._df()
        sub = df[df["station_id"] == station_id].sort_values("timestamp")
        if sub.empty:
            return None
        return self._row_to_standard(sub.iloc[-1])

    def get_history(
        self,
        station_id: str,
        start: Optional[str] = None,
        end: Optional[str] = None,
    ) -> list[dict]:
        """回傳單站的歷史時間序列（可用於時間軸/回放/降級同時段推估）。"""
        df = self._df()
        sub = df[df["station_id"] == station_id].sort_values("timestamp")
        if start:
            sub = sub[sub["timestamp"].astype(str) >= start]
        if end:
            sub = sub[sub["timestamp"].astype(str) <= end]
        return [self._row_to_standard(r) for _, r in sub.iterrows()]

    def health(self) -> dict:
        try:
            df = self._df()
            return {"source": self.name, "available": True,
                    "detail": f"{self._default_month}｜{len(df)} rows"}
        except Exception as e:
            return {"source": self.name, "available": False, "detail": str(e)}
