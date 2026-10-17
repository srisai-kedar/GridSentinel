"""
test_mitre_ics.py
-----------------
Unit and integration tests for MITRE ATT&CK for ICS mapping and technique tagging.
Verifies that:
1. Simulated False Data Injection (FDI) triggers return T0856 (or T0831) tags with Impact tactic.
2. Command overrides return T0855 (Unauthorized Command Message) tags.
3. Replay attacks return T0856 tags.
4. Natural electrical faults (line trips, short circuits) and normal operation return null/None.
5. Alert payloads strictly attach MITRE ATT&CK for ICS metadata.
6. RTUVerdict models and /classifier/verdict endpoint payloads pass schema validation with mitre_ics.
"""

import pytest
from fastapi.testclient import TestClient

from app.alerts import CyberAlert, build_alert_payload, format_cyber_alert
from app.audit_store import clear_incidents
from app.main import app
from app.mitre_ics import (
    CYBER_SUBTYPE_TO_MITRE,
    MITRE_ICS_TECHNIQUES,
    MitreIcsMapping,
    get_mitre_mapping,
)
from app.ml.classifier_service import classifier_service
from app.models.schemas import RTUVerdict, VerdictResponse
from app.replay_capture import replay_capture_store


@pytest.fixture(scope="module")
def client():
    clear_incidents()
    replay_capture_store.clear()
    with TestClient(app) as test_client:
        yield test_client
    clear_incidents()
    replay_capture_store.clear()


# ---------------------------------------------------------------------------
# Unit Tests: Mapping Logic
# ---------------------------------------------------------------------------

def test_fdi_returns_correct_t0856_tag():
    """Verify simulated False Data Injection (FDI) maps to T0856 Spoof Reporting Message."""
    for subtype in ("data_injection", "silent_data_injection", "fdi", "false_data_injection"):
        mapping = get_mitre_mapping("Cyber Intrusion", subtype)
        assert mapping is not None, f"Mapping should not be None for {subtype}"
        assert mapping["technique_id"] == "T0856"
        assert mapping["technique_name"] == "Spoof Reporting Message"
        assert mapping["tactic"] == "Impact"
        assert "telemetry" in mapping["description"].lower() or "readings" in mapping["description"].lower()


def test_control_manipulation_returns_t0831_tag():
    """Verify control manipulation maps to T0831 Manipulation of Control."""
    mapping = get_mitre_mapping("Cyber Intrusion", "manipulation_of_control")
    assert mapping is not None
    assert mapping["technique_id"] == "T0831"
    assert mapping["technique_name"] == "Manipulation of Control"
    assert mapping["tactic"] == "Impair Process Control"


def test_command_override_returns_t0855_tag():
    """Verify command overrides map to T0855 Unauthorized Command Message."""
    for subtype in ("command_injection", "unauthorized_command"):
        mapping = get_mitre_mapping("Cyber Intrusion", subtype)
        assert mapping is not None
        assert mapping["technique_id"] == "T0855"
        assert mapping["technique_name"] == "Unauthorized Command Message"
        assert mapping["tactic"] == "Impair Process Control"


def test_replay_returns_t0856_tag():
    """Verify replay attacks map to T0856 Spoof Reporting Message."""
    for subtype in ("replay", "replay_attack"):
        mapping = get_mitre_mapping("Cyber Intrusion", subtype)
        assert mapping is not None
        assert mapping["technique_id"] == "T0856"
        assert mapping["technique_name"] == "Spoof Reporting Message"
        assert mapping["tactic"] == "Impact"


def test_natural_electrical_faults_return_no_cyber_tags():
    """Ensure natural electrical faults map strictly to None (no cyber technique tags)."""
    natural_fault_subtypes = [
        "line_trip",
        "short_circuit",
        "physical_fault",
        "transformer_overload",
        "sensor_anomaly",
        "cable_fault",
        None,
    ]
    for st in natural_fault_subtypes:
        mapping = get_mitre_mapping("Natural Fault", st)
        assert mapping is None, f"Natural Fault with subtype '{st}' must return None, got {mapping}"


