"""
state_estimation.py
-------------------
WLS state estimation + bad-data detection for the GridSentinel feeder.

Supports populating measurement vectors from:
1. Live polled Modbus TCP telemetry (from SCADA Master / RTUs)
2. Direct power flow results with RTU-class Gaussian noise (for standalone tests)

Key design choices:
- Measurements placed at all 11kV buses (voltage magnitude), all lines
  (P and Q power flows at the from-bus end), and the substation transformer (P and Q LV side).
  This provides 18 measurements for 12 state variables (redundancy factor 1.5).
- Noise model: std_dev = 0.003 pu for voltage, 0.005 MW/MVAR for power.
- Bad-data detection: Largest Normalised Residual (LNR) test (>3.0 sigma)
  and Chi-Square (χ²) hypothesis test against the 95% confidence threshold.
"""

from typing import Any, Dict, List, Optional
import numpy as np
import pandapower as pp
import pandapower.estimation as est
from scipy.stats import chi2


# ---------------------------------------------------------------------------
# Measurement noise model (realistic RTU-class accuracy)
# ---------------------------------------------------------------------------
_VM_STD_DEV = 0.003   # pu — voltage magnitude RTU accuracy
_PQ_STD_DEV = 0.005   # MW/MVAR — power flow RTU accuracy


def add_measurements(
    net: pp.pandapowerNet,
    telemetry: Optional[Dict[int, Dict[str, Any]]] = None,
) -> None:
    """
    Add a redundant set of measurements to the pandapower network in-place.

    Parameters
    ----------
    net : pandapowerNet
    telemetry : dict, optional
        If provided, maps rtu_id -> {voltage_pu, p_mw, q_mvar, ...} polled over Modbus TCP.
        If None, measurements are seeded from the current power-flow solution + Gaussian noise.
    """
    # Clear any pre-existing measurements
    net.measurement.drop(net.measurement.index, inplace=True)

    # Ensure power flow has run to provide true base values
    if net.res_bus.empty or net.res_line.empty or net.res_trafo.empty:
        pp.runpp(net, algorithm="nr", calculate_voltage_angles=True, numba=False)

    rng = np.random.default_rng(seed=42)

    # Mapping of RTU IDs to monitored buses/elements
    # RTU 1 -> Bus 1 & Trafo 0
    # RTU 2 -> Bus 2 & Line 0
    # RTU 3 -> Bus 3 & Line 1
    # RTU 4 -> Bus 4 & Line 2
    # RTU 5 -> Bus 5 & Line 3
    bus_to_rtu = {1: 1, 2: 2, 3: 3, 4: 4, 5: 5}
    line_to_rtu = {0: 2, 1: 3, 2: 4, 3: 5}
    trafo_to_rtu = {0: 1}

    # --- Voltage magnitude measurements at all 11kV buses ------------------
    lv_buses = net.bus.index[net.bus.vn_kv == 11.0].tolist()
    for bus_idx in lv_buses:
        rtu_id = bus_to_rtu.get(bus_idx)
        if telemetry and rtu_id in telemetry and "voltage_pu" in telemetry[rtu_id]:
            v_val = float(telemetry[rtu_id]["voltage_pu"])
        else:
            true_vm = float(net.res_bus.at[bus_idx, "vm_pu"])
            noise = rng.normal(0.0, _VM_STD_DEV)
            v_val = true_vm + noise

        pp.create_measurement(
            net,
            meas_type="v",
            element_type="bus",
            value=v_val,
            std_dev=_VM_STD_DEV,
            element=bus_idx,
            name=f"vm_bus{bus_idx}",
        )

    # --- P and Q power flow measurements at each line (from-bus side) ------
    for line_idx in net.line.index:
        rtu_id = line_to_rtu.get(line_idx)
        if telemetry and rtu_id in telemetry and "p_mw" in telemetry[rtu_id] and "q_mvar" in telemetry[rtu_id]:
            p_val = float(telemetry[rtu_id]["p_mw"])
            q_val = float(telemetry[rtu_id]["q_mvar"])
        else:
            true_p = float(net.res_line.at[line_idx, "p_from_mw"])
            true_q = float(net.res_line.at[line_idx, "q_from_mvar"])
            p_val = true_p + rng.normal(0.0, _PQ_STD_DEV)
            q_val = true_q + rng.normal(0.0, _PQ_STD_DEV)

        pp.create_measurement(
            net,
            meas_type="p",
            element_type="line",
            value=p_val,
            std_dev=_PQ_STD_DEV,
            element=line_idx,
            side="from",
            name=f"p_line{line_idx}",
        )
        pp.create_measurement(
            net,
            meas_type="q",
            element_type="line",
            value=q_val,
            std_dev=_PQ_STD_DEV,
            element=line_idx,
            side="from",
            name=f"q_line{line_idx}",
        )

    # --- P and Q power flow measurements at Transformer LV side ------------
    for trafo_idx in net.trafo.index:
        rtu_id = trafo_to_rtu.get(trafo_idx)
        if telemetry and rtu_id in telemetry and "p_mw" in telemetry[rtu_id] and "q_mvar" in telemetry[rtu_id]:
            p_val = float(telemetry[rtu_id]["p_mw"])
            q_val = float(telemetry[rtu_id]["q_mvar"])
        else:
            true_p_trafo = float(net.res_trafo.at[trafo_idx, "p_lv_mw"])
            true_q_trafo = float(net.res_trafo.at[trafo_idx, "q_lv_mvar"])
            p_val = true_p_trafo + rng.normal(0.0, _PQ_STD_DEV)
            q_val = true_q_trafo + rng.normal(0.0, _PQ_STD_DEV)

        pp.create_measurement(
            net,
            meas_type="p",
            element_type="trafo",
            value=p_val,
            std_dev=_PQ_STD_DEV,
            element=trafo_idx,
            side="lv",
            name=f"p_trafo{trafo_idx}",
        )
        pp.create_measurement(
            net,
            meas_type="q",
            element_type="trafo",
            value=q_val,
            std_dev=_PQ_STD_DEV,
            element=trafo_idx,
            side="lv",
            name=f"q_trafo{trafo_idx}",
        )


