"""ADR-121: transform observations using immutable statistics from model training."""
from datetime import timedelta
from hashlib import sha256
import json
import math
from pathlib import Path
import numpy as np
from core.data.observations import parse_time, recent, TAIPEI


class PredictionUnavailable(NotImplementedError):
    pass


def model_fingerprint(model_dir):
    paths = [model_dir / "meta.json", *sorted(model_dir.glob("model_*_p*.txt"))]
    digest = sha256()
    for path in paths:
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def load_bundle(model_dir, feature_cols):
    path = model_dir / "serving_features.json"
    try:
        bundle = json.loads(path.read_text())
        if (bundle["schema_version"] != 1 or bundle["feature_cols"] != feature_cols
                or bundle["model_fingerprint"] != model_fingerprint(model_dir)):
            raise ValueError("model and feature bundle mismatch")
        return bundle
    except (OSError, ValueError, KeyError) as exc:
        raise PredictionUnavailable("模型特徵包缺失或與模型版本不符") from exc


def station_key(station):
    return f"{round(float(station['lat']), 4)}_{round(float(station['lng']), 4)}"


def transform(station, bundle, observations=None):
    """No fitting, no archive lookups, no network; lags never select future data."""
    from config_loader import get_config
    cfg = get_config().get("serving", {})
    columns = bundle["feature_cols"]
    row = {name: np.nan for name in columns}
    try:
        asof = parse_time(station.get("observed_at") or station.get("source_timestamp") or station.get("timestamp")).astimezone(TAIPEI)
        key = station_key(station)
    except (ValueError, TypeError, KeyError) as exc:
        raise PredictionUnavailable("預測缺少有效觀測時間或座標") from exc
    if station.get("data_freshness") in ("stale", "historical") or not station.get("service_available", True):
        raise PredictionUnavailable("過期、歷史或停用站點不提供即時預測")
    for name in ("available_bikes", "available_docks", "total_docks"):
        row[name] = float(station[name])
    # Calendar is packaged with the model; no online calendar refresh during serving.
    datekey = asof.strftime("%Y%m%d")
    calendar = bundle.get("dayoff", {})
    dayoff = calendar.get(datekey)
    row.update(hour=asof.hour, weekday=asof.weekday(), month=asof.month,
               time_slot=asof.hour * 2 + int(asof.minute >= 30))
    row["is_weekend"] = float(dayoff) if dayoff is not None else np.nan
    frozen = bundle.get("stations", {}).get(key, {})
    row.update(frozen.get("features", {}))
    if dayoff is not None:
        row["station_slot_p50"] = frozen.get("slots", {}).get(f"{int(dayoff)}:{row['time_slot']}", np.nan)
    points = observations if observations is not None else recent(station)
    tolerance = timedelta(minutes=cfg.get("lag_tolerance_minutes", 5))
    for name, minutes in (("lag_30min", 30), ("lag_1hr", 60), ("lag_2hr", 120),
                          ("lag_1day", 1440), ("lag_1week", 10080)):
        target = asof - timedelta(minutes=minutes)
        candidates = [(parse_time(ts), value) for ts, value in points
                      if target - tolerance <= parse_time(ts) <= target]
        if candidates:
            row[name] = max(candidates, key=lambda p: p[0])[1]
    row["change_1hr"] = row["available_bikes"] - row["lag_1hr"]
    row["change_2hr"] = row["available_bikes"] - row["lag_2hr"]
    # Only accept explicitly timestamped observed weather from the trusted adapter.
    weather = station.get("weather_features", {})
    try:
        weather_time = parse_time(weather["observed_at"])
        if weather.get("source") == "cwa" and timedelta(0) <= asof - weather_time <= timedelta(minutes=cfg.get("weather_max_age_minutes", 30)):
            for name in ("temperature", "humidity", "wind_speed", "temp_comfort", "rain_level"):
                row[name] = weather.get(name, np.nan)
    except (KeyError, ValueError, TypeError):
        pass
    values = []
    for name in columns:
        try:
            value = float(row.get(name, np.nan))
        except (ValueError, TypeError):
            value = np.nan
        values.append(value if math.isfinite(value) else np.nan)
    missing = [name for name, value in zip(columns, values) if not math.isfinite(value)]
    return np.asarray([values], dtype=float), {
        "status": "degraded" if missing else "ready", "missing_features": missing,
        "predict_from": asof.isoformat(), "model_version": bundle["model_fingerprint"],
    }


def export_frame(frame, feature_cols):
    """Extract the actual fitted columns, without recomputing their statistics."""
    import pandas as pd
    names = [c for c in feature_cols if c.startswith(("prof_", "dist_", "terrain_")) or c == "area_type_code"]
    result = {}
    for key, group in frame.groupby("station_key", sort=False):
        features = {c: float(group[c].iloc[0]) if pd.notna(group[c].iloc[0]) and np.isfinite(group[c].iloc[0]) else None for c in names}
        slots = group[["is_weekend", "time_slot", "station_slot_p50"]].drop_duplicates(["is_weekend", "time_slot"])
        entry = {"features": features, "slots": {
            f"{int(r.is_weekend)}:{int(r.time_slot)}": float(r.station_slot_p50) if pd.notna(r.station_slot_p50) and np.isfinite(r.station_slot_p50) else None
            for r in slots.itertuples()}}
        # ADR-126：未觸底時的同時段流量（估計被壓抑的需求用）。欄位不存在的舊管線自動略過。
        demand_cols = ["is_weekend", "time_slot", "slot_outflow_p50", "slot_inflow_p50", "slot_uncensored_n"]
        if all(c in group.columns for c in demand_cols):
            rows = group[demand_cols].drop_duplicates(["is_weekend", "time_slot"])
            entry["demand"] = {
                f"{int(r.is_weekend)}:{int(r.time_slot)}": {
                    "out": float(r.slot_outflow_p50) if pd.notna(r.slot_outflow_p50) and np.isfinite(r.slot_outflow_p50) else None,
                    "in": float(r.slot_inflow_p50) if pd.notna(r.slot_inflow_p50) and np.isfinite(r.slot_inflow_p50) else None,
                    "n": int(r.slot_uncensored_n) if pd.notna(r.slot_uncensored_n) else 0,
                } for r in rows.itertuples()}
        result[str(key)] = entry
    return result


