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

    @staticmethod
    @lru_cache(maxsize=2)
    def _load_local(path):
        import pandas as pd
        df = pd.read_parquet(path).rename(columns=_COL_MAP)
        df["station_id"] = df["station_name"].astype(str).map(_resolve_station_id)
        return df

    def _df(self, month: Optional[str] = None):
        month = month or self._default_month
        local = os.environ.get("YOUBIKE_HISTORY_DIR", _cfg().get("historical_local_dir", ""))
        if local:
            base = Path(local)
            if not base.is_absolute():
                base = Path(__file__).resolve().parents[3] / base
            return self._load_local(str(base / f"year_month={month}" / "data.parquet"))
        return self._load_month(_bucket(), _prefix(), month)

    def _row_to_standard(self, row) -> dict:
        usage = float(row.get("usage_rate", 0) or 0)
        bikes = int(row.get("available_bikes", 0) or 0)
        docks = int(row.get("available_docks", 0) or 0)
        from .observations import parse_time
        ts = parse_time(row.get("timestamp")).isoformat()
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
            "source": "historical",
            "identity_source": "official_name_lookup" if str(row.get("station_name", "")).strip() in _load_station_id_lookup() else "unmapped_historical_name",
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

    def _row_to_history_point(self, row) -> dict:
        std = self._row_to_standard(row)
        return {
            "station_id": std["station_id"],
            "station_name": std["station_name"],
            "district": std["district"],
            "lat": std["lat"],
            "lng": std["lng"],
            "total_docks": std["total_docks"],
            "available_bikes": std["available_bikes"],
            "available_docks": std["available_docks"],
            "usage_rate": std["usage_rate"],
            "status": std["status"],
            "urgency_score": None,
            "timestamp": std["timestamp"],
        }

    def get_timeline(
        self,
        district: str = "中和區",
        date: str = "2026-06-02",
        interval: int = 30,
    ) -> dict:
        """既有 API 3.10：回傳某日、可選行政區的歷史快照序列。全市用 district=全市。"""
        import pandas as pd

        interval = max(int(interval or 30), 1)
        month = date[:7] if date and len(date) >= 7 else self._default_month
        df = self._df(month)
        times = pd.to_datetime(df["timestamp"])
        day = pd.to_datetime(date)
        day_df = df.loc[(times >= day) & (times < day + pd.Timedelta(days=1))].copy()
        note = None
        actual_date = date
        if day_df.empty:
            last = times.max()
            actual_date = pd.Timestamp(last).strftime("%Y-%m-%d")
            if actual_date[:7] != month:
                df = self._df(actual_date[:7])
                times = pd.to_datetime(df["timestamp"])
            day = pd.to_datetime(actual_date)
            day_df = df.loc[(times >= day) & (times < day + pd.Timedelta(days=1))].copy()
            note = f"請求日期無資料，改用歷史最後一日 {actual_date}"
        citywide = district in (None, "", "全市", "all", "全部", "*")
        if not citywide:
            day_df = day_df[day_df["district"] == district]
        if day_df.empty:
            raise ValueError("此範圍沒有歷史時間軸")

        stamp = pd.to_datetime(day_df["timestamp"])
        minutes = stamp.dt.hour * 60 + stamp.dt.minute
        slot = (minutes // interval) * interval
        day_df = day_df.assign(
            _time=(slot // 60).astype(int).map(lambda h: f"{h:02d}")
            + ":"
            + (slot % 60).astype(int).map(lambda m: f"{m:02d}")
        )
        frames = []
        for time_label, group in day_df.groupby("_time", sort=True):
            latest = group.sort_values("timestamp").groupby("station_id", as_index=False).last()
            frames.append({
                "time": time_label,
                "stations": [self._row_to_history_point(r) for _, r in latest.iterrows()],
            })
        return {
            "district": "全市" if citywide else district,
            "date": actual_date,
            "interval": interval,
            "source": "historical",
            "note": note,
            "frames": frames,
        }

    def get_history(
        self,
        station_id: str,
        start: Optional[str] = None,
        end: Optional[str] = None,
    ) -> list[dict]:
        """回傳單站的歷史時間序列（可用於時間軸/回放/降級同時段推估）。"""
        import pandas as pd
        from .observations import parse_time, TAIPEI
        start_dt = parse_time(start).astimezone(TAIPEI).replace(tzinfo=None) if start else None
        end_dt = parse_time(end).astimezone(TAIPEI).replace(tzinfo=None) if end else None
        months = [self._default_month]
        if start_dt and end_dt:
            if end_dt < start_dt or (end_dt - start_dt).days > 31:
                raise ValueError("歷史查詢區間須在 31 天內")
            months = [str(m) for m in pd.period_range(start_dt, end_dt, freq="M")]
        rows = []
        for month in months:
            df = self._df(month)
            sub = df[df["station_id"] == station_id].copy()
            times = pd.to_datetime(sub["timestamp"])
            if start_dt:
                sub = sub[times >= start_dt]
            if end_dt:
                sub = sub[pd.to_datetime(sub["timestamp"]) <= end_dt]
            rows.extend(self._row_to_standard(r) for _, r in sub.iterrows())
        return sorted(rows, key=lambda r: r["timestamp"])

    def health(self) -> dict:
        try:
            df = self._df()
            return {"source": self.name, "available": True,
                    "detail": f"{self._default_month}｜{len(df)} rows"}
        except Exception as e:
            return {"source": self.name, "available": False, "detail": str(e)}

    def slot_median(self, station_id: str, weekday: int, time_slot: int,
                    months: Optional[tuple[str, ...]] = None) -> Optional[float]:
        """回傳某站在指定 weekday+time_slot 的歷史 available_bikes 中位數；查無回 None。"""
        if months is None:
            cfg = _cfg()
            # 預設用全部可用月份（1~default_month），週期樣本越多越穩。
            last = int(str(cfg.get("historical_default_month", "2026-06"))[-2:])
            year = str(cfg.get("historical_default_month", "2026-06"))[:4]
            months = tuple(f"{year}-{mo:02d}" for mo in range(1, last + 1))
        table = _slot_table(tuple(sorted(months)))
        return table.get((str(station_id), int(weekday), int(time_slot)))


# ── ADR-306：同時段歷史代理查表（模組級快取，跨 instance 共用）──
# 比賽階段只有 1–6 月官方歷史、即時是 9 月，模型的 lag（絕對往前推 1 天/1 週）
# 在即時 asof 下取不到真值。用「同一站 × 同 weekday × 同 time_slot」的歷史
# available_bikes 中位數當代理，讓 predict 能補上 lag。屬近似值（週期性代理，非真值），
# 呼叫端須誠實標示，且此代理只餵預測特徵、不改站況/不進派工 payload。
# 用模組級 lru_cache：整包查表建一次常駐（首次含 S3 讀取較慢，之後 O(1) 查詢）。
@lru_cache(maxsize=1)
def _slot_table(months: tuple[str, ...]) -> dict:
    import pandas as pd
    src = HistoricalDataSource()
    frames = []
    for m in months:
        try:
            frames.append(src._df(m))
        except Exception:
            continue  # 缺某月分區不致命，用有的月份即可
    if not frames:
        return {}
    df = pd.concat(frames, ignore_index=True)
    t = pd.to_datetime(df["timestamp"])
    df = df.assign(_wd=t.dt.weekday, _slot=t.dt.hour * 2 + (t.dt.minute >= 30).astype(int))
    grouped = df.groupby(["station_id", "_wd", "_slot"])["available_bikes"].median()
    return {(str(sid), int(wd), int(slot)): float(val)
            for (sid, wd, slot), val in grouped.items()}
