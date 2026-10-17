"""
tests/test_sensor_drift_taxonomy.py
-----------------------------------
Tests for CHANGE 7: 3-Class / 4-Class Taxonomy Expansion
Verifies the complete taxonomy:
  - NORMAL (clean physics, clean network)
  - PHYSICAL_ELECTRICAL_FAULT (multi-sensor / high breadth residual, clean network)
  - SENSOR_MALFUNCTION (moderate residual strictly localized to single sensor, clean network)
  - CYBER_ATTACK (residual + network anomaly / unexpected writes / extreme falsification)

Directly validates neutralization of the judge trap:
"Is your system confusing a broken sensor wire with an active cyber attack?"
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.feeder import build_feeder
from app.core.state_estimation import (
    classify_residual_taxonomy,
    inject_sensor_drift,
)
from app.ml.classifier_service import (
    ClassifierService,
    VerdictLabel,
    classifier_service,
    evaluate_residual_disagreement,
)
from app.ml.feature_engineering import FEATURE_SCHEMA
from app.ot.scenario_injector import scenario_injector
from app.main import app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_base_features() -> dict[str, float]:
    """Return zeroed features matching FEATURE_SCHEMA."""
    return {k: 0.0 for k in FEATURE_SCHEMA}


def _make_sensor_drift_features(target_rtu: int = 2) -> dict[str, float]:
    """
    Features typical of broken sensor wire / PT calibration drift:
    - Moderate localized LNR residual (3.2 > 2.5 threshold) strictly on single sensor
    - Residual breadth count = 1 (strictly localized)
    - Target RTU flagged
    - Moderate voltage deviation (0.025 pu)
    - Zero network anomalies (no unexpected writes, zero error rate, normal reads)
    """
    feats = _make_base_features()
    feats["pcd_target_rtu_is_flagged"] = 1.0
    feats["pcd_max_lnr"] = 3.2
    feats["pcd_lnr_mean"] = 1.8
    feats["pcd_flagged_count"] = 1.0
    feats["pcd_resid_breadth_count"] = 1.0
    feats["pcd_resid_concentration"] = 0.95
    feats["pcd_voltage_deviation_pu"] = 0.025
    feats["pcd_power_flow_valid"] = 1.0
    feats["pcd_substation_v_pu"] = 1.0

    # Clean OT Modbus traffic channel
    feats["nbd_read_count"] = 25.0
    feats["nbd_write_count"] = 0.0
    feats["nbd_unexpected_write_count"] = 0.0
    feats["nbd_modbus_anomaly_rate"] = 0.0
    feats["nbd_error_rate"] = 0.0
    feats["nbd_mean_response_time_ms"] = 5.0
    return feats


def _make_physical_fault_features() -> dict[str, float]:
    """
    Features typical of a physical line trip / short circuit:
    - Multi-sensor residual spike (breadth >= 2)
    - High voltage sag across feeder
    - Clean OT Modbus network channel
    """
    feats = _make_base_features()
    feats["pcd_target_rtu_is_flagged"] = 1.0
    feats["pcd_max_lnr"] = 5.8
    feats["pcd_lnr_mean"] = 3.6
    feats["pcd_flagged_count"] = 3.0
    feats["pcd_resid_breadth_count"] = 3.0
    feats["pcd_resid_concentration"] = 0.40
    feats["pcd_voltage_deviation_pu"] = 0.065
    feats["pcd_chi2_failed"] = 1.0
    feats["pcd_power_flow_valid"] = 1.0

    # Clean OT Modbus traffic channel
    feats["nbd_read_count"] = 25.0
    feats["nbd_write_count"] = 0.0
    feats["nbd_unexpected_write_count"] = 0.0
    feats["nbd_modbus_anomaly_rate"] = 0.0
    return feats


def _make_cyber_fdi_features() -> dict[str, float]:
    """
    Features typical of cyber False Data Injection:
    - High physics residual
    - Severe falsification or network correlation
    """
    feats = _make_base_features()
    feats["pcd_target_rtu_is_flagged"] = 1.0
    feats["pcd_max_lnr"] = 6.5
    feats["pcd_voltage_deviation_pu"] = 0.15  # Fabricated 1.15 pu
    feats["pcd_chi2_failed"] = 1.0
    feats["nbd_read_count"] = 25.0
    feats["nbd_write_count"] = 0.0
    feats["nbd_unexpected_write_count"] = 0.0
    return feats


# ---------------------------------------------------------------------------
# Test Suite
# ---------------------------------------------------------------------------

class TestVerdictLabelTaxonomy:
    """Verifies VerdictLabel dual-compatibility across legacy strings and modern enums."""

    def test_verdict_label_sensor_malfunction_equality(self):
        v = VerdictLabel("Sensor Malfunction")
        assert v == "Sensor Malfunction"
        assert v == "SENSOR_MALFUNCTION"
        assert v == "SENSOR_DRIFT_OR_MALFUNCTION"
        assert v == "sensor_malfunction"
        assert v != "Cyber Intrusion"
        assert v != "CYBER_ATTACK"
        assert v != "Normal"

    def test_verdict_label_normal_equality(self):
        v = VerdictLabel("Normal")
        assert v == "Normal"
        assert v == "NORMAL"
        assert v == "NORMAL_OPERATION"
        assert v != "Sensor Malfunction"

    def test_verdict_label_natural_fault_equality(self):
        v = VerdictLabel("Natural Fault")
        assert v == "Natural Fault"
        assert v == "PHYSICAL_ELECTRICAL_FAULT"
        assert v == "PHYSICAL_FAULT"
        assert v != "Sensor Malfunction"

    def test_verdict_label_cyber_attack_equality(self):
        v = VerdictLabel("Cyber Intrusion")
        assert v == "Cyber Intrusion"
        assert v == "CYBER_ATTACK"
        assert v == "MALICIOUS_CYBER_ATTACK"
        assert v != "Sensor Malfunction"


class TestResidualDisagreementLogic:
    """
    Verifies that evaluate_residual_disagreement distinguishes
    sensor drift from physical faults and cyber attacks.
    """

    def test_sensor_drift_not_confused_with_cyber_attack(self):
        """
        Judge trap test: A single drifting sensor with clean Modbus traffic
        MUST NOT be flagged as a Cyber Attack.
        """
        feats = _make_sensor_drift_features(target_rtu=2)
        verdict, subtype, prob_dict = evaluate_residual_disagreement(feats)

        assert verdict == "SENSOR_MALFUNCTION"
        assert verdict == "Sensor Malfunction"
        assert verdict != "CYBER_ATTACK"
        assert verdict != "Cyber Intrusion"
        assert prob_dict["Sensor Malfunction"] >= 0.80
        assert "sensor" in subtype.lower() or "drift" in subtype.lower()

    def test_physical_fault_multi_sensor_breadth(self):
        """
        A physical line trip or short circuit causing diffuse multi-sensor residuals
        with clean network MUST be classified as PHYSICAL_ELECTRICAL_FAULT.
        """
        feats = _make_physical_fault_features()
        verdict, subtype, prob_dict = evaluate_residual_disagreement(feats)

        assert verdict == "PHYSICAL_ELECTRICAL_FAULT"
        assert verdict == "Natural Fault"
        assert verdict != "CYBER_ATTACK"
        assert verdict != "SENSOR_MALFUNCTION"

    def test_cyber_fdi_classified_correctly(self):
        """
        High residual with network behavioral anomaly is classified as CYBER_ATTACK.
        """
        feats = _make_cyber_fdi_features()
        feats["nbd_unexpected_write_count"] = 1.0
        verdict, subtype, prob_dict = evaluate_residual_disagreement(feats)

        assert verdict == "CYBER_ATTACK"
        assert verdict == "Cyber Intrusion"

    def test_cyber_command_injection_classified_correctly(self):
        """
        Unexpected Modbus FC 06 writes classify as CYBER_ATTACK.
        """
        feats = _make_base_features()
        feats["nbd_unexpected_write_count"] = 2.0
        feats["nbd_write_count"] = 2.0
        verdict, subtype, prob_dict = evaluate_residual_disagreement(feats)

        assert verdict == "CYBER_ATTACK"


class TestStateEstimatorResidualTaxonomy:
    """Tests the state estimation module's classify_residual_taxonomy function."""

    def test_classify_residual_single_sensor_drift(self):
        # 1 sensor exceeds LNR threshold, network clean
        residuals = [1.2, 0.8, 3.8, 0.5, 1.1]
        res = classify_residual_taxonomy(residuals, has_network_anomaly=False, lnr_threshold=3.0)
        assert res["taxonomy_class"] == "SENSOR_MALFUNCTION"

    def test_classify_residual_physical_fault(self):
        # 3 sensors exceed LNR threshold, network clean
        residuals = [3.5, 4.1, 3.8, 0.5, 1.1]
        res = classify_residual_taxonomy(residuals, has_network_anomaly=False, lnr_threshold=3.0)
        assert res["taxonomy_class"] == "PHYSICAL_ELECTRICAL_FAULT"

    def test_classify_residual_cyber_attack(self):
        # Residuals high and network anomaly present
        residuals = [0.2, 0.5, 4.0, 0.1, 0.3]
        res = classify_residual_taxonomy(residuals, has_network_anomaly=True, lnr_threshold=3.0)
        assert res["taxonomy_class"] == "CYBER_ATTACK"

    def test_classify_residual_normal(self):
        residuals = [0.5, 0.8, 1.2, 0.4, 0.9]
        res = classify_residual_taxonomy(residuals, has_network_anomaly=False, lnr_threshold=3.0)
        assert res["taxonomy_class"] == "NORMAL"


