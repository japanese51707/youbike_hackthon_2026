"""ADR-121: model feature parity, clocks, missingness and artifact identity."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
from copy import deepcopy
import json
import numpy as np
import pandas as pd
import pytest
from prediction.serving_features import transform, load_bundle, PredictionUnavailable, export_frame
from prediction.feature_pipeline import build_training_frame
from core.data.observations import record, recent, reset


def fixture_bundle():
    columns = ["lag_30min", "lag_1hr", "lag_2hr", "lag_1day", "lag_1week", "change_1hr", "change_2hr",
               "available_bikes", "available_docks", "total_docks", "hour", "weekday", "is_weekend", "month", "time_slot", "station_slot_p50"]
    return {"feature_cols": columns, "model_fingerprint": "test", "dayoff": {"20260911": 0},
            "stations": {"25.01_121.46": {"features": {}, "slots": {"0:20": 4.5}}}}


def snapshot():
    return {"station_id": "S1", "lat": 25.01, "lng": 121.46,
            "available_bikes": 12, "available_docks": 8, "total_docks": 20,
            "observed_at": "2026-09-11T10:05:00+08:00", "source": "youbike_official", "data_freshness": "live"}


def test_lags_use_real_clock_and_never_bridge_june_to_september():
    bundle = fixture_bundle()
    points = [("2026-06-30T23:30:00+08:00", 99), ("2026-09-11T09:35:00+08:00", 7),
              ("2026-09-11T09:36:00+08:00", 100), ("2026-09-11T09:05:00+08:00", 5)]
    X, quality = transform(snapshot(), bundle, points)
    row = dict(zip(bundle["feature_cols"], X[0]))
    assert row["lag_30min"] == 7 and row["lag_1hr"] == 5
    assert row["change_1hr"] == 7
    assert np.isnan(row["lag_2hr"]) and np.isnan(row["lag_1week"])
    assert row["station_slot_p50"] == 4.5
    assert quality["predict_from"] == "2026-09-11T10:05:00+08:00"
    assert quality["status"] == "degraded" and "lag_1week" in quality["missing_features"]


def test_runtime_does_not_fit_training_statistics(monkeypatch):
    monkeypatch.setattr("prediction.feature_pipeline.build_training_frame", lambda *a, **k: pytest.fail("runtime fitted training statistics"))
    _, quality = transform(snapshot(), fixture_bundle(), [])
    assert quality["status"] == "degraded"


def test_source_isolation_and_duplicate_snapshot_memory():
    reset()
    row = snapshot()
    record([row, row])
    assert len(recent(row)) == 1
    assert recent({**row, "source": "tdx"}) == []
    assert recent({**row, "station_id": "S2"}) == []


def test_missing_or_wrong_model_bundle_is_rejected(tmp_path):
    with pytest.raises(PredictionUnavailable): load_bundle(tmp_path, ["hour"])
    (tmp_path / "serving_features.json").write_text(json.dumps({"schema_version": 1, "feature_cols": ["hour"], "model_fingerprint": "wrong"}))
    (tmp_path / "meta.json").write_text("{}")
    with pytest.raises(PredictionUnavailable): load_bundle(tmp_path, ["hour"])


def test_frozen_statistics_match_training_frame(monkeypatch):
    # Independent short station history; compare fitted columns on a held point.
    monkeypatch.setattr("features.calendar_holiday.get_holiday_feature", lambda date: {"is_holiday": False})
    dates = pd.date_range("2026-09-10", periods=72, freq="30min")
    raw = pd.DataFrame({"場站名稱": "S1", "日期": dates, "可借車數": [i % 10 + 3 for i in range(72)],
                        "可還位數": [17 - i % 10 for i in range(72)], "總車柱數": 20, "緯度": 25.01, "經度": 121.46})
    frame, columns = build_training_frame(raw, "2026-09-11", with_profile=True)
    bundle = {"feature_cols": columns, "model_fingerprint": "test", "dayoff": {"20260911": 0},
              "stations": export_frame(frame, columns)}
    target = frame.iloc[68]
    st = {**snapshot(), "observed_at": str(target["dt"]), "available_bikes": int(target.available_bikes),
          "available_docks": int(target.available_docks)}
    points = [(str(r.dt), r.available_bikes) for r in frame.iloc[:68].itertuples()]
    X, _ = transform(st, bundle, points)
    np.testing.assert_allclose(X[0], target[columns].astype(float), equal_nan=True)


def test_packaged_model_features_match_and_run_real_boosters():
    from core.interfaces import LightGBMPredictor
    pred = LightGBMPredictor()
    bundle = pred._BUNDLE
    assert bundle["provenance"]["reconstructed_rows"] == 13340606
    assert len(bundle["stations"]) == 1579
    key = next(iter(bundle["stations"]))
    lat, lng = map(float, key.split("_"))
    row = {**snapshot(), "lat": lat, "lng": lng}
    X, quality = transform(row, bundle, [])
    assert X.shape == (1, 45)
    assert quality["status"] == "degraded"
    for model in pred._MODELS.values():
        assert np.isfinite(model.predict(X, num_threads=1)[0])


def test_crossed_quantiles_do_not_become_valid_intervals(monkeypatch):
    from core.interfaces import LightGBMPredictor
    class Booster:
        def __init__(self, value): self.value = value
        def predict(self, *a, **k): return [self.value]
    monkeypatch.setattr(LightGBMPredictor, "_MODELS", {(30, q): Booster(v) for q, v in [("p10", 5), ("p50", 0), ("p90", 3)]})
    monkeypatch.setattr(LightGBMPredictor, "_META", {"horizons": [30]})
    monkeypatch.setattr(LightGBMPredictor, "_BUNDLE", fixture_bundle())
    monkeypatch.setattr(LightGBMPredictor, "_CACHE", {})
    with pytest.raises(PredictionUnavailable, match="分位數"):
        LightGBMPredictor().predict_multi(snapshot())
