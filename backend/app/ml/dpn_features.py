"""
dpn_features.py
---------------
Physics-Network Disagreement (D_PN) and residual-structure feature extraction
for GridSentinel (Change 5).

Provides observable-only feature functions:
  F1: pcd_resid_jump
  F2: pcd_resid_persist
  F3: pcd_resid_concentration, pcd_resid_rtu_share
  F4: pcd_resid_breadth_count, pcd_resid_breadth_frac
  F5: dpn_legacy (control composite)
  Controls: dpn_ing_delta, dpn_ing_resid
  Evidence: build_disagreement_payload

NOTE ON RESIDUALS:
Residuals computed from pandapower WLS are standardized residuals r_i / sigma_i
(labeled as "standardized (not normalized)" because the hat-matrix diagonal
Omega_ii is not exposed by pandapower's state estimation API).
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence, Union
import numpy as np


def compute_resid_jump(
    curr_rtu_residuals: Sequence[float],
    prev_rtu_residuals: Optional[Sequence[float]] = None,
) -> float:
    """
    F1: pcd_resid_jump
    Max over the RTU's measurements of |d_i(t) - d_i(t-1)|.
    
    If prev_rtu_residuals is None or empty, returns 0.0.
    """
    if not curr_rtu_residuals or not prev_rtu_residuals:
        return 0.0
    
    min_len = min(len(curr_rtu_residuals), len(prev_rtu_residuals))
    if min_len == 0:
        return 0.0
    
    jumps = [
        abs(float(curr_rtu_residuals[i]) - float(prev_rtu_residuals[i]))
        for i in range(min_len)
    ]
    return float(max(jumps)) if jumps else 0.0


def compute_resid_persist(
    history_rtu_max_residuals: Sequence[float],
    tau_low: float = 2.0,
    window_w: int = 5,
) -> int:
    """
    F2: pcd_resid_persist
    Number of consecutive ticks ending at t, capped at window_w (default 5),
    in which the max over the RTU's measurements of |d_i| exceeds tau_low.
    
    history_rtu_max_residuals: chronological list of max |d_i| for the RTU,
    with the most recent tick at the end (index -1).
    """
    if not history_rtu_max_residuals:
        return 0
    
    consecutive = 0
    # Walk backward from the most recent tick
    for val in reversed(history_rtu_max_residuals):
        if val > tau_low:
            consecutive += 1
            if consecutive >= window_w:
                break
        else:
            break
            
    return min(consecutive, window_w)


def compute_resid_concentration(
    all_residuals: Sequence[float],
) -> float:
    """
    F3: pcd_resid_concentration
    max_i |d_i| / sqrt(sum_j d_j^2) over all measurements.
    Returns 1.0 for a single isolated outlier, lower for diffuse perturbations.
    Returns 0.0 on a zero denominator or empty input.
    """
    if not all_residuals:
        return 0.0
    
    abs_vals = [abs(float(x)) for x in all_residuals]
    max_val = max(abs_vals)
    denom = math.sqrt(sum(x * x for x in abs_vals))
    if denom <= 1e-12:
        return 0.0
    return float(max_val / denom)


def compute_resid_rtu_share(
    rtu_residuals: Sequence[float],
    all_residuals: Sequence[float],
) -> float:
    """
    F3 companion: pcd_resid_rtu_share
    sum_{i in RTU} d_i^2 / sum_j d_j^2 over all measurements.
    Returns 0.0 on a zero denominator or empty input.
    """
    if not rtu_residuals or not all_residuals:
        return 0.0
    
    rtu_sum_sq = sum(float(x) ** 2 for x in rtu_residuals)
    all_sum_sq = sum(float(x) ** 2 for x in all_residuals)
    if all_sum_sq <= 1e-12:
        return 0.0
    return float(min(1.0, max(0.0, rtu_sum_sq / all_sum_sq)))


def compute_resid_breadth(
    all_residuals: Sequence[float],
    threshold: float = 3.0,
) -> tuple[int, float]:
    """
    F4: pcd_resid_breadth
    Returns (count, fraction) of measurements with |d_j| > threshold.
    """
    if not all_residuals:
        return 0, 0.0
    
    total = len(all_residuals)
    count = sum(1 for x in all_residuals if abs(float(x)) > threshold)
    frac = float(count / total) if total > 0 else 0.0
    return count, frac


def compute_dpn_legacy(
    delta_p_reported: float,
    sigma_p: float,
    r_max: float,
    chi2_threshold: float = 3.0,
) -> tuple[float, float, float]:
    """
    F5: dpn_legacy and its two control ingredients.
    
    D_PN = (|delta reported active power| / sigma_P) * (1 + r_max / chi2_threshold)
    
    Returns:
      (dpn_legacy, dpn_ing_delta, dpn_ing_resid)
    """
    sigma_safe = max(1e-4, float(sigma_p))
    delta_ing = float(abs(delta_p_reported) / sigma_safe)
    
    thresh_safe = max(1e-4, float(chi2_threshold))
    resid_ing = float(1.0 + (max(0.0, float(r_max)) / thresh_safe))
    
    dpn = float(delta_ing * resid_ing)
    return dpn, delta_ing, resid_ing


def build_disagreement_payload(
    target_rtu_id: str,
    all_residuals: Sequence[Dict[str, Any]],
    rtu_measurements: Sequence[Dict[str, Any]],
    history_rtu_max_residuals: Optional[Sequence[float]] = None,
    tau_low: float = 2.0,
    window_w: int = 5,
    breadth_threshold: float = 3.0,
) -> Optional[Dict[str, Any]]:
    """
    Build explainable disagreement payload for the evidence panel.
    
    Identifies the RTU measurement with the largest standardized residual,
    computes physics-implied value from the estimator's fitted result,
    and returns:
      {
        "measurement": str,
        "reported_value": float,
        "physics_implied_value": float,
        "delta_sigma": float,
        "persistence_ticks": int,
        "concentration": float,
        "breadth": int,
      }
    Returns None if no measurements or estimator did not run.
    """
    if not rtu_measurements:
        return None
    
    # Find measurement with max standardized residual among RTU's measurements
    best_meas = None
    max_norm_resid = -1.0
    for m in rtu_measurements:
        norm_r = float(m.get("normalised_residual", 0.0))
        if norm_r > max_norm_resid:
            max_norm_resid = norm_r
            best_meas = m
            
    if best_meas is None:
        return None
    
    val = float(best_meas.get("value", 0.0))
    raw_r = float(best_meas.get("raw_residual", 0.0))
    # Fitted / physics-implied value = reported_value - raw_residual
    physics_implied = float(val - raw_r)
    
    # Extract all standardized residuals for concentration & breadth
    all_norm_resids = [
        float(r.get("normalised_residual", 0.0))
        for r in all_residuals
    ]
    
    concentration = compute_resid_concentration(all_norm_resids)
    breadth_count, _ = compute_resid_breadth(all_norm_resids, threshold=breadth_threshold)
    
    persist_ticks = 0
    if history_rtu_max_residuals:
        persist_ticks = compute_resid_persist(
            history_rtu_max_residuals, tau_low=tau_low, window_w=window_w
        )
    elif max_norm_resid > tau_low:
        persist_ticks = 1
        
    return {
        "measurement": str(best_meas.get("name", best_meas.get("meas_type", "unknown"))),
        "reported_value": round(val, 4),
        "physics_implied_value": round(physics_implied, 4),
        "delta_sigma": round(max_norm_resid, 2),
        "persistence_ticks": int(persist_ticks),
        "concentration": round(concentration, 4),
        "breadth": int(breadth_count),
    }
