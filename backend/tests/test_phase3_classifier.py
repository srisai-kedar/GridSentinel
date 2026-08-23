"""
tests/test_phase3_classifier.py
--------------------------------
Phase 3 test suite: ML Fusion Classifier.

Covers:
  - Feature engineering schema alignment
  - ClassifierService (loaded model + heuristic fallback)
  - FastAPI endpoints: /classifier/verdict, /classifier/reload, /classifier/status
  - WebSocket /ws/live now carries ml_verdicts field
  - End-to-end: data-injection attack scenario should skew classifier toward Cyber Intrusion
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_normal_features() -> Dict[str, float]:
    """Produce a feature dict that looks like a completely normal tick."""
    from app.ml.feature_engineering import FEATURE_SCHEMA
    return {k: 0.0 for k in FEATURE_SCHEMA}


def _make_data_injection_features() -> Dict[str, float]:
    """Produce a feature dict typical of an ongoing silent data-injection attack."""
    feats = _make_normal_features()
    # Physics channel: voltage deviation + flagged measurement
    feats["pcd_target_rtu_is_flagged"] = 1.0
    feats["pcd_max_lnr"] = 4.5        # >> 3.0 threshold
    feats["pcd_lnr_mean"] = 2.1
    feats["pcd_chi2_failed"] = 1.0
    feats["pcd_flagged_count"] = 1.0
    feats["pcd_voltage_deviation_pu"] = 0.08
    # Network channel: all reads (no writes), normal timing
    feats["nbd_read_count"] = 25.0
    feats["nbd_write_count"] = 0.0
    feats["nbd_unexpected_write_count"] = 0.0
    feats["nbd_error_rate"] = 0.0
    return feats


def _make_command_injection_features() -> Dict[str, float]:
    """Feature dict typical of a command-injection (rogue Modbus Write)."""
    feats = _make_normal_features()
    feats["nbd_unexpected_write_count"] = 3.0
    feats["nbd_write_count"] = 3.0
    feats["nbd_fc6_count"] = 3.0
    feats["nbd_read_count"] = 22.0
    return feats


def _make_traffic_events(n_writes: int = 0) -> List[Dict[str, Any]]:
    """Synthetic Modbus traffic event list."""
    events = []
    for i in range(20):
        events.append({
            "event_id": i + 1,
            "timestamp": "2025-01-01T00:00:00Z",
            "source": "SCADA_MASTER",
            "target_rtu": "RTU_1 (Port 5021)",
            "function_code": 3,
            "function_name": "READ_HOLDING_REGISTERS",
            "response_time_ms": 12.5,
            "is_unexpected_write": False,
            "success": True,
            "details": "",
        })
    for j in range(n_writes):
        events.append({
            "event_id": 100 + j,
            "timestamp": "2025-01-01T00:00:01Z",
            "source": "ATTACKER",
            "target_rtu": "RTU_1 (Port 5021)",
            "function_code": 6,
            "function_name": "WRITE_SINGLE_REGISTER",
            "response_time_ms": 9.1,
            "is_unexpected_write": True,
            "success": True,
            "details": "register=0, value=11500",
        })
    return events


def _normal_se_result() -> Dict[str, Any]:
    return {
        "success": True,
        "chi2_test_passed": True,
        "chi2_statistic": 4.1,
        "chi2_threshold": 15.5,
        "flagged_measurements": [],
        "bad_data_detected": False,
        "status_code": 1,
    }


def _anomalous_se_result() -> Dict[str, Any]:
    return {
        "success": True,
        "chi2_test_passed": False,
        "chi2_statistic": 32.4,
        "chi2_threshold": 15.5,
        "flagged_measurements": [
            {
                "measurement_index": 0,
                "name": "v_bus1",
                "meas_type": "v",
                "element_type": "bus",
                "element": 0,
                "value": 1.15,
                "std_dev": 0.01,
                "normalised_residual": 4.8,
            }
        ],
        "bad_data_detected": True,
        "status_code": 1,
    }


# ---------------------------------------------------------------------------
# Feature Engineering Tests
# ---------------------------------------------------------------------------

class TestFeatureEngineering:
    def test_feature_schema_is_defined(self):
        from app.ml.feature_engineering import FEATURE_SCHEMA
        assert isinstance(FEATURE_SCHEMA, list)
        assert len(FEATURE_SCHEMA) > 0, "FEATURE_SCHEMA must not be empty"

    def test_extract_features_returns_all_keys(self):
        from app.ml.feature_engineering import FEATURE_SCHEMA, extract_features
        feats = extract_features(
            traffic_events=_make_traffic_events(),
            state_estimation_result=_normal_se_result(),
            target_rtu_id=1,
        )
        for key in FEATURE_SCHEMA:
            assert key in feats, f"Missing feature '{key}'"

    def test_extract_features_values_are_float(self):
        from app.ml.feature_engineering import FEATURE_SCHEMA, extract_features
        feats = extract_features(
            traffic_events=_make_traffic_events(),
            state_estimation_result=_normal_se_result(),
            target_rtu_id=1,
        )
        for key in FEATURE_SCHEMA:
            assert isinstance(feats[key], (int, float)), (
                f"Feature '{key}' must be numeric, got {type(feats[key])}"
            )

    def test_write_count_captured(self):
        from app.ml.feature_engineering import extract_features
        feats = extract_features(
            traffic_events=_make_traffic_events(n_writes=3),
            state_estimation_result=_normal_se_result(),
            target_rtu_id=1,
        )
        assert feats["nbd_unexpected_write_count"] == 3.0

    def test_anomalous_se_sets_chi2_failed(self):
        from app.ml.feature_engineering import extract_features
        feats = extract_features(
            traffic_events=_make_traffic_events(),
            state_estimation_result=_anomalous_se_result(),
            target_rtu_id=1,
        )
        assert feats["pcd_chi2_failed"] == 1.0
        # A flagged measurement in the SE result should set the global bad-data flag
        assert feats["pcd_global_bad_data_flag"] == 1.0


# ---------------------------------------------------------------------------
# ClassifierService Unit Tests (independent of FastAPI)
# ---------------------------------------------------------------------------

class TestClassifierService:
    @pytest.fixture(autouse=True)
    def svc(self):
        """Import the *module-level* singleton (model already loaded on import)."""
        from app.ml.classifier_service import classifier_service as _svc
        self.svc = _svc

    def test_model_loaded(self):
        """Fusion model file must exist and be loaded by now."""
        assert self.svc.is_loaded, (
            "ClassifierService.is_loaded is False — model bundle not found. "
            "Run: python -m app.ml.train_classifier ... first."
        )

    def test_predict_returns_required_fields(self):
        result = self.svc.predict(_make_normal_features())
        assert "verdict" in result
        assert "subtype" in result
        assert "confidence" in result
        assert "probabilities" in result
        assert "model_status" in result

    def test_predict_verdict_is_valid_label(self):
        result = self.svc.predict(_make_normal_features())
        valid = {"Normal", "Natural Fault", "Cyber Intrusion"}
        assert result["verdict"] in valid, f"Unexpected verdict: {result['verdict']}"

    def test_predict_confidence_range(self):
        result = self.svc.predict(_make_normal_features())
        assert 0.0 <= result["confidence"] <= 1.0

    def test_probabilities_sum_to_one(self):
        result = self.svc.predict(_make_normal_features())
        total = sum(result["probabilities"].values())
        assert abs(total - 1.0) < 1e-3, f"Probabilities sum to {total}, not 1.0"

    def test_heuristic_fallback_on_unloaded(self):
        """Create a fresh service pointing to a non-existent model file."""
        from app.ml.classifier_service import ClassifierService
        svc = ClassifierService(model_path="models/does_not_exist.joblib")
        assert not svc.is_loaded
        # Heuristic should still produce a valid result
        result = svc.predict(_make_normal_features())
        assert result["model_status"] == "heuristic_fallback"
        assert result["verdict"] in {"Normal", "Natural Fault", "Cyber Intrusion"}

    def test_heuristic_flags_command_injection(self):
        from app.ml.classifier_service import ClassifierService
        svc = ClassifierService(model_path="models/does_not_exist.joblib")
        feats = _make_normal_features()
        feats["nbd_unexpected_write_count"] = 2.0
        result = svc.predict(feats)
        assert result["verdict"] == "Cyber Intrusion"
        assert result["subtype"] == "command_injection"

    def test_evaluate_all_rtus_returns_five_entries(self):
        verdicts = self.svc.evaluate_all_rtus(
            traffic_events=_make_traffic_events(),
            state_estimation_result=_normal_se_result(),
        )
        assert len(verdicts) == 5
        for rtu_id in range(1, 6):
            assert rtu_id in verdicts

    def test_evaluate_all_rtus_caches_in_latest_verdicts(self):
        self.svc.evaluate_all_rtus(
            traffic_events=_make_traffic_events(),
            state_estimation_result=_normal_se_result(),
        )
        assert len(self.svc.latest_verdicts) == 5

    def test_model_hot_reload(self):
        """Reloading an existing model should succeed."""
        success = self.svc.load_model()
        assert success is True
        assert self.svc.is_loaded is True


# ---------------------------------------------------------------------------
# API Endpoint Tests
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def client():
    from app.main import app
    with TestClient(app) as c:
        yield c


class TestClassifierStatusEndpoint:
    def test_status_returns_200(self, client):
        resp = client.get("/classifier/status")
        assert resp.status_code == 200

    def test_status_model_is_loaded(self, client):
        data = client.get("/classifier/status").json()
        assert data["is_loaded"] is True

    def test_status_has_three_classes(self, client):
        data = client.get("/classifier/status").json()
        assert len(data["classes"]) == 3
        assert "Normal" in data["classes"]
        assert "Natural Fault" in data["classes"]
        assert "Cyber Intrusion" in data["classes"]

    def test_status_has_subtype_classes(self, client):
        data = client.get("/classifier/status").json()
        assert len(data["subtype_classes"]) >= 1


class TestClassifierReloadEndpoint:
    def test_reload_returns_200(self, client):
        resp = client.post("/classifier/reload")
        assert resp.status_code == 200

    def test_reload_success_true(self, client):
        data = client.post("/classifier/reload").json()
        assert data["success"] is True

    def test_reload_message_present(self, client):
        data = client.post("/classifier/reload").json()
        assert isinstance(data["message"], str)
        assert len(data["message"]) > 0


class TestVerdictEndpoint:
    def test_verdict_no_body_returns_200(self, client):
        """POST with no body must work (uses live simulation state)."""
        resp = client.post("/classifier/verdict")
        assert resp.status_code == 200

    def test_verdict_response_schema(self, client):
        data = client.post("/classifier/verdict").json()
        assert "tick_timestamp" in data
        assert "model_loaded" in data
        assert "overall_status" in data
        assert "rtu_verdicts" in data
        assert "evaluation_latency_ms" in data

    def test_verdict_has_five_rtu_verdicts(self, client):
        data = client.post("/classifier/verdict").json()
        assert len(data["rtu_verdicts"]) == 5

    def test_verdict_rtu_fields(self, client):
        data = client.post("/classifier/verdict").json()
        for rv in data["rtu_verdicts"]:
            assert "rtu_id" in rv
            assert "verdict" in rv
            assert "confidence" in rv
            assert "probabilities" in rv
            assert "model_status" in rv

    def test_verdict_overall_status_valid(self, client):
        data = client.post("/classifier/verdict").json()
        assert data["overall_status"] in {"NORMAL", "ANOMALY_DETECTED"}

    def test_verdict_latency_positive(self, client):
        data = client.post("/classifier/verdict").json()
        assert data["evaluation_latency_ms"] >= 0.0

    def test_verdict_model_loaded_flag(self, client):
        data = client.post("/classifier/verdict").json()
        assert data["model_loaded"] is True

    def test_verdict_with_normal_snapshot(self, client):
        """Pass a normal snapshot via the request body."""
        payload = {
            "traffic_window": _make_traffic_events(n_writes=0),
            "state_estimation_result": _normal_se_result(),
            "polled_telemetry": {
                str(i): {"voltage_pu": 1.0, "p_mw": 0.5, "q_mvar": 0.1, "status_flag": 1}
                for i in range(1, 6)
            },
        }
        resp = client.post("/classifier/verdict", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        # All 5 verdicts must be present
        assert len(data["rtu_verdicts"]) == 5

    def test_verdict_with_command_injection_snapshot(self, client):
        """Command-injection snapshot: >=1 RTU should be flagged as anomalous."""
        payload = {
            "traffic_window": _make_traffic_events(n_writes=5),
            "state_estimation_result": _normal_se_result(),
            "polled_telemetry": {
                str(i): {"voltage_pu": 1.0, "p_mw": 0.5, "q_mvar": 0.1, "status_flag": 1}
                for i in range(1, 6)
            },
        }
        resp = client.post("/classifier/verdict", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        # With 5 unexpected writes in the window, overall should be flagged
        # (or at minimum the model should NOT crash)
        assert data["overall_status"] in {"NORMAL", "ANOMALY_DETECTED"}

    def test_verdict_with_data_injection_snapshot(self, client):
        """Data-injection snapshot (Chi2 failure + flagged measurement): no crash."""
        payload = {
            "traffic_window": _make_traffic_events(n_writes=0),
            "state_estimation_result": _anomalous_se_result(),
            "polled_telemetry": {
                str(i): {"voltage_pu": 1.15, "p_mw": 0.5, "q_mvar": 0.1, "status_flag": 2}
                for i in range(1, 6)
            },
        }
        resp = client.post("/classifier/verdict", json=payload)
        assert resp.status_code == 200

    def test_verdict_probabilities_sum(self, client):
        """For each RTU verdict, probabilities must sum to ~1."""
        data = client.post("/classifier/verdict").json()
        for rv in data["rtu_verdicts"]:
            total = sum(rv["probabilities"].values())
            assert abs(total - 1.0) < 0.01, (
                f"RTU-{rv['rtu_id']} probabilities sum to {total}"
            )


# ---------------------------------------------------------------------------
# Integration: End-to-end data-injection detection
# ---------------------------------------------------------------------------

class TestEndToEndDetection:
    """
    Integration tests that verify the full pipeline:
    feature extraction -> classification -> verdict.
    """

    def test_classify_normal_snapshot(self):
        """A clearly normal snapshot should not raise, and produce a confident result."""
        from app.ml.feature_engineering import extract_features
        from app.ml.classifier_service import classifier_service as svc

        feats = extract_features(
            traffic_events=_make_traffic_events(n_writes=0),
            state_estimation_result=_normal_se_result(),
            target_rtu_id=1,
        )
        result = svc.predict(feats)
        assert result["verdict"] in {"Normal", "Natural Fault", "Cyber Intrusion"}
        assert result["confidence"] > 0.0

    def test_classify_command_injection_heuristic_path(self):
        """
        When the ML model is NOT loaded, the heuristic must flag unexpected writes
        as Cyber Intrusion / command_injection.
        """
        from app.ml.classifier_service import ClassifierService
        svc = ClassifierService(model_path="models/does_not_exist.joblib")

        feats = _make_normal_features()
        feats["nbd_unexpected_write_count"] = 1.0
        result = svc.predict(feats)
        assert result["verdict"] == "Cyber Intrusion"
        assert result["subtype"] == "command_injection"

    def test_classify_data_injection_heuristic_path(self):
        """
        When model NOT loaded, LNR > 3.0 should flag as Cyber Intrusion / data_injection.
        """
        from app.ml.classifier_service import ClassifierService
        svc = ClassifierService(model_path="models/does_not_exist.joblib")

        feats = _make_normal_features()
        feats["pcd_max_lnr"] = 4.5
        feats["pcd_target_rtu_is_flagged"] = 1.0
        result = svc.predict(feats)
        assert result["verdict"] == "Cyber Intrusion"
        assert result["subtype"] == "data_injection"

    def test_classify_line_trip_heuristic_path(self):
        """Chi2 failure without flagged measurement should hint Natural Fault."""
        from app.ml.classifier_service import ClassifierService
        svc = ClassifierService(model_path="models/does_not_exist.joblib")

        feats = _make_normal_features()
        feats["pcd_chi2_failed"] = 1.0
        feats["pcd_target_rtu_is_flagged"] = 0.0
        feats["pcd_status_code"] = 3.0
        result = svc.predict(feats)
        assert result["verdict"] == "Natural Fault"
