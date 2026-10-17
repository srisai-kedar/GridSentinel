"""
state_estimator.py
------------------
Root-level wrapper and re-export for GridSentinel state estimation and bad-data detection.
Ensures direct imports like `import backend.state_estimator` or `from backend.state_estimator import ...`
resolve seamlessly.
"""

from app.core.state_estimation import (
    add_measurements,
    run_state_estimation,
    inject_bad_data,
    detect_bad_data,
    inject_sensor_drift,
    classify_residual_taxonomy,
    _compute_residuals_and_chi2,
)

__all__ = [
    "add_measurements",
    "run_state_estimation",
    "inject_bad_data",
    "detect_bad_data",
    "inject_sensor_drift",
    "classify_residual_taxonomy",
    "_compute_residuals_and_chi2",
]