def _compute_residuals_and_chi2(net: pp.pandapowerNet):
    """
    Helper function to compute physical measurement residuals r_i = z_i - h_i(x_est),
    normalised residuals r_N,i = |r_i| / sigma_i, and the Chi-square statistic.
    """
    residuals = []
    chi2_stat = 0.0

    for idx, row in net.measurement.iterrows():
        meas_type = str(row["measurement_type"]).lower()
        elem_type = str(row["element_type"]).lower()
        elem_idx = int(row["element"])
        val = float(row["value"])
        std = float(row["std_dev"])
        side = str(row.get("side", ""))

        est_val = None
        if elem_type == "bus" and meas_type == "v":
            if not net.res_bus_est.empty and elem_idx in net.res_bus_est.index:
                est_val = float(net.res_bus_est.at[elem_idx, "vm_pu"])
        elif elem_type == "line":
            if not net.res_line_est.empty and elem_idx in net.res_line_est.index:
                if meas_type == "p":
                    col = "p_from_mw" if side == "from" else "p_to_mw"
                    est_val = float(net.res_line_est.at[elem_idx, col])
                elif meas_type == "q":
                    col = "q_from_mvar" if side == "from" else "q_to_mvar"
                    est_val = float(net.res_line_est.at[elem_idx, col])
        elif elem_type == "trafo":
            if not net.res_trafo_est.empty and elem_idx in net.res_trafo_est.index:
                if meas_type == "p":
                    col = "p_lv_mw" if side == "lv" else "p_hv_mw"
                    est_val = float(net.res_trafo_est.at[elem_idx, col])
                elif meas_type == "q":
                    col = "q_lv_mvar" if side == "lv" else "q_hv_mvar"
                    est_val = float(net.res_trafo_est.at[elem_idx, col])

        if est_val is not None and not np.isnan(est_val):
            raw_residual = val - est_val
            norm_residual = abs(raw_residual) / std if std > 0 else 0.0
            chi2_stat += (raw_residual / std) ** 2
        else:
            raw_residual = 0.0
            norm_residual = 0.0

        residuals.append({
            "measurement_index": int(idx),
            "name": str(row.get("name", f"meas_{idx}")),
            "meas_type": meas_type,
            "element_type": elem_type,
            "element": elem_idx,
            "value": val,
            "std_dev": std,
            "raw_residual": raw_residual,
            "normalised_residual": round(norm_residual, 4),
        })

    # Degrees of freedom: m (measurements) - n (state variables: 2*N_buses - 1)
    num_meas = len(net.measurement)
    num_states = max(1, 2 * len(net.bus) - 1)
    dof = max(1, num_meas - num_states)
    chi2_threshold = float(chi2.ppf(0.95, df=dof))
    chi2_passed = bool(chi2_stat <= chi2_threshold)

    return residuals, chi2_passed, round(float(chi2_stat), 4), round(chi2_threshold, 4)