def unconstrained_demand(station, bundle, action):
    """ADR-126：估計被物理邊界壓抑的真實需求（站內自比，不跨站外推）。

    只有在站點觸底（補車時空站／取車時滿站）才給估計；站況正常時觀測本身沒被壓抑，回 None。
    樣本不足時回 (None, "insufficient_samples")——不得在樣本不足時給看起來很確定的數字。
    回 (值或 None, 依據字串)。
    """
    from config_loader import get_config
    cfg = get_config()
    if not cfg.get("prediction", {}).get("輸出未受限需求估計", False):
        return None, None
    available = float(station.get("available_bikes", 0) or 0)
    docks = float(station.get("available_docks", 0) or 0)
    at_empty, at_full = available <= 0, docks <= 0
    if not ((action == "補車" and at_empty) or (action == "取車" and at_full)):
        return None, "not_censored"
    try:
        key = station_key(station)
        asof = parse_time(station.get("observed_at") or station.get("timestamp")).astimezone(TAIPEI)
    except (ValueError, TypeError, KeyError):
        return None, "insufficient_samples"
    dayoff = bundle.get("dayoff", {}).get(asof.strftime("%Y%m%d"))
    if dayoff is None:
        return None, "insufficient_samples"
    slot = asof.hour * 2 + int(asof.minute >= 30)
    entry = bundle.get("stations", {}).get(key, {}).get("demand", {}).get(f"{int(dayoff)}:{slot}")
    minimum = cfg.get("prediction", {}).get("需求估計最小樣本數", 8)
    if not entry or entry.get("n", 0) < minimum:
        return None, "insufficient_samples"
    value = entry.get("out") if action == "補車" else entry.get("in")
    if value is None or not math.isfinite(value):
        return None, "insufficient_samples"
    return round(float(value), 1), "station_slot_uncensored"


def save_bundle(model_dir, feature_cols, stations, train_start, train_end, provenance):
    from features.calendar_holiday import get_holiday_feature, _CACHE_PATH
    if not _CACHE_PATH.exists():
        raise FileNotFoundError("需既有官方月曆快取，匯出不自動抓取外部資料")
    import pandas as pd
    cached = json.loads(_CACHE_PATH.read_text())
    last_year = max(int(date[:4]) for date in cached)
    first_year = int(str(train_start)[:4])
    if int(str(train_end)[:4]) > last_year:
        raise ValueError("官方月曆快取未涵蓋訓練期間")
    calendar = {d.strftime("%Y%m%d"): int(get_holiday_feature(d.strftime("%Y%m%d"))["is_holiday"])
                for d in pd.date_range(f"{first_year}-01-01", f"{last_year}-12-31")}
    bundle = {"schema_version": 1, "feature_cols": feature_cols,
              "model_fingerprint": model_fingerprint(model_dir),
              "train_start": train_start, "train_end": train_end, "provenance": provenance,
              "dayoff": calendar, "stations": stations}
    path = model_dir / "serving_features.json"
    pending = path.with_suffix(".tmp")
    pending.write_text(json.dumps(bundle, ensure_ascii=False, allow_nan=False, separators=(",", ":")))
    pending.replace(path)
    return path


def observed_weather(station):
    """Adapter values retain their own clocks; unavailable weather stays missing."""
    from core.data.weather_source import get_weather_source
    from features.weather import _temp_comfort
    from config_loader import get_config
    max_age = get_config().get("serving", {}).get("weather_max_age_minutes", 30)
    src = get_weather_source()
    if src.name != "cwa":
        return {}
    try:
        wx = src.get_weather_by_location(station["lat"], station["lng"]) or {}
        rain = src.get_rainfall_by_location(station["lat"], station["lng"]) or {}
        asof = parse_time(station.get("observed_at") or station.get("timestamp"))
        result = {"source": "cwa", "observed_at": wx.get("observed_at")}
        for target, origin, lo, hi in (("temperature", "temperature_c", -50, 60),
                                       ("humidity", "humidity", 0, 100), ("wind_speed", "wind_speed", 0, 100)):
            value = wx.get(origin)
            if isinstance(value, (int, float)) and math.isfinite(value) and lo <= value <= hi:
                result[target] = value
        if "temperature" in result:
            result["temp_comfort"] = _temp_comfort(result["temperature"])
        age = asof - parse_time(rain.get("observed_at"))
        precipitation = rain.get("past1hr")
        if (timedelta(0) <= age <= timedelta(minutes=max_age) and isinstance(precipitation, (int, float))
                and math.isfinite(precipitation) and precipitation >= 0):
            result["rain_level"] = 0 if precipitation == 0 else 1 if precipitation < 5 else 2 if precipitation < 15 else 3
        return result
    except (RuntimeError, ValueError, TypeError, KeyError):
        return {}
