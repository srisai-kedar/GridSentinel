"""
feature_engineering.py
----------------------
Cyber-Physical Feature Extraction for GridSentinel.

Extracts a strictly ordered, fixed-schema feature vector combining:
1. Network-Behavioral Detection (NBD) signals from Modbus TCP traffic transactions
2. Physics-Consistency Detection (PCD) signals from WLS State Estimation residuals

EXPLICIT NON-GOAL:
Never include ground-truth scenario labels or any oracle information.
Only operational signals available to a real-time SCADA security detector.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional
import numpy as np

# ---------------------------------------------------------------------------
# FIXED FEATURE SCHEMA (Exact Ordering for Training & Real-Time Inference)
# ---------------------------------------------------------------------------
FEATURE_SCHEMA: List[str] = [
    # --- NBD: Network Behavioral Features (Traffic Logger) ---
    "nbd_unexpected_write_count",       # Count of unauthorized write transactions (FC 06/16)
    "nbd_mean_response_time_ms",        # Mean latency of Modbus transactions
    "nbd_std_response_time_ms",         # Standard deviation of Modbus latency
    "nbd_distinct_sources_count",       # Unique IPs/sources communicating with target RTU
    "nbd_fc3_read_count",               # Function Code 03 (Read Holding Registers) count
    "nbd_fc6_write_count",              # Function Code 06 (Write Single Register) count
    "nbd_fc16_write_count",             # Function Code 16 (Write Multiple Registers) count
    "nbd_error_count",                  # Failed/timeout Modbus transaction count
    "nbd_traffic_volume",               # Total transaction count for target RTU in window

    # --- PCD: Physics Consistency Features (State Estimation & Power Flow) ---
    "pcd_max_lnr",                      # Global Largest Normalized Residual (LNR) across all measurements
    "pcd_is_target_rtu_max_lnr",        # 1.0 if target RTU owns the system's max residual, else 0.0
    "pcd_chi2_statistic",               # Global Chi-square (χ²) test statistic
    "pcd_chi2_ratio",                   # Ratio χ² / χ²_threshold (>1.0 indicates hypothesis rejection)
    "pcd_chi2_failed",                  # 1.0 if global χ² test failed, 0.0 if passed
    "pcd_target_rtu_v_residual",        # Normalized residual of target RTU voltage measurement
    "pcd_target_rtu_p_residual",        # Normalized residual of target RTU active power measurement
    "pcd_target_rtu_is_flagged",        # 1.0 if target RTU measurement exceeds 3.0σ threshold
    "pcd_global_bad_data_flag",         # 1.0 if global bad data detector triggered
    "pcd_voltage_pu_reported",          # Reported voltage magnitude in per-unit
    "pcd_voltage_dev_nominal",          # Absolute deviation of voltage from nominal (|V - 1.0|)
    "pcd_p_mw_reported",                # Reported active power flow in MW
    "pcd_status_code",                  # RTU hardware/trip status code (1=OK, 2=WARN, 3=TRIP)
]

# Mapping of RTU IDs to their pandapower element bindings
# RTU 1 -> Bus 1, Trafo 0
# RTU 2 -> Bus 2, Line 0
# RTU 3 -> Bus 3, Line 1
# RTU 4 -> Bus 4, Line 2
# RTU 5 -> Bus 5, Line 3
RTU_BUS_MAPPING = {1: 1, 2: 2, 3: 3, 4: 4, 5: 5}


def extract_features(
    traffic_events: List[Dict[str, Any]],
    state_estimation_result: Dict[str, Any],
    target_rtu_id: int,
    polled_telemetry: Optional[Dict[int, Dict[str, Any]]] = None,
) -> Dict[str, float]:
    """
    Extract a fixed-schema feature dictionary combining NBD and PCD metrics for a target RTU.

    Parameters
    ----------
    traffic_events : list of dict
        Recent Modbus traffic events from traffic_logger
    state_estimation_result : dict
        Output dictionary from run_state_estimation() / detect_bad_data()
    target_rtu_id : int
        RTU ID (1 to 5) to compute features for
    polled_telemetry : dict, optional
        Latest telemetry dictionary polled by SCADA Master

    Returns
    -------
    dict
        Feature dictionary guaranteed to contain exactly the keys in FEATURE_SCHEMA.
    """
    target_bus = RTU_BUS_MAPPING.get(target_rtu_id, target_rtu_id)
    target_rtu_str = f"RTU_{target_rtu_id}"
    target_rtu_dash = f"RTU-{target_rtu_id}"

    # -----------------------------------------------------------------------
    # 1. NBD: Network Behavioral Features
    # -----------------------------------------------------------------------
    rtu_events = [
        e for e in traffic_events
        if (target_rtu_str in e.get("target_rtu", "") or
            target_rtu_dash in e.get("target_rtu", "") or
            f"Port {5020 + target_rtu_id}" in e.get("target_rtu", ""))
    ]

    traffic_volume = float(len(rtu_events))
    unexpected_writes = 0.0
    fc3_count = 0.0
    fc6_count = 0.0
    fc16_count = 0.0
    error_count = 0.0
    response_times = []
    sources = set()

    for e in rtu_events:
        if e.get("is_unexpected_write", False):
            unexpected_writes += 1.0

        fc = int(e.get("function_code", 0))
        if fc == 3:
            fc3_count += 1.0
        elif fc == 6:
            fc6_count += 1.0
        elif fc in (15, 16):
            fc16_count += 1.0

        if not e.get("success", True):
            error_count += 1.0

        rt = float(e.get("response_time_ms", 0.0))
        response_times.append(rt)

        src = str(e.get("source", "UNKNOWN"))
        sources.add(src)

    mean_rt = float(np.mean(response_times)) if response_times else 0.0
    std_rt = float(np.std(response_times)) if len(response_times) > 1 else 0.0
    distinct_sources = float(len(sources))

    # -----------------------------------------------------------------------
    # 2. PCD: Physics Consistency Features
    # -----------------------------------------------------------------------
    flagged = state_estimation_result.get("flagged_measurements", [])
    chi2_stat = float(state_estimation_result.get("chi2_statistic", 0.0))
    chi2_thresh = float(state_estimation_result.get("chi2_threshold", 11.07))
    chi2_ratio = float(chi2_stat / chi2_thresh) if chi2_thresh > 0 else 0.0
    chi2_failed = 1.0 if not state_estimation_result.get("chi2_test_passed", True) else 0.0
    global_bad_data = 1.0 if state_estimation_result.get("bad_data_detected", False) or chi2_failed > 0 else 0.0

    # Residuals inspection
    max_lnr = 0.0
    max_lnr_element: Optional[int] = None
    target_v_res = 0.0
    target_p_res = 0.0
    target_is_flagged = 0.0

    for fm in flagged:
        lnr = float(fm.get("normalised_residual", 0.0))
        elem = int(fm.get("element", -1))
        elem_type = str(fm.get("element_type", "")).lower()

        if lnr > max_lnr:
            max_lnr = lnr
            max_lnr_element = elem

        # Check if this flagged measurement corresponds to our target RTU
        if elem_type == "bus" and elem == target_bus:
            target_v_res = max(target_v_res, lnr)
            target_is_flagged = 1.0
        elif elem_type in ("line", "trafo") and elem == (target_rtu_id - 1 if target_rtu_id > 1 else 0):
            target_p_res = max(target_p_res, lnr)
            target_is_flagged = 1.0

    is_target_max_lnr = 1.0 if (max_lnr_element == target_bus and max_lnr > 0.0) else 0.0

    # Telemetry values for target RTU
    reported_v = 1.0
    reported_p = 0.0
    status_code = 1.0

    if polled_telemetry and target_rtu_id in polled_telemetry:
        t = polled_telemetry[target_rtu_id]
        reported_v = float(t.get("voltage_pu", 1.0))
        reported_p = float(t.get("p_mw", 0.0))
        status_code = float(t.get("status_flag", 1.0))

    v_dev_nominal = abs(reported_v - 1.0)

    # -----------------------------------------------------------------------
    # Assemble Feature Vector strictly according to FEATURE_SCHEMA
    # -----------------------------------------------------------------------
    features = {
        "nbd_unexpected_write_count": unexpected_writes,
        "nbd_mean_response_time_ms": round(mean_rt, 3),
        "nbd_std_response_time_ms": round(std_rt, 3),
        "nbd_distinct_sources_count": distinct_sources,
        "nbd_fc3_read_count": fc3_count,
        "nbd_fc6_write_count": fc6_count,
        "nbd_fc16_write_count": fc16_count,
        "nbd_error_count": error_count,
        "nbd_traffic_volume": traffic_volume,
        "pcd_max_lnr": round(max_lnr, 4),
        "pcd_is_target_rtu_max_lnr": is_target_max_lnr,
        "pcd_chi2_statistic": round(chi2_stat, 4),
        "pcd_chi2_ratio": round(chi2_ratio, 4),
        "pcd_chi2_failed": chi2_failed,
        "pcd_target_rtu_v_residual": round(target_v_res, 4),
        "pcd_target_rtu_p_residual": round(target_p_res, 4),
        "pcd_target_rtu_is_flagged": target_is_flagged,
        "pcd_global_bad_data_flag": global_bad_data,
        "pcd_voltage_pu_reported": round(reported_v, 5),
        "pcd_voltage_dev_nominal": round(v_dev_nominal, 5),
        "pcd_p_mw_reported": round(reported_p, 5),
        "pcd_status_code": status_code,
    }

    # Verify all schema keys are present
    assert set(features.keys()) == set(FEATURE_SCHEMA), "Extracted features mismatch FEATURE_SCHEMA"

    return features


def features_to_vector(features: Dict[str, float]) -> List[float]:
    """Convert feature dictionary into ordered float array according to FEATURE_SCHEMA."""
    return [float(features[key]) for key in FEATURE_SCHEMA]
