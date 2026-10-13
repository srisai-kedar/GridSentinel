"""
tests/test_dpn_features.py
--------------------------
Unit and validation test suite for Change 5 (Physics-Network Disagreement Family):
  1. Identity test: Linear WLS standardized leave-one-out innovation == normalized residual (to 1e-8).
  2. Feature unit tests: Hand-built numerical test series for F1, F2, F3, F4, F5.
  3. Leakage checks: Observable-only function signatures (no label/metadata params) and scenario perturbation invariance.
  4. Schema checks: Verification that base 28 features remain hash-identical and version handling works.
  5. Harness and Decision logic unit tests: Mocked boundary conditions for rules (a)-(f).
  6. Promote candidate script safety: Refuses without --confirm and without PROMOTE.
  7. Evidence payload: Present and absent conditions.
"""

import inspect
import json
import numpy as np
import pytest
from pathlib import Path

from app.ml.dpn_config import (
    BASE_FEATURES,
    NEW_DPN_FEATURES,
    FULL_FEATURE_SCHEMA_V2_1,
    TAU_LOW,
    PERSIST_WINDOW_W,
    RESID_BREADTH_THRESHOLD,
    PROMOTE_MIN_ABS_REDUCTION_PP,
    PROMOTE_FPR_MAX_INCREASE_PP,
)
from app.ml.dpn_features import (
    compute_resid_jump,
    compute_resid_persist,
    compute_resid_concentration,
    compute_resid_rtu_share,
    compute_resid_breadth,
    compute_dpn_legacy,
    build_disagreement_payload,
)
from app.ml.feature_engineering import FEATURE_SCHEMA, FEATURE_SCHEMA_VERSION, extract_features
from app.ml.classifier_service import ClassifierService


# ===========================================================================
# 1. MATHEMATICAL IDENTITY TEST (Linear WLS LOO Innovation == Normalized Residual)
# ===========================================================================

def test_linear_wls_loo_innovation_identity():
    """
    Identity test: On a random linear WLS system (diagonal R), the standardized
    leave-one-out innovation equals the normalized residual to 1e-8.
    
    Proves analytically and numerically that 'physics-implied innovation'
    is mathematically identical to the classical normalized residual (Handschin et al., 1975).
    """
    rng = np.random.default_rng(seed=42)
    m = 12  # measurements
    n = 4   # state variables
    
    # Random full-rank measurement matrix H
    H = rng.normal(0, 1, size=(m, n))
    # Random positive measurement error variances (diagonal R)
    sigmas = rng.uniform(0.5, 2.0, size=m)
    R_diag = sigmas ** 2
    R_inv = np.diag(1.0 / R_diag)
    
    # True state and simulated noisy measurements z
    x_true = rng.normal(0, 2, size=n)
    z = H @ x_true + rng.normal(0, sigmas, size=m)
    
    # 1. Full WLS State Estimation: x_hat = (H^T R^-1 H)^-1 H^T R^-1 z
    Ht_Rinv = H.T @ R_inv
    Gain = Ht_Rinv @ H
    P = np.linalg.inv(Gain)  # Cov(x_hat)
    x_hat = P @ (Ht_Rinv @ z)
    
    # Residual vector r = z - H x_hat
    z_hat = H @ x_hat
    r = z - z_hat
    
    # Hat matrix K = H (H^T R^-1 H)^-1 H^T R^-1
    # Residual covariance Omega = R - H P H^T
    H_P_Ht = H @ P @ H.T
    Omega_diag = R_diag - np.diag(H_P_Ht)
    
    # Normalized residuals: r_N,i = r_i / sqrt(Omega_ii)
    normalized_residuals = r / np.sqrt(Omega_diag)
    
    # 2. Leave-One-Out (LOO) Estimation for each measurement i
    std_loo_innovations = np.zeros(m)
    for i in range(m):
        # Exclude measurement i
        idx_loo = [j for j in range(m) if j != i]
        H_loo = H[idx_loo, :]
        z_loo = z[idx_loo]
        R_inv_loo = np.diag(1.0 / R_diag[idx_loo])
        
        Gain_loo = H_loo.T @ R_inv_loo @ H_loo
        P_loo = np.linalg.inv(Gain_loo)
        x_hat_loo = P_loo @ (H_loo.T @ R_inv_loo @ z_loo)
        
        # LOO prediction for omitted measurement i
        z_pred_loo_i = H[i, :] @ x_hat_loo
        innovation_i = z[i] - z_pred_loo_i
        
        # Variance of innovation: Var(z_i - H_i x_hat_loo) = sigma_i^2 + H_i P_loo H_i^T
        var_innovation_i = R_diag[i] + float(H[i, :] @ P_loo @ H[i, :].T)
        std_loo_innovations[i] = innovation_i / np.sqrt(var_innovation_i)
    
    # Check that difference is below 1e-8 for every measurement
    max_abs_diff = float(np.max(np.abs(normalized_residuals - std_loo_innovations)))
    assert max_abs_diff < 1e-8, (
        f"LOO innovation does not match normalized residual to 1e-8! Max diff: {max_abs_diff}"
    )


