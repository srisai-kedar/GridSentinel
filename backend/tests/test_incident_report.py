"""Integration tests for the isolated incident PDF report feature."""

import pytest
from fastapi.testclient import TestClient

from app.audit_store import clear_incidents
from app.main import app


@pytest.fixture(scope="module")
def client():
    clear_incidents()
    with TestClient(app) as test_client:
        yield test_client
    clear_incidents()


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
