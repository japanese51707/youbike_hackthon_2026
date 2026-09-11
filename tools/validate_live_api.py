"""Read official observations and exercise the real model/API on isolated SQLite.

Run from the repo: .venv/bin/python tools/validate_live_api.py
No operational DB, source configuration file, or remote system is modified.
"""
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from time import perf_counter
import json

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))


def main():
    with TemporaryDirectory(prefix="youbike-live-check-") as tmp:
        os.environ["YOUBIKE_DB_PATH"] = str(Path(tmp) / "test.db")
        os.environ["BCRYPT_ROUNDS"] = "4"
        from config_loader import get_config
        get_config()["data_source"]["mode"] = "youbike_official"
        # Independent public station test; CWA requires a separately configured key.
        get_config()["weather"]["mode"] = "mock"
        from fastapi.testclient import TestClient
        from main import app
        from core.interfaces import LightGBMPredictor
        from db import vehicles_repo, operators_repo
        with TestClient(app) as client:
            begin = perf_counter()
            response = client.get("/api/v1/stations")
            assert response.status_code == 200, response.text
            stations = response.json()
            rec_response = client.get("/api/v1/dispatch/recommendations?limit=100")
            assert rec_response.status_code == 200, rec_response.text
            recs = rec_response.json()
            sample = next(s for s in stations if s["dispatch_eligible"])
            detail = client.get(f"/api/v1/stations/{sample['station_id']}")
            assert detail.status_code == 200, detail.text
            prediction = detail.json()["prediction"]
            assert prediction["source"] in {"lightgbm", "unavailable"}
            assert LightGBMPredictor._MODELS and len(LightGBMPredictor._MODELS) == 12
            summary = {"station_count": len(stations), "eligible_count": sum(s["dispatch_eligible"] for s in stations),
                       "recommendations": len(recs), "model_boosters": len(LightGBMPredictor._MODELS),
                       "prediction_source": prediction["source"], "prediction_status": prediction["status"],
                       "missing_features": prediction.get("missing_features"),
                       "observed_at": sample["observed_at"], "received_at": sample["received_at"],
                       "history_status": detail.json()["history_status"]["status"]}
            if recs:
                vehicles_repo.seed_default_vehicles(1, 15)
                # ADR-123：未回報車上台數的車不可確認派工；驗證流程明確宣告滿載出車。
                vehicles_repo.report_onboard("CAR-001", 15, "manual_report")
                operators_repo.seed_dispatch_operators(4)
                driver = {"X-Operator-Id": "OP-004"}
                controller = {"X-Operator-Id": "OP-002"}
                assert client.post("/api/v1/operators/me/duty", json={"status": "on_duty"}, headers=driver).status_code == 200
                response = client.post("/api/v1/dispatch/build/from-station", json={"station_id": recs[0]["station_id"],
                    "vehicle_id": "CAR-001", "operator_id": "OP-004"}, headers=controller)
                assert response.status_code == 200, response.text
                draft = response.json()
                assert draft.get("draft_id"), draft
                assert draft.get("blocking_reasons") == [], draft.get("blocking_reasons")
                summary["onboard_start"] = draft.get("onboard_start")
                summary["horizons_used"] = [e.get("horizon_used_min") for e in draft.get("load_plan", [])]
                confirmed = client.post("/api/v1/dispatch/confirm-trip", json={"draft_id": draft["draft_id"], "version": draft["version"]}, headers=controller)
                assert confirmed.status_code == 200, confirmed.text
                tid = confirmed.json()["trip_id"]
                assert client.post(f"/api/v1/dispatch/tasks/{tid}/start", headers=driver).status_code == 200
                for stop in draft["stations"]:
                    # Test reports only go to the temporary DB, never to the provider.
                    report = client.post(f"/api/v1/dispatch/tasks/{tid}/report", json={"station_id": stop["station_id"],
                        "actual_available": int(stop["target_available"])}, headers=driver)
                    assert report.status_code == 200, report.text
                assert client.get(f"/api/v1/dispatch/tasks/{tid}").json()["task_status"] == "completed"
                assert vehicles_repo.get_vehicle("CAR-001")["status"] == "available"
                summary["isolated_dispatch_lifecycle"] = "passed"
            summary["elapsed_sec"] = round(perf_counter() - begin, 2)
            print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