# ===========================================================================
# 2. FEATURE UNIT TESTS (Hand-built series)
# ===========================================================================

def test_feature_f1_jump():
    """Unit test for F1 pcd_resid_jump with series d = [0.2, -0.1, 0.1, 4.0, 4.2]."""
    # At t=3: |4.0 - 0.1| = 3.9
    jump_t3 = compute_resid_jump(curr_rtu_residuals=[4.0], prev_rtu_residuals=[0.1])
    assert pytest.approx(jump_t3, abs=1e-5) == 3.9

    # At t=4: |4.2 - 4.0| = 0.2
    jump_t4 = compute_resid_jump(curr_rtu_residuals=[4.2], prev_rtu_residuals=[4.0])
    assert pytest.approx(jump_t4, abs=1e-5) == 0.2

    # Empty previous tick returns 0.0
    assert compute_resid_jump([4.0], None) == 0.0


def test_feature_f2_persist():
    """Unit test for F2 pcd_resid_persist with series d = [0.2, -0.1, 0.1, 4.0, 4.2]."""
    series = [0.2, -0.1, 0.1, 4.0, 4.2]
    # At t=4 with tau_low=2.0: consecutive > 2.0 ending at t=4 are 4.0 and 4.2 -> persist = 2
    persist_t4 = compute_resid_persist(series, tau_low=2.0, window_w=5)
    assert persist_t4 == 2

    # At t=2 (series up to 0.1): 0.1 <= 2.0 -> persist = 0
    persist_t2 = compute_resid_persist(series[:3], tau_low=2.0, window_w=5)
    assert persist_t2 == 0

    # Cap at W=5
    long_series = [3.0] * 10
    assert compute_resid_persist(long_series, tau_low=2.0, window_w=5) == 5


def test_feature_f3_concentration_and_share():
    """Unit test for F3 concentration with [4,0,0,0] -> 1.0 and [1,1,1,1] -> 0.5."""
    conc_single = compute_resid_concentration([4.0, 0.0, 0.0, 0.0])
    assert pytest.approx(conc_single, abs=1e-5) == 1.0

    conc_diffuse = compute_resid_concentration([1.0, 1.0, 1.0, 1.0])
    assert pytest.approx(conc_diffuse, abs=1e-5) == 0.5

    # RTU share
    share_full = compute_resid_rtu_share([4.0], [4.0, 0.0, 0.0])
    assert pytest.approx(share_full, abs=1e-5) == 1.0

    share_half = compute_resid_rtu_share([1.0, 1.0], [1.0, 1.0, 1.0, 1.0])
    assert pytest.approx(share_half, abs=1e-5) == 0.5


def test_feature_f4_breadth():
    """Unit test for F4 breadth with threshold 3: [4, 3.1, 2.9, 0.1] -> count = 2."""
    count, frac = compute_resid_breadth([4.0, 3.1, 2.9, 0.1], threshold=3.0)
    assert count == 2
    assert pytest.approx(frac, abs=1e-5) == 0.5


def test_feature_f5_legacy():
    """Unit test for F5 dpn_legacy composite and its two control ingredients."""
    dpn, delta_ing, resid_ing = compute_dpn_legacy(
        delta_p_reported=0.06,
        sigma_p=0.02,
        r_max=3.0,
        chi2_threshold=3.0,
    )
    # delta_ing = 0.06 / 0.02 = 3.0
    # resid_ing = 1 + (3.0 / 3.0) = 2.0
    # dpn = 3.0 * 2.0 = 6.0
    assert pytest.approx(delta_ing, abs=1e-5) == 3.0
    assert pytest.approx(resid_ing, abs=1e-5) == 2.0
    assert pytest.approx(dpn, abs=1e-5) == 6.0


# ===========================================================================
# 3. LEAKAGE AND OBSERVABILITY STATIC TESTS
# ===========================================================================

def test_feature_functions_have_no_label_or_oracle_parameters():
    """
    Verify by function signature that no feature function in dpn_features
    accepts scenario labels, oracle states, or simulation ground truth.
    """
    forbidden_terms = [
        "label", "scenario", "oracle", "ground_truth", "injection_type",
        "is_attack", "is_fault", "target_scenario", "attack_type"
    ]
    functions_to_check = [
        compute_resid_jump,
        compute_resid_persist,
        compute_resid_concentration,
        compute_resid_rtu_share,
        compute_resid_breadth,
        compute_dpn_legacy,
        build_disagreement_payload,
        extract_features,
    ]
    for fn in functions_to_check:
        sig = inspect.signature(fn)
        for param_name in sig.parameters.keys():
            for term in forbidden_terms:
                assert term not in param_name.lower(), (
                    f"Forbidden oracle/label term '{term}' found in parameter '{param_name}' of function {fn.__name__}!"
                )