class TestScenarioInjectorSensorDrift:
    """Verifies sensor drift injection in ScenarioInjector and simulation loop."""

    def test_inject_sensor_drift_scenario(self):
        scenario_injector.clear_all_scenarios()
        res = scenario_injector.inject_sensor_drift(rtu_id=2, drift_percent=0.08, duration_ticks=5)
        assert res["status"] == "injected"
        assert res["type"] == "SENSOR_DRIFT"
        assert res["rtu_id"] == 2
        assert res["drift_percent"] == 0.08

        active = scenario_injector.get_active_scenarios()
        assert 2 in active["sensor_drifts"]
        assert active["sensor_drifts"][2] == 0.08

        # Clear scenarios
        scenario_injector.clear_all_scenarios()
        active_cleared = scenario_injector.get_active_scenarios()
        assert len(active_cleared["sensor_drifts"]) == 0


class TestFastApiSensorDriftEndpoint:
    """Verifies POST /ot/fault/sensor-drift endpoint."""

    def test_sensor_drift_endpoint(self):
        client = TestClient(app)
        scenario_injector.clear_all_scenarios()

        resp = client.post(
            "/ot/fault/sensor-drift",
            json={"rtu_id": 2, "drift_percent": 0.08, "duration_ticks": 10},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "injected"
        assert data["details"]["type"] == "SENSOR_DRIFT"
        assert data["details"]["rtu_id"] == 2

        # Cleanup
        client.post("/ot/scenario/clear")

        # Cleanup
        client.post("/ot/scenario/clear")


class TestClassifierServicePredictionWithDrift:
    """Verifies ClassifierService end-to-end prediction with sensor drift features."""

    def test_predict_returns_sensor_malfunction_verdict(self):
        svc = classifier_service
        feats = _make_sensor_drift_features(target_rtu=2)
        result = svc.predict(rtu_id=2, features=feats)

        assert result["verdict"] == "Sensor Malfunction"
        assert result["verdict"] == "SENSOR_MALFUNCTION"
        assert result["confidence"] >= 0.70
        assert "probabilities" in result
        probs = result["probabilities"]
        # Probabilities include Sensor Malfunction
        assert "Sensor Malfunction" in probs or "SENSOR_MALFUNCTION" in probs
        # Plain-language explainability evidence
        assert result.get("physics_evidence") is not None
        assert "sensor" in result.get("conclusion", "").lower() or "drift" in result.get("conclusion", "").lower()