def run_state_estimation(net: pp.pandapowerNet) -> dict:
    """
    Run pandapower WLS state estimation and return results.
    """
    try:
        res = est.estimate(net, algorithm="wls")
        success = res.get("success", False) if isinstance(res, dict) else bool(res)
    except Exception as exc:
        return {"success": False, "error": str(exc)}

    if not success or net.res_bus_est.empty:
        return {"success": False, "error": "WLS state estimation did not converge"}

    estimated_voltages = []
    for idx, row in net.res_bus_est.iterrows():
        estimated_voltages.append(
            {
                "bus_index": int(idx),
                "name": str(net.bus.at[idx, "name"]),
                "vm_pu_est": float(row["vm_pu"]) if not np.isnan(row["vm_pu"]) else None,
                "va_degree_est": float(row["va_degree"]) if not np.isnan(row["va_degree"]) else None,
            }
        )

    _, chi2_passed, chi2_stat, chi2_thresh = _compute_residuals_and_chi2(net)

    return {
        "success": True,
        "estimated_voltages": estimated_voltages,
        "chi2_test_passed": chi2_passed,
        "chi2_statistic": chi2_stat,
        "chi2_threshold": chi2_thresh,
        "error": None,
    }


def inject_bad_data(
    net: pp.pandapowerNet,
    measurement_index: int,
    magnitude_multiplier: float,
) -> None:
    """
    Corrupt measurement at `measurement_index` by multiplying its value by
    `magnitude_multiplier`.
    """
    if measurement_index not in net.measurement.index:
        raise IndexError(
            f"Measurement index {measurement_index} not found. "
            f"Valid indices: {list(net.measurement.index)}"
        )
    original_value = net.measurement.at[measurement_index, "value"]
    net.measurement.at[measurement_index, "value"] = original_value * magnitude_multiplier


def detect_bad_data(net: pp.pandapowerNet) -> dict:
    """
    Run WLS state estimation and apply the Largest Normalised Residual (LNR) test
    and Chi-square hypothesis test to detect and identify bad data.
    """
    LNR_THRESHOLD = 3.0

    try:
        res = est.estimate(net, algorithm="wls")
        success = res.get("success", False) if isinstance(res, dict) else bool(res)
    except Exception as exc:
        return {"bad_data_detected": False, "error": str(exc)}

    if not success or net.res_bus_est.empty:
        return {
            "bad_data_detected": True,
            "flagged_measurements": [],
            "chi2_test_passed": False,
            "chi2_statistic": 9999.0,
            "chi2_threshold": 20.0,
            "lnr_threshold": LNR_THRESHOLD,
            "error": "WLS estimation failed to converge due to severe measurement corruption",
        }

    residuals, chi2_passed, chi2_stat, chi2_thresh = _compute_residuals_and_chi2(net)

    flagged = []
    for r in residuals:
        if r["normalised_residual"] > LNR_THRESHOLD:
            flagged.append({
                "measurement_index": r["measurement_index"],
                "name": r["name"],
                "meas_type": r["meas_type"],
                "element_type": r["element_type"],
                "element": r["element"],
                "value": r["value"],
                "std_dev": r["std_dev"],
                "normalised_residual": r["normalised_residual"],
            })

    bad_detected = len(flagged) > 0 or not chi2_passed

    return {
        "bad_data_detected": bad_detected,
        "flagged_measurements": flagged,
        "chi2_test_passed": chi2_passed,
        "chi2_statistic": chi2_stat,
        "chi2_threshold": chi2_thresh,
        "lnr_threshold": LNR_THRESHOLD,
        "error": None,
    }
