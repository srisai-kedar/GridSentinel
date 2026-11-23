from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.ml.classifier_service import detect_sensor_drift_signature


def _features(concentration: float) -> dict[str, float]:
    return {
        "pcd_resid_breadth_count": 1.0,
        "pcd_resid_concentration": concentration,
        "pcd_resid_rtu_share": 0.9,
        "pcd_is_target_rtu_max_lnr": 1.0,
        "pcd_target_rtu_is_flagged": 1.0,
        "pcd_max_lnr": 3.0,
        "pcd_target_rtu_v_residual": 3.0,
        "pcd_voltage_dev_nominal": 0.04,
        "nbd_unexpected_write_count": 0.0,
        "nbd_modbus_anomaly_rate": 0.0,
    }


def test_drift_rule_requires_concentration_threshold():
    assert detect_sensor_drift_signature(_features(0.70)) is True
    assert detect_sensor_drift_signature(_features(0.69)) is False
