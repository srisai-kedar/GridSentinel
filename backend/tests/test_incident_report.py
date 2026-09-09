"""Integration tests for the isolated incident PDF report feature."""

import pytest
from fastapi.testclient import TestClient

from app.audit_store import clear_incidents
from app.ml.classifier_service import classifier_service
from app.main import app
from app.replay_capture import replay_capture_store


@pytest.fixture(scope="module")
def client():
    clear_incidents()
    replay_capture_store.clear()
    with TestClient(app) as test_client:
        yield test_client
    clear_incidents()
    replay_capture_store.clear()


def test_report_pdf_returns_real_pdf_for_existing_incident(client):
    incident = {
        "id": "audit-real-incident-001",
        "timestamp": "2026-09-09T10:20:30.000Z",
        "sim_time": "10:20:30",
        "rtu_id": 2,
        "asset_name": "RTU-2 (Feeder A Industrial)",
        "verdict": "Cyber Intrusion",
        "subtype": "data_injection",
        "confidence": 0.95,
        "network_evidence": "Modbus traffic remained nominal.",
        "physics_evidence": "Reported voltage conflicts with feeder physics.",
        "conclusion": "Evidence supports silent data injection.",
        "recommended_action": "Inspect RTU sensor telemetry.",
        "formatted_alert": "RTU-2 silent data injection detected.",
    }

    registration = client.post("/audit/incidents", json=incident)
    assert registration.status_code == 201

    response = client.get("/audit/audit-real-incident-001/report.pdf")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/pdf")
    assert response.content.startswith(b"%PDF-")
    assert len(response.content) > 1000


def test_report_pdf_returns_404_for_unknown_incident(client):
    response = client.get("/audit/does-not-exist/report.pdf")
    assert response.status_code == 404


def test_report_pdf_handles_missing_optional_fields(client):
    incident = {"id": "audit-missing-fields"}
    assert client.post("/audit/incidents", json=incident).status_code == 201

    response = client.get("/audit/audit-missing-fields/report.pdf")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/pdf")
    assert response.content.startswith(b"%PDF-")


def test_triggered_incident_exposes_ordered_real_replay_window(client):
    """A live classifier tick copy becomes an ordered +/-5 incident window."""
    polled = {
        rtu_id: {"voltage_pu": 0.98, "p_mw": 0.2, "q_mvar": 0.05, "status_flag": 1}
        for rtu_id in range(1, 6)
    }
    state_estimation = {
        "chi2_test_passed": True,
        "chi2_statistic": 1.0,
        "chi2_threshold": 11.07,
        "bad_data_detected": False,
        "flagged_measurements": [],
    }

    def record_tick(tick: int) -> None:
        classifier_service.evaluate_all_rtus(
            traffic_events=[],
            state_estimation_result=state_estimation,
            polled_telemetry=polled,
            tick=tick,
            sim_time=f"08:{tick:02d}:00",
        )

    for tick in range(1, 7):
        record_tick(tick)

    incident = {
        "id": "audit-replay-incident-001",
        "rtu_id": 2,
        "verdict": "Cyber Intrusion",
        "subtype": "data_injection",
        "confidence": 0.96,
        "trigger_tick": 6,
    }
    assert client.post("/audit/incidents", json=incident).status_code == 201

    for tick in range(7, 12):
        record_tick(tick)

    replay = client.get("/audit/audit-replay-incident-001/replay")
    assert replay.status_code == 200
    window = replay.json()["replay_window"]
    assert len(window) == 11
    assert [point["tick_offset"] for point in window] == list(range(-5, 6))
    assert all(
        {"tick_offset", "voltage_pu", "p_mw", "q_mvar", "nbd", "pcd", "verdict"} <= point.keys()
        for point in window
    )
    assert "nbd_modbus_anomaly_rate" in window[0]["nbd"]
    assert "pcd_max_lnr" in window[0]["pcd"]
    assert window[5]["voltage_pu"] == 0.98
    assert window[5]["p_mw"] == 0.2
