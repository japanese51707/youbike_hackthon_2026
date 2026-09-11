"""ADR-303: retain last successful observations, never substitute history for live."""
from copy import deepcopy
from datetime import datetime, timezone
from threading import RLock
from .data_source import get_data_source
from .observations import DataUnavailable, normalize, parse_time, record

_lock = RLock()
_last = None
_last_source = None


def _cfg():
    from config_loader import get_config
    ds = get_config().get("data_source", {})
    return {"mode": ds.get("mode", "mock"), "stale_after_sec": ds.get("stale_after_sec", 600)}


def _is_stale(source_timestamp, stale_after_sec):
    try:
        age = (datetime.now(timezone.utc) - parse_time(source_timestamp)).total_seconds()
        return age > stale_after_sec or age < -60
    except (ValueError, TypeError):
        return True


def get_stations_with_degradation(district=None, status=None):
    global _last, _last_source
    cfg = _cfg()
    primary = get_data_source()
    source_key = (cfg["mode"], primary)
    with _lock:
        failed = False
        try:
            rows = primary.get_stations()
            if not rows:
                raise DataUnavailable("資料來源未提供站點快照")
            _last, _last_source = deepcopy(rows), source_key
        except Exception as exc:
            if _last_source != source_key or not _last:
                raise DataUnavailable("站點資料暫時無法取得，請稍後重試") from exc
            rows, failed = deepcopy(_last), True
        rows = [normalize(r, cfg["mode"], cfg["stale_after_sec"], failed=failed) for r in rows]
        record(rows)
    if district:
        rows = [r for r in rows if r.get("district") == district]
    if status:
        wanted = {s.strip() for s in status.split(",")}
        rows = [r for r in rows if r.get("status") in wanted]
    return rows


def degradation_status():
    cfg = _cfg()
    try:
        rows = get_stations_with_degradation()
        counts = {key: sum(r["data_freshness"] == key for r in rows)
                  for key in ("live", "stale", "historical", "mock")}
        return {**cfg, "source": cfg["mode"], "primary_available": not any(
            "upstream_unavailable" in r["quality_reasons"] for r in rows),
            "freshness_counts": counts, "degrading_to_historical": False,
            "dispatch_eligible_count": sum(r["dispatch_eligible"] for r in rows)}
    except DataUnavailable:
        return {**cfg, "source": cfg["mode"], "primary_available": False,
                "data_freshness": "unavailable", "degrading_to_historical": False}


def reset():
    global _last, _last_source
    with _lock:
        _last = _last_source = None
