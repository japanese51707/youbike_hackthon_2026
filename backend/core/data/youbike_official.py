"""
新北市 YouBike2.0 官方即時資料源（ADR-113）
============================================
接新北市開放資料「YouBike2.0 即時」CSV：
  https://data.ntpc.gov.tw/api/datasets/010e5b15-3823-4b20-b401-b1cf000550c5/csv/file
與 tdx.py 平行，介面相同（DataSource），差在來源 URL 與欄位。可抽換（ADR-006）。

即時源欄位（實測）→ 標準欄位映射：
  sno→station_id, sna→station_name, sarea→district, lat/lng,
  tot_quantity→total_docks, sbi_quantity→available_bikes, bemp→available_docks,
  mday→source_timestamp（秒級 YYYYMMDDThhmmss）, act→service_available(1啟用),
  yb2_quantity/eyb_quantity→YouBike2.0/電輔車數（額外保留）。

安全備註：政府平台 SSL 憑證鏈問題需 verify=False（比照 calendar_holiday，一次性公開資料源）；
第三方回應當不可信輸入（欄位缺失/型別容錯）；無金鑰、無個資。
開發階段當「測試數據源」（當場打一次拿快照），常駐拉取待正式環境（ADR-113）。
"""

from __future__ import annotations
import csv
import io
from datetime import datetime, timezone, timedelta
from typing import Optional

from .data_source import DataSource, classify_status

_DEFAULT_URL = ("https://data.ntpc.gov.tw/api/datasets/"
                "010e5b15-3823-4b20-b401-b1cf000550c5/csv/file")


class YouBikeOfficialDataSource(DataSource):
    name = "youbike_official"

    def __init__(self):
        from config_loader import get_config
        ds = get_config().get("data_source", {})
        self._url = ds.get("youbike_official_url", "") or _DEFAULT_URL
        self._refresh = ds.get("refresh_interval_sec", 60)
        self._cache: list[dict] = []
        self._cache_at: Optional[datetime] = None

    # ── 內部：抓 CSV + 映射標準欄位 ──
    def _fetch_raw(self) -> list[dict]:
        import httpx
        # 政府平台憑證鏈問題，verify=False（一次性公開資料，無金鑰無個資）
        r = httpx.get(self._url, timeout=60, follow_redirects=True, verify=False)
        r.raise_for_status()
        text = r.text.lstrip("\ufeff")   # 去 BOM
        return list(csv.DictReader(io.StringIO(text)))

    @staticmethod
    def _to_standard(row: dict) -> Optional[dict]:
        """即時 CSV 一列 → 標準站點 dict。欄位缺失/型別錯則回 None（不可信輸入容錯）。"""
        def _int(v, d=0):
            try:
                return int(float(v))
            except (TypeError, ValueError):
                return d
        def _float(v, d=0.0):
            try:
                return float(v)
            except (TypeError, ValueError):
                return d
        sid = (row.get("sno") or "").strip()
        if not sid:
            return None
        total = _int(row.get("tot_quantity"))
        avail = _int(row.get("sbi_quantity"))
        docks = _int(row.get("bemp"))
        lat, lng = _float(row.get("lat")), _float(row.get("lng"))
        if lat == 0.0 or lng == 0.0:
            return None
        usage = (avail / total * 100) if total > 0 else 0.0
        act = (row.get("act") or "1").strip()
        service_available = (act == "1")   # act=1 啟用中
        # mday: 20260907T002402（無時區，視為台北時間）
        src_ts = (row.get("mday") or "").strip()
        return {
            "station_id": sid,
            "station_name": (row.get("sna") or "").strip(),
            "district": (row.get("sarea") or "").strip(),
            "lat": lat, "lng": lng,
            "total_docks": total,
            "available_bikes": avail,
            "available_docks": docks,
            "usage_rate": round(usage, 1),
            "status": classify_status(usage, avail, docks),
            "service_available": service_available,
            "timestamp": datetime.now(timezone(timedelta(hours=8))).isoformat(),
            "source_timestamp": src_ts,
            "data_freshness": "live:youbike_official",
            # 額外保留（ADR-113：電輔車數，未來因子/顯示用）
            "yb2_quantity": _int(row.get("yb2_quantity")),
            "eyb_quantity": _int(row.get("eyb_quantity")),
        }

    def _load(self, force: bool = False) -> list[dict]:
        """抓並快取（refresh 秒內重用，避免頻繁打 API）。"""
        now = datetime.now(timezone.utc)
        if (not force and self._cache and self._cache_at
                and (now - self._cache_at).total_seconds() < self._refresh):
            return self._cache
        rows = self._fetch_raw()
        std = [s for s in (self._to_standard(r) for r in rows) if s is not None]
        self._cache, self._cache_at = std, now
        return std

    # ── DataSource 介面 ──
    def get_stations(self, district: Optional[str] = None, status: Optional[str] = None) -> list[dict]:
        out = self._load()
        if district:
            out = [s for s in out if s["district"] == district]
        if status:
            allow = {x.strip() for x in status.split(",")}
            out = [s for s in out if s["status"] in allow]
        return out

    def get_station(self, station_id: str) -> Optional[dict]:
        for s in self._load():
            if s["station_id"] == station_id:
                return s
        return None

    def get_history(self, station_id: str, start: Optional[str] = None, end: Optional[str] = None) -> list[dict]:
        raise NotImplementedError("官方源為即時源，歷史查詢請用 historical 資料源。")

    def health(self) -> dict:
        try:
            n = len(self._load())
            return {"source": self.name, "available": n > 0, "detail": f"live {n} 站"}
        except Exception as e:
            return {"source": self.name, "available": False, "detail": str(e)[:80]}