def test_normal_operation_returns_no_cyber_tags():
    """Ensure normal operation maps strictly to None."""
    for st in ("normal", "nominal", None):
        mapping = get_mitre_mapping("Normal", st)
        assert mapping is None, f"Normal with subtype '{st}' must return None, got {mapping}"

    assert get_mitre_mapping(None) is None
    assert get_mitre_mapping("") is None


def test_cyber_classification_variants_supported():
    """Verify case-insensitive and variant names (CYBER_ATTACK, CYBER) resolve properly."""
    for cls_name in ("CYBER_ATTACK", "cyber intrusion", "Cyber Intrusion", "CYBER"):
        mapping = get_mitre_mapping(cls_name, "data_injection")
        assert mapping is not None
        assert mapping["technique_id"] == "T0856"


# ---------------------------------------------------------------------------
# Unit Tests: Alert Payload Construction
# ---------------------------------------------------------------------------

def test_build_alert_payload_cyber():
    """Verify cyber alert payload adheres to the required MITRE ATT&CK for ICS schema."""
    payload = build_alert_payload(
        event_id="evt-101",
        timestamp="2026-10-17T12:00:00Z",
        classification="CYBER_ATTACK",
        subtype="data_injection",
        rtu_id=2,
    )
    assert payload["event_id"] == "evt-101"
    assert payload["timestamp"] == "2026-10-17T12:00:00Z"
    assert payload["classification"] == "CYBER_ATTACK"
    assert payload["rtu_id"] == 2
    assert payload["mitre_ics"] is not None
    assert payload["mitre_ics"]["technique_id"] in ("T0856", "T0831")
    assert payload["mitre_ics"]["technique_name"] == "Spoof Reporting Message"
    assert payload["mitre_ics"]["tactic"] == "Impact"


def test_build_alert_payload_natural_fault():
    """Verify natural electrical fault payload explicitly contains mitre_ics: null."""
    payload = build_alert_payload(
        event_id="evt-102",
        timestamp="2026-10-17T12:00:00Z",
        classification="Natural Fault",
        subtype="line_trip",
        rtu_id=3,
    )
    assert payload["classification"] == "Natural Fault"
    assert payload["mitre_ics"] is None


def test_format_cyber_alert_pydantic_model():
    """Verify format_cyber_alert produces a valid CyberAlert schema."""
    raw = format_cyber_alert(
        event_id="alert-202",
        classification="CYBER_ATTACK",
        subtype="command_injection",
        rtu_id=4,
    )
    alert = CyberAlert(**raw)
    assert alert.event_id == "alert-202"
    assert alert.mitre_ics is not None
    assert alert.mitre_ics.technique_id == "T0855"
    assert alert.mitre_ics.technique_name == "Unauthorized Command Message"
    assert alert.mitre_ics.tactic == "Impair Process Control"


# ---------------------------------------------------------------------------
# Unit & Integration Tests: Classifier Service Inference Output
# ---------------------------------------------------------------------------

def test_classifier_predict_attaches_mitre_to_cyber_intrusion():
    """Verify classifier_service attaches mitre_ics when Cyber Intrusion (FDI or command injection) is detected."""
    from app.ml.classifier_service import ClassifierService
    svc = ClassifierService(model_path="models/does_not_exist.joblib")

    # 1. Test False Data Injection (FDI) trigger -> T0856 Spoof Reporting Message
    fdi_features = {
        "pcd_target_rtu_is_flagged": 1.0,
        "pcd_max_lnr": 4.5,
    }
    fdi_verdict = svc.predict(fdi_features)
    assert fdi_verdict["verdict"] == "Cyber Intrusion"
    assert fdi_verdict["subtype"] == "data_injection"
    assert fdi_verdict["mitre_ics"] is not None
    assert fdi_verdict["mitre_ics"]["technique_id"] in ("T0856", "T0831")
    assert fdi_verdict["mitre_ics"]["technique_name"] == "Spoof Reporting Message"
    assert fdi_verdict["mitre_ics"]["tactic"] == "Impact"

    # 2. Test Command Injection trigger -> T0855 Unauthorized Command Message
    cmd_features = {
        "nbd_unexpected_write_count": 3.0,
        "nbd_modbus_anomaly_rate": 0.40,
    }
    cmd_verdict = svc.predict(cmd_features)
    assert cmd_verdict["verdict"] == "Cyber Intrusion"
    assert cmd_verdict["subtype"] == "command_injection"
    assert cmd_verdict["mitre_ics"] is not None
    assert cmd_verdict["mitre_ics"]["technique_id"] == "T0855"
    assert cmd_verdict["mitre_ics"]["tactic"] == "Impair Process Control"