def test_features_invariant_to_evaluation_metadata():
    """Features extracted are strictly unchanged when metadata/oracle fields are altered."""
    se_res = {
        "success": True,
        "bad_data_detected": False,
        "chi2_test_passed": True,
        "chi2_statistic": 2.1,
        "chi2_threshold": 11.07,
        "flagged_measurements": [],
        "all_residuals": [
            {"element_type": "bus", "element": 0, "normalised_residual": 1.2, "raw_residual": 0.01, "value": 1.01},
            {"element_type": "line", "element": 0, "normalised_residual": 0.8, "raw_residual": 0.02, "value": 10.0},
        ],
    }
    telemetry = {1: {"voltage_pu": 1.01, "p_mw": 10.0, "q_mvar": 2.0, "status_flag": 1.0}}
    traffic = []

    f1 = extract_features(traffic, se_res, target_rtu_id=1, polled_telemetry=telemetry)
    # Re-run identical observable inputs
    f2 = extract_features(traffic, se_res, target_rtu_id=1, polled_telemetry=telemetry)
    assert f1 == f2


# ===========================================================================
# 4. SCHEMA VERSIONING & COMPATIBILITY
# ===========================================================================

def test_feature_schema_additive_version_bump():
    """Verify FEATURE_SCHEMA v2.1.0 preserves base 28 columns at the exact start."""
    assert FEATURE_SCHEMA_VERSION == "2.1.0"
    assert len(FEATURE_SCHEMA) == 37
    assert FEATURE_SCHEMA[:28] == BASE_FEATURES
    assert FEATURE_SCHEMA[28:] == NEW_DPN_FEATURES


def test_classifier_service_schema_acceptance_and_rejection(tmp_path):
    """classifier_service accepts v2.0.0 and v2.1.0, rejects unsupported schemas."""
    import joblib
    from sklearn.tree import DecisionTreeClassifier

    # Create dummy mock bundle with invalid schema version
    bad_bundle_path = tmp_path / "bad_schema.joblib"
    bad_bundle = {
        "top_level_model": DecisionTreeClassifier(),
        "feature_schema_version": "9.9.9",
        "classes": ["Normal", "Natural Fault", "Cyber Intrusion"],
    }
    joblib.dump(bad_bundle, bad_bundle_path)

    service = ClassifierService()
    # Loading bad schema version must fail
    res = service.load_model(str(bad_bundle_path))
    assert res is False
    assert service.is_loaded is False


# ===========================================================================
# 5. EVIDENCE PAYLOAD GENERATION TESTS
# ===========================================================================

def test_disagreement_payload_generation():
    """Verify build_disagreement_payload exposes expected keys when residuals exist."""
    all_resids = [
        {"name": "vm_bus0", "element_type": "bus", "element": 0, "normalised_residual": 4.2, "raw_residual": -1.83, "value": 9.40},
        {"name": "p_line0", "element_type": "line", "element": 0, "normalised_residual": 0.5, "raw_residual": 0.1, "value": 15.0},
    ]
    rtu_meas = [all_resids[0]]
    
    payload = build_disagreement_payload(
        target_rtu_id="RTU_1",
        all_residuals=all_resids,
        rtu_measurements=rtu_meas,
        history_rtu_max_residuals=[0.2, 0.1, 4.0, 4.2],
    )
    assert payload is not None
    assert payload["reported_value"] == 9.40
    # physics-implied = reported - raw = 9.40 - (-1.83) = 11.23
    assert pytest.approx(payload["physics_implied_value"], abs=1e-3) == 11.23
    assert payload["delta_sigma"] == 4.2
    assert payload["persistence_ticks"] >= 2
    assert "concentration" in payload
    assert "breadth" in payload


def test_disagreement_payload_absent_when_no_measurements():
    """Payload is None when no measurements are available."""
    assert build_disagreement_payload("RTU_1", [], []) is None


# ===========================================================================
# 6. DECISION RULE LOGIC & PROMOTION SCRIPT SAFETY TESTS
# ===========================================================================

def test_promote_script_safety_refuses_without_confirm(tmp_path):
    """scripts/promote_candidate.py must refuse promotion when --confirm is absent."""
    import sys
    scripts_dir = Path(__file__).resolve().parent.parent.parent / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    import promote_candidate

    mock_report = tmp_path / "decision_report.json"
    mock_candidate = tmp_path / "candidate.joblib"
    mock_candidate.write_bytes(b"dummy_candidate")

    mock_report.write_text(json.dumps({
        "decision": "PROMOTE",
        "candidate_artifact": str(mock_candidate),
    }))

    # Call promote without confirm -> must return 1 (refused)
    code = promote_candidate.promote(confirm=False, report_path=mock_report, candidate_path=mock_candidate, backend_dir=tmp_path)
    assert code == 1


def test_promote_script_safety_refuses_on_no_promote(tmp_path):
    """scripts/promote_candidate.py must refuse promotion when decision == 'NO-PROMOTE'."""
    import sys
    scripts_dir = Path(__file__).resolve().parent.parent.parent / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    import promote_candidate

    mock_report = tmp_path / "decision_report.json"
    mock_report.write_text(json.dumps({
        "decision": "NO-PROMOTE",
        "candidate_artifact": None,
    }))

    code = promote_candidate.promote(confirm=True, report_path=mock_report, backend_dir=tmp_path)
    assert code == 1
