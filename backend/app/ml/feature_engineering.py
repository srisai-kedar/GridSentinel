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
# ---------------------------------------------------------------------------
# FIXED FEATURE SCHEMA (Exact Ordering for Training & Real-Time Inference)
# ---------------------------------------------------------------------------
FEATURE_SCHEMA_VERSION: str = "2.0.0"

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
    "nbd_modbus_anomaly_rate",          # Rate of unexpected writes, anomalous FCs, and transaction errors

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
    "pcd_physics_network_disagreement_index", # Normalized Modbus-reported power delta scaled by LNR ratio
    "pcd_temporal_dv_dt_3tick",         # Rolling 3-tick window rate-of-change dV/dt
    "pcd_temporal_dp_dt_3tick",         # Rolling 3-tick window rate-of-change dP/dt
    "pcd_temporal_dq_dt_3tick",         # Rolling 3-tick window rate-of-change dQ/dt
    "pcd_cross_rtu_voltage_divergence", # Voltage difference between target RTU and electrical neighbors
]

# Mapping of RTU IDs to their pandapower element bindings
# RTU 1 -> Bus 1, Trafo 0
# RTU 2 -> Bus 2, Line 0
# RTU 3 -> Bus 3, Line 1
# RTU 4 -> Bus 4, Line 2
# RTU 5 -> Bus 5, Line 3
RTU_BUS_MAPPING = {1: 1, 2: 2, 3: 3, 4: 4, 5: 5}

# Electrical adjacency mapping for radial feeder
# Bus 1 (Substation) connects to Bus 2, Bus 3, Bus 4
# Bus 2 (Feeder A) connects to Bus 1 and Bus 5 (Feeder A2)
# Bus 3 (Feeder B) connects to Bus 1
# Bus 4 (Feeder C) connects to Bus 1
# Bus 5 (Feeder A2) connects to Bus 2
ELECTRICAL_NEIGHBORS = {
    1: [2, 3, 4],
    2: [1, 5],
    3: [1],
    4: [1],
    5: [2],
}


def extract_features(
    traffic_events: List[Dict[str, Any]],
    state_estimation_result: Dict[str, Any],
    target_rtu_id: int,
    polled_telemetry: Optional[Dict[int, Dict[str, Any]]] = None,
    telemetry_history: Optional[List[Dict[int, Dict[str, Any]]]] = None,
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
    telemetry_history : list of dict, optional
        Recent history of polled telemetry snapshots (up to 3 most recent ticks)

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

    # Candidate Feature: Modbus Anomaly Rate
    if traffic_volume > 0.0:
        modbus_anomaly_rate = (unexpected_writes * 2.0 + fc6_count + fc16_count + error_count) / traffic_volume
    else:
        modbus_anomaly_rate = 0.0
    modbus_anomaly_rate = min(10.0, float(modbus_anomaly_rate))

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
    reported_q = 0.0
    status_code = 1.0

    if polled_telemetry and target_rtu_id in polled_telemetry:
        t = polled_telemetry[target_rtu_id]
        reported_v = float(t.get("voltage_pu", 1.0))
        reported_p = float(t.get("p_mw", 0.0))
        reported_q = float(t.get("q_mvar", 0.0))
        status_code = float(t.get("status_flag", 1.0))

    v_dev_nominal = abs(reported_v - 1.0)

    # -----------------------------------------------------------------------
    # 3. Candidate Domain Features
    # -----------------------------------------------------------------------
    # a) Cross-RTU Voltage Correlation Anomaly
    neighbor_ids = ELECTRICAL_NEIGHBORS.get(target_rtu_id, [])
    neighbor_voltages = []
    if polled_telemetry:
        for nid in neighbor_ids:
            if nid in polled_telemetry:
                neighbor_voltages.append(float(polled_telemetry[nid].get("voltage_pu", 1.0)))

    if neighbor_voltages:
        neighbor_v_avg = float(np.mean(neighbor_voltages))
        cross_rtu_v_divergence = abs(reported_v - neighbor_v_avg)
    else:
        cross_rtu_v_divergence = 0.0

    # b) Temporal Telemetry Deltas over 3-tick window (dV/dt, dP/dt, dQ/dt)
    dv_dt = 0.0
    dp_dt = 0.0
    dq_dt = 0.0
    p_history = [reported_p]

    if telemetry_history and len(telemetry_history) > 1:
        v_seq = []
        p_seq = []
        q_seq = []
        for hist_snap in telemetry_history:
            if target_rtu_id in hist_snap:
                rtu_h = hist_snap[target_rtu_id]
                v_seq.append(float(rtu_h.get("voltage_pu", reported_v)))
                p_seq.append(float(rtu_h.get("p_mw", reported_p)))
                q_seq.append(float(rtu_h.get("q_mvar", reported_q)))

        if len(v_seq) >= 2:
            dt = float(len(v_seq) - 1)
            dv_dt = abs(v_seq[-1] - v_seq[0]) / dt
            dp_dt = abs(p_seq[-1] - p_seq[0]) / dt
            dq_dt = abs(q_seq[-1] - q_seq[0]) / dt
            p_history = p_seq

    # c) Physics-Network Disagreement Index
    # Normalize power delta by std, scaled by LNR relative to chi-square threshold
    p_delta = abs(p_history[-1] - p_history[0]) if len(p_history) > 1 else abs(reported_p * 0.05)
    p_std = float(np.std(p_history)) if len(p_history) > 1 else 0.02
    p_std_safe = max(0.01, p_std)
    norm_p_delta = p_delta / p_std_safe

    # Scale up when WLS largest normalized residual is high relative to bad-data threshold
    lnr_multiplier = 1.0 + (max_lnr / 3.0) * max(0.0, chi2_ratio)
    physics_net_disagreement = float(norm_p_delta * lnr_multiplier)

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
        "nbd_modbus_anomaly_rate": round(modbus_anomaly_rate, 4),
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
        "pcd_physics_network_disagreement_index": round(physics_net_disagreement, 4),
        "pcd_temporal_dv_dt_3tick": round(dv_dt, 5),
        "pcd_temporal_dp_dt_3tick": round(dp_dt, 5),
        "pcd_temporal_dq_dt_3tick": round(dq_dt, 5),
        "pcd_cross_rtu_voltage_divergence": round(cross_rtu_v_divergence, 5),
    }

    # Verify all schema keys are present
    assert set(features.keys()) == set(FEATURE_SCHEMA), f"Extracted features mismatch FEATURE_SCHEMA: missing {set(FEATURE_SCHEMA) - set(features.keys())}"

    return features


def features_to_vector(features: Dict[str, float]) -> List[float]:
    """Convert feature dictionary into ordered float array according to FEATURE_SCHEMA."""
    return [float(features[key]) for key in FEATURE_SCHEMA]
