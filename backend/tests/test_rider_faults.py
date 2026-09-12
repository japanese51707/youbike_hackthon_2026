from core.rider_faults import add_report, get_summary


def test_fault_report_adds_to_station_totals(client):
    first = client.post(
        "/api/v1/rider/fault-reports",
        json={"station_id": "S1", "station_name": "測試站", "issue": "bike", "add_quantity": 2},
    )
    assert first.status_code == 200
    assert first.json()["summary"]["bikes"] == 2
    second = client.post(
        "/api/v1/rider/fault-reports",
        json={"station_id": "S1", "issue": "bike", "add_quantity": 1},
    )
    assert second.json()["summary"]["bikes"] == 3
    listed = client.get("/api/v1/rider/fault-summaries").json()["summaries"]
    assert listed[0]["bikes"] == 3
    assert listed[0]["docks"] == 0
    assert get_summary("S1")["bikes"] == 3


def test_fault_report_does_not_require_operator(client):
    response = client.post(
        "/api/v1/rider/fault-reports",
        json={"station_id": "S2", "issue": "dock", "add_quantity": 1},
    )
    assert response.status_code == 200
    assert response.json()["dispatches"] is False
