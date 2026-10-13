"""
dpn_config.py
-------------
Pre-registered configuration, feature lists, ablation arms, and decision rule
thresholds for Change 5 (Physics-Network Disagreement Feature Family).

MANDATORY PROTOCOL CONSTRAINT:
This file is committed prior to any ablation run. All thresholds, seeds,
and arm specifications are locked and pre-registered.
"""

from typing import Dict, List

# ---------------------------------------------------------------------------
# 1. DATASET SPLIT RANDOM SEEDS
# ---------------------------------------------------------------------------
TRAIN_SEED: int = 42
VAL_SEED: int = 999
SELECTION_SEED: int = 2024
TEST_SEED: int = 1337

# Model training random seeds (5 seeds per arm for mean ± std reporting)
MODEL_SEEDS: List[int] = [42, 43, 44, 45, 46]

# ---------------------------------------------------------------------------
# 2. PHYSICS RESIDUAL HYPERPARAMETERS
# ---------------------------------------------------------------------------
TAU_LOW: float = 2.0               # Persistence threshold for standardized residuals
PERSIST_WINDOW_W: int = 5           # Maximum history cap for consecutive ticks
RESID_BREADTH_THRESHOLD: float = 3.0 # Threshold for global residual breadth (3.0 sigma)
CHI2_THRESHOLD_LEGACY: float = 3.0  # Legacy chi2 normalization factor for F5

# ---------------------------------------------------------------------------
# 3. FEATURE SCHEMAS
# ---------------------------------------------------------------------------
BASE_SCHEMA_VERSION: str = "2.0.0"
NEW_SCHEMA_VERSION: str = "2.1.0"

# Base 28 features (v2.0.0)
BASE_FEATURES: List[str] = [
    # NBD features (0-9)
    "nbd_unexpected_write_count",
    "nbd_mean_response_time_ms",
    "nbd_std_response_time_ms",
    "nbd_distinct_sources_count",
    "nbd_fc3_read_count",
    "nbd_fc6_write_count",
    "nbd_fc16_write_count",
    "nbd_error_count",
    "nbd_traffic_volume",
    "nbd_modbus_anomaly_rate",
    # PCD features (10-27)
    "pcd_max_lnr",
    "pcd_is_target_rtu_max_lnr",
    "pcd_chi2_statistic",
    "pcd_chi2_ratio",
    "pcd_chi2_failed",
    "pcd_target_rtu_v_residual",
    "pcd_target_rtu_p_residual",
    "pcd_target_rtu_is_flagged",
    "pcd_global_bad_data_flag",
    "pcd_voltage_pu_reported",
    "pcd_voltage_dev_nominal",
    "pcd_p_mw_reported",
    "pcd_status_code",
    "pcd_physics_network_disagreement_index",
    "pcd_temporal_dv_dt_3tick",
    "pcd_temporal_dp_dt_3tick",
    "pcd_temporal_dq_dt_3tick",
    "pcd_cross_rtu_voltage_divergence",
]

# Change 5: 9 new features appended additively
NEW_DPN_FEATURES: List[str] = [
    "pcd_resid_jump",             # F1: max over RTU's measurements of |d_i(t) - d_i(t-1)|
    "pcd_resid_persist",          # F2: consecutive ticks capped at W=5 where max RTU |d_i| > tau_low
    "pcd_resid_concentration",    # F3: max_i |d_i| / sqrt(sum_j d_j^2) over all measurements
    "pcd_resid_rtu_share",        # F3: sum over RTU's measurements of d_i^2 / sum_j d_j^2
    "pcd_resid_breadth_count",    # F4: count of measurements with |d_j| > 3.0
    "pcd_resid_breadth_frac",     # F4: fraction of measurements with |d_j| > 3.0
    "dpn_legacy",                 # F5: (|delta P| / sigma_P) * (1 + r_max / chi2_threshold)
    "dpn_ing_delta",              # Control: |delta reported active power| / sigma_P
    "dpn_ing_resid",              # Control: 1 + r_max / chi2_threshold
]

FULL_FEATURE_SCHEMA_V2_1: List[str] = BASE_FEATURES + NEW_DPN_FEATURES

# Single-source column groupings for baseline comparison
NBD_COLUMNS: List[str] = [col for col in BASE_FEATURES if col.startswith("nbd_")]
PCD_COLUMNS: List[str] = [col for col in BASE_FEATURES if col.startswith("pcd_")]

# ---------------------------------------------------------------------------
# 4. PRE-REGISTERED ABLATION ARMS
# ---------------------------------------------------------------------------
# A0: Deployed baseline (28 features)
# A1: + F1 (jump)
# A2: + F2 (persistence)
# A3: + F3 (concentration + rtu_share)
# A4: + F4 (breadth count + frac)
# A5: + F3 + F4
# A6: + F1 + F2 + F3 + F4
# A7: + F5 (legacy composite)
# C1: + controls only (dpn_ing_delta, dpn_ing_resid)

ARMS: Dict[str, List[str]] = {
    "A0": list(BASE_FEATURES),
    "A1": BASE_FEATURES + ["pcd_resid_jump"],
    "A2": BASE_FEATURES + ["pcd_resid_persist"],
    "A3": BASE_FEATURES + ["pcd_resid_concentration", "pcd_resid_rtu_share"],
    "A4": BASE_FEATURES + ["pcd_resid_breadth_count", "pcd_resid_breadth_frac"],
    "A5": BASE_FEATURES + [
        "pcd_resid_concentration",
        "pcd_resid_rtu_share",
        "pcd_resid_breadth_count",
        "pcd_resid_breadth_frac",
    ],
    "A6": BASE_FEATURES + [
        "pcd_resid_jump",
        "pcd_resid_persist",
        "pcd_resid_concentration",
        "pcd_resid_rtu_share",
        "pcd_resid_breadth_count",
        "pcd_resid_breadth_frac",
    ],
    "A7": BASE_FEATURES + ["dpn_legacy"],
    "C1": BASE_FEATURES + ["dpn_ing_delta", "dpn_ing_resid"],
}

# ---------------------------------------------------------------------------
# 5. PRE-REGISTERED DECISION RULE THRESHOLDS
# ---------------------------------------------------------------------------
# Bootstrap resamples for paired difference testing vs A0
BOOTSTRAP_N_RESAMPLES: int = 2000

# Rule (a): delta FNR < 0 and the bootstrap 95% CI excludes 0 (upper CI < 0)
PROMOTE_FNR_DELTA_MAX: float = 0.0

# Rule (b): absolute FNR reduction is at least 3 percentage points (3.0 pp)
PROMOTE_MIN_ABS_REDUCTION_PP: float = 3.0

# Rule (c): Cyber FPR increases by no more than 0.2 pp (0.002)
# and natural-fault -> Cyber rate does not increase (delta <= 0)
PROMOTE_FPR_MAX_INCREASE_PP: float = 0.2
PROMOTE_MAX_NATURAL_FAULT_CYBER_INCREASE_PP: float = 0.0

# Rule (d): Compute budget constraints
MAX_ADDED_P99_MS: float = 2.0         # Hard budget: p99 <= 2 ms added per tick
MAX_TOTAL_INFERENCE_MS: float = 50.0   # Total feature + inference path < 50 ms

# Rule (e): Label shuffle smoke test tolerance (performance collapses toward chance)
LABEL_SHUFFLE_COLLAPSE_THRESHOLD: float = 0.35  # Cyber recall drops below 0.35 or accuracy near random