def test_classifier_predict_natural_fault_has_null_mitre():
    """Verify classifier_service leaves mitre_ics as None for Natural Faults."""
    from app.ml.classifier_service import ClassifierService
    svc = ClassifierService(model_path="models/does_not_exist.joblib")

    fault_features = {
        "pcd_status_code": 3.0,
        "pcd_chi2_failed": 1.0,
        "pcd_target_rtu_is_flagged": 0.0,
        "nbd_unexpected_write_count": 0.0,
    }
    verdict = svc.predict(fault_features)
    assert verdict["verdict"] == "Natural Fault"
    assert verdict["mitre_ics"] is None


def test_loaded_model_attaches_mitre_when_cyber_detected(monkeypatch):
    """Verify the loaded model path also attaches MITRE metadata when Cyber Intrusion probability exceeds threshold."""
    if classifier_service.is_loaded and classifier_service.top_model is not None:
        import numpy as np
        # Mock predict_proba to return high cyber probability
        def mock_predict_proba(vector):
            return np.array([[0.90, 0.05, 0.05]])
        monkeypatch.setattr(classifier_service.top_model, "predict_proba", mock_predict_proba)

        result = classifier_service.predict({})
        assert result["verdict"] == "Cyber Intrusion"
        assert result["mitre_ics"] is not None
        assert result["mitre_ics"]["technique_id"].startswith("T08")


def test_classifier_evaluate_all_rtus_schema():
    """Verify evaluate_all_rtus produces RTUVerdict-compatible dictionaries."""
    results = classifier_service.evaluate_all_rtus(
        traffic_events=[],
        state_estimation_result={},
        polled_telemetry=None,
    )
    for rtu_id, res in results.items():
        assert "mitre_ics" in res
        if res["verdict"] == "Cyber Intrusion":
            assert res["mitre_ics"] is not None
            assert res["mitre_ics"]["technique_id"].startswith("T08")
        else:
            assert res["mitre_ics"] is None


# ---------------------------------------------------------------------------
# API Integration Tests
# ---------------------------------------------------------------------------

def test_api_verdict_endpoint_includes_mitre_schema(client):
    """Verify POST /classifier/verdict responds with valid mitre_ics metadata in RTUVerdicts."""
    resp = client.post("/classifier/verdict", json={})
    assert resp.status_code == 200
    data = resp.json()
    assert "rtu_verdicts" in data
    for item in data["rtu_verdicts"]:
        # Schema validation via Pydantic model
        verdict_obj = RTUVerdict(**item)
        if verdict_obj.verdict == "Cyber Intrusion":
            assert verdict_obj.mitre_ics is not None
            assert verdict_obj.mitre_ics.technique_id in ("T0856", "T0855", "T0831", "T0814")
        else:
            assert verdict_obj.mitre_ics is None


def test_audit_incident_registration_auto_enriches_mitre(client):
    """Verify POST /audit/incidents automatically populates mitre_ics for cyber records."""
    incident = {
        "id": "audit-mitre-test-001",
        "rtu_id": 2,
        "verdict": "Cyber Intrusion",
        "subtype": "data_injection",
        "confidence": 0.94,
    }
    res = client.post("/audit/incidents", json=incident)
    assert res.status_code == 201
    stored = res.json()
    assert stored["mitre_ics"] is not None
    assert stored["mitre_ics"]["technique_id"] in ("T0856", "T0831")
    assert stored["mitre_ics"]["technique_name"] == "Spoof Reporting Message"
    assert stored["mitre_ics"]["tactic"] == "Impact"

    # PDF generation works with the MITRE row
    pdf_resp = client.get(f"/audit/{incident['id']}/report.pdf")
    assert pdf_resp.status_code == 200
    assert pdf_resp.headers["content-type"].startswith("application/pdf")
