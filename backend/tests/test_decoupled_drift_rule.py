"""Regression tests for the full live-feature drift rule with the frozen model."""

from pathlib import Path

from app.ml.classifier_service import ClassifierService, detect_sensor_drift_signature
from app.ml.feature_engineering import FEATURE_SCHEMA


def _features() -> dict[str, float]:
    return {key: 0.0 for key in FEATURE_SCHEMA}


def _drift() -> dict[str, float]:
    features = _features()
    features.update(
        pcd_target_rtu_is_flagged=1.0,
        pcd_is_target_rtu_max_lnr=1.0,
        pcd_max_lnr=3.2,
        pcd_target_rtu_v_residual=3.2,
        pcd_resid_breadth_count=1.0,
        pcd_resid_concentration=0.95,
        pcd_resid_rtu_share=0.95,
        pcd_voltage_dev_nominal=0.025,
        nbd_unexpected_write_count=0.0,
        nbd_modbus_anomaly_rate=0.0,
    )
    return features


def _fdi() -> dict[str, float]:
    features = _drift()
    features.update(pcd_voltage_dev_nominal=0.15, pcd_voltage_pu_reported=1.15)
    return features


def _natural_fault() -> dict[str, float]:
    features = _drift()
    features.update(pcd_resid_breadth_count=3.0, pcd_resid_concentration=0.40, pcd_resid_rtu_share=0.30)
    return features


def _normal() -> dict[str, float]:
    return _features()


def _production_service() -> ClassifierService:
    path = Path(__file__).parents[1] / "models" / "fusion_classifier.joblib"
    service = ClassifierService(model_path=str(path))
    assert len(service.bundle["feature_schema"]) == 28
    return service


def test_28_feature_model_uses_full_live_drift_dictionary() -> None:
    service = _production_service()
    assert detect_sensor_drift_signature(_drift()) is True
    assert service.predict(features=_drift(), rtu_id=2)["verdict"] == "Sensor Malfunction"


def test_28_feature_model_drift_rule_rejects_fdi_natural_fault_and_normal() -> None:
    service = _production_service()
    for fixture in (_fdi(), _natural_fault(), _normal()):
        assert detect_sensor_drift_signature(fixture) is False
        assert service.predict(features=fixture, rtu_id=2)["verdict"] != "Sensor Malfunction"
