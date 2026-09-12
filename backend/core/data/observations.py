"""ADR-303: explicit observation clocks and bounded, source-isolated lag storage."""
from collections import OrderedDict, deque
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import math
import re
from threading import RLock

TAIPEI = timezone(timedelta(hours=8))


class DataUnavailable(RuntimeError):
    """No trustworthy snapshot is available; exposed as a safe HTTP 503."""


# 緊湊基本式 ISO 8601（YYYYMMDDTHHMMSS）→ 拆出各欄位以改寫成擴充式。
_COMPACT_ISO = re.compile(r"^(\d{4})(\d{2})(\d{2})[T ](\d{2})(\d{2})(\d{2})(.*)$")
# 無冒號時區位移（+0800）→ 補冒號。尾端四位必須全為數字，因此不誤中 +08:00。
_BARE_OFFSET = re.compile(r"^(.*[+-])(\d{2})(\d{2})$")


def _relax_iso(text):
    """把實際來源會出現、但 Python 3.10 fromisoformat 不收的 ISO 8601 變體正規化。

    3.11 起 fromisoformat 已全面支援 ISO 8601；3.10 只吃 isoformat() 自己的輸出。
    因此官方即時源的 mday（20260912T093402）與歷史查詢邊界的 Z 結尾
    （2026-05-31T15:00:00Z）在 3.10 都會 ValueError。只做等價改寫，不推測時區。
    """
    match = _COMPACT_ISO.match(text)
    if match:
        year, month, day, hour, minute, second, rest = match.groups()
        text = f"{year}-{month}-{day}T{hour}:{minute}:{second}{rest}"
    if text[-1:] in ("Z", "z"):
        text = text[:-1] + "+00:00"
    match = _BARE_OFFSET.match(text)
    if match:
        text = f"{match.group(1)}{match.group(2)}:{match.group(3)}"
    return text


def parse_time(value):
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).strip()
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            # 只在標準解析失敗後才正規化，保證原本已可解析的輸入行為完全不變；
            # 正規化後仍不合法則由 fromisoformat 拋出原有的 ValueError。
            dt = datetime.fromisoformat(_relax_iso(text))
    return dt.replace(tzinfo=TAIPEI) if dt.tzinfo is None else dt


def normalize(row, source, stale_after_sec=600, now=None, failed=False):
    from config_loader import get_config
    cfg = get_config().get("data_source", {})
    now = now or datetime.now(timezone.utc)
    result = deepcopy(row)
    reasons = list(row.get("quality_reasons", []))
    try:
        observed = parse_time(row.get("observed_at") or row.get("source_timestamp") or row.get("timestamp"))
        age = (now - observed).total_seconds()
        if age < -cfg.get("future_tolerance_sec", 60):
            reasons.append("future_observation")
    except (ValueError, TypeError, OverflowError):
        observed, age = None, None
        reasons.append("invalid_observation_time")
    numbers = {}
    for key in ("total_docks", "available_bikes", "available_docks"):
        try:
            value = float(row[key])
            if not math.isfinite(value) or value < 0 or not value.is_integer():
                raise ValueError(key)
            numbers[key] = int(value)
        except (KeyError, ValueError, TypeError, OverflowError):
            reasons.append("invalid_inventory")
    if any(isinstance(row.get(k), bool) for k in numbers):
        reasons.append("invalid_inventory")
    if len(numbers) == 3:
        result.update(numbers)
        total = numbers["total_docks"]
        if total <= 0 or numbers["available_bikes"] + numbers["available_docks"] > total:
            reasons.append("invalid_inventory")
        result["usage_rate"] = round(numbers["available_bikes"] / total * 100, 1) if total else 0
    if failed:
        reasons.append("upstream_unavailable")
    freshness = source if source in ("mock", "historical") else "live"
    if freshness == "live" and (reasons or age is None or age > stale_after_sec):
        freshness = "stale"
        if age is not None and age > stale_after_sec:
            reasons.append("observation_expired")
    try:
        lat, lng = float(row["lat"]), float(row["lng"])
        if not (math.isfinite(lat) and math.isfinite(lng) and -90 <= lat <= 90 and -180 <= lng <= 180):
            raise ValueError()
        result["station_key"] = f"{round(lat, 4)}_{round(lng, 4)}"
    except (KeyError, TypeError, ValueError):
        reasons.append("invalid_coordinates")
    if observed:
        result["hour"] = observed.astimezone(TAIPEI).hour
    if freshness == "live" and reasons:
        freshness = "stale"
    enabled = row.get("service_available", True) is True and row.get("status") != "offline"
    if not enabled:
        result["status"] = "offline"
    result.update(source=source, observed_at=observed.isoformat() if observed else None,
                  source_timestamp=observed.isoformat() if observed else None,
                  timestamp=observed.isoformat() if observed else None,
                  received_at=row.get("received_at"), data_freshness=freshness,
                  observation_age_sec=round(max(0, age), 1) if age is not None else None,
                  quality_reasons=sorted(set(reasons)),
                  dispatch_eligible=enabled and not reasons and freshness in ("live", "mock"))
    return result


_lock = RLock()
_series = OrderedDict()


def record(rows):
    from config_loader import get_config
    cfg = get_config().get("data_source", {})
    with _lock:
        for row in rows:
            if row.get("data_freshness") != "live" or row.get("quality_reasons"):
                continue
            key = (row["source"], row["station_id"])
            ts = parse_time(row["observed_at"])
            points = _series.setdefault(key, deque(maxlen=cfg.get("observation_max_points", 2100)))
            if not points or ts > points[-1][0]:
                points.append((ts, row["available_bikes"]))
            elif ts == points[-1][0]:
                points[-1] = (ts, row["available_bikes"])
            _series.move_to_end(key)
        while len(_series) > cfg.get("observation_max_stations", 3000):
            _series.popitem(last=False)


def recent(station):
    with _lock:
        return list(_series.get((station.get("source"), station["station_id"]), ()))


def reset():
    with _lock:
        _series.clear()
