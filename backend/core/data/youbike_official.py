"""New Taipei official snapshot adapter (ADR-121/303); verified, bounded HTTPS."""
from copy import deepcopy
import csv
import io
import math
from datetime import datetime, timezone
from threading import RLock
from time import monotonic
from urllib.parse import urlparse
from .data_source import DataSource, classify_status
from .observations import DataUnavailable, parse_time

_DEFAULT_URL = ("https://data.ntpc.gov.tw/api/datasets/"
                "010e5b15-3823-4b20-b401-b1cf000550c5/csv/file")


class YouBikeOfficialDataSource(DataSource):
    name = "youbike_official"

    def __init__(self):
        from config_loader import get_config
        ds = get_config().get("data_source", {})
        self._url = ds.get("youbike_official_url") or _DEFAULT_URL
        parsed = urlparse(self._url)
        if (parsed.scheme != "https" or parsed.hostname != "data.ntpc.gov.tw"
                or parsed.port not in (None, 443) or parsed.username or parsed.password):
            raise ValueError("官方資料源須使用 data.ntpc.gov.tw 的 HTTPS 網址")
        self._refresh = max(ds.get("min_refresh_sec", 60), ds.get("refresh_interval_sec", 300))
        self._timeout = ds.get("timeout_sec", 10)
        self._max_bytes = ds.get("max_response_bytes", 5_000_000)
        self._backoff = ds.get("retry_backoff_sec", 30)
        self._cache = []
        self._cache_at = None
        self._retry_at = 0
        self._lock = RLock()

    def _fetch_raw(self):
        import httpx
        import ssl
        import certifi
        context = ssl.create_default_context(cafile=certifi.where())
        # Official chain lacks SKI on a CA. Match the Python 3.12 baseline:
        # retain CERT_REQUIRED, hostname/expiry/signature/CA verification.
        # Scope this legacy X.509 compatibility to the fixed official host only.
        context.verify_flags &= ~ssl.VERIFY_X509_STRICT
        with httpx.stream("GET", self._url, timeout=self._timeout, follow_redirects=False, verify=context) as response:
            response.raise_for_status()
            body = bytearray()
            for chunk in response.iter_bytes():
                body.extend(chunk)
                if len(body) > self._max_bytes:
                    raise DataUnavailable("官方資料回應超過大小限制")
        return list(csv.DictReader(io.StringIO(body.decode("utf-8-sig"))))

    @staticmethod
    def _to_standard(row):
        try:
            sid = row["sno"].strip()
            lat, lng = float(row["lat"]), float(row["lng"])
            if not sid or not (math.isfinite(lat) and math.isfinite(lng)
                               and -90 <= lat <= 90 and -180 <= lng <= 180):
                return None
            values = [float(row[k]) for k in ("tot_quantity", "sbi_quantity", "bemp")]
            if any(not math.isfinite(v) or v < 0 or not v.is_integer() for v in values):
                return None
            total, avail, docks = map(int, values)
            if total <= 0 or avail + docks > total:
                return None
            observed = parse_time(row["mday"]).isoformat()
            act = row["act"].strip()
            if act not in ("0", "1"):
                return None
        except (KeyError, TypeError, ValueError, OverflowError, AttributeError):
            return None
        usage = avail / total * 100
        result = {
            "station_id": sid, "station_name": (row.get("sna") or "").strip(),
            "district": (row.get("sarea") or "").strip(), "lat": lat, "lng": lng,
            "station_key": f"{round(lat, 4)}_{round(lng, 4)}",
            "total_docks": total, "available_bikes": avail, "available_docks": docks,
            "usage_rate": round(usage, 1),
            "status": classify_status(usage, avail, docks) if act == "1" else "offline",
            "service_available": act == "1", "timestamp": observed,
            "observed_at": observed, "source_timestamp": observed,
            "received_at": datetime.now(timezone.utc).isoformat(),
            "data_freshness": "live", "source": "youbike_official",
        }
        for key in ("yb2_quantity", "eyb_quantity"):
            try:
                value = float(row[key])
                result[key] = int(value) if math.isfinite(value) and value.is_integer() and 0 <= value <= total else None
            except (KeyError, TypeError, ValueError):
                result[key] = None
        return result

    def _load(self, force=False):
        with self._lock:
            now = datetime.now(timezone.utc)
            if not force and self._cache_at and (now - self._cache_at).total_seconds() < self._refresh:
                return deepcopy(self._cache)
            if monotonic() < self._retry_at:
                raise DataUnavailable("官方資料來源暫時不可用")
            try:
                raw = self._fetch_raw()
                rows = [s for r in raw if (s := self._to_standard(r)) is not None]
                # A partial/invalid response must not silently erase stations from the map.
                if not rows or len(rows) != len(raw) or len({r["station_id"] for r in rows}) != len(rows):
                    raise DataUnavailable("官方站點資料驗證失敗")
                self._cache, self._cache_at = rows, now
            except Exception:
                self._retry_at = monotonic() + self._backoff
                raise
            return deepcopy(self._cache)

    def get_stations(self, district=None, status=None):
        rows = self._load()
        if district:
            rows = [s for s in rows if s["district"] == district]
        if status:
            wanted = {x.strip() for x in status.split(",")}
            rows = [s for s in rows if s["status"] in wanted]
        return rows

    def get_station(self, station_id):
        return next((s for s in self._load() if s["station_id"] == station_id), None)

    def get_history(self, station_id, start=None, end=None):
        raise NotImplementedError("即時來源不提供歷史；請使用歷史查詢服務")

    def health(self):
        try:
            rows = self._load()
            return {"source": self.name, "available": bool(rows), "station_count": len(rows)}
        except Exception:
            return {"source": self.name, "available": False, "detail": "官方資料暫時無法取得"}
