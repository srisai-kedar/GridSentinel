"""T1 post-training leakage re-evaluation and lens ablation.

All thresholds are selected on validation data. The test file is scored once.
This script never writes the production model.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import (
    average_precision_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
    roc_curve,
)


NBD = [
    "nbd_unexpected_write_count", "nbd_mean_response_time_ms", "nbd_std_response_time_ms",
    "nbd_distinct_sources_count", "nbd_fc3_read_count", "nbd_fc6_write_count",
    "nbd_fc16_write_count", "nbd_error_count", "nbd_traffic_volume", "nbd_modbus_anomaly_rate",
]
PCD = [
    "pcd_max_lnr", "pcd_is_target_rtu_max_lnr", "pcd_chi2_statistic", "pcd_chi2_ratio",
    "pcd_chi2_failed", "pcd_target_rtu_v_residual", "pcd_target_rtu_p_residual",
    "pcd_target_rtu_is_flagged", "pcd_global_bad_data_flag", "pcd_voltage_pu_reported",
    "pcd_voltage_dev_nominal", "pcd_p_mw_reported", "pcd_status_code",
    "pcd_physics_network_disagreement_index", "pcd_temporal_dv_dt_3tick",
    "pcd_temporal_dp_dt_3tick", "pcd_temporal_dq_dt_3tick", "pcd_cross_rtu_voltage_divergence",
    "pcd_resid_jump", "pcd_resid_persist", "pcd_resid_concentration", "pcd_resid_rtu_share",
    "pcd_resid_breadth_count", "pcd_resid_breadth_frac", "dpn_legacy", "dpn_ing_delta",
    "dpn_ing_resid",
]
FIXED_FPR = 0.01


def _fit_score(train: pd.DataFrame, test: pd.DataFrame, features: list[str]):
    primary = train[train.top_level_label != "Sensor Malfunction"].copy()
    y = (primary.top_level_label == "Cyber Intrusion").astype(int)
    model = __import__("sklearn.pipeline", fromlist=["make_pipeline"]).make_pipeline(
        SimpleImputer(strategy="median"),
        RandomForestClassifier(n_estimators=200, class_weight="balanced_subsample", random_state=42, n_jobs=-1),
    )
    model.fit(primary[features], y)
    return model.predict_proba(test[features])[:, 1]


def _threshold_at_fpr(y_val: np.ndarray, s_val: np.ndarray) -> tuple[float, float, float]:
    fpr, tpr, thresholds = roc_curve(y_val, s_val)
    eligible = np.flatnonzero(fpr <= FIXED_FPR)
    if len(eligible) == 0:
        idx = int(np.argmin(fpr))
    else:
        idx = int(eligible[np.argmax(tpr[eligible])])
    return float(thresholds[idx]), float(fpr[idx]), float(tpr[idx])


def _metrics(y: np.ndarray, score: np.ndarray, threshold: float) -> dict:
    pred = score >= threshold
    cm = confusion_matrix(y, pred, labels=[0, 1]).tolist()
    normal = y == 0
    return {
        "threshold_from_validation": threshold,
        "roc_auc": float(roc_auc_score(y, score)),
        "pr_auc": float(average_precision_score(y, score)),
        "precision": float(precision_score(y, pred, zero_division=0)),
        "recall": float(recall_score(y, pred, zero_division=0)),
        "f1": float(f1_score(y, pred, zero_division=0)),
        "fpr_at_selected_threshold": float(pred[normal].mean()),
        "tpr_at_fixed_fpr_target": float(pred[y == 1].mean()),
        "confusion_matrix_truth_0_1_pred_0_1": cm,
    }


def run(train_path: Path, val_path: Path, test_path: Path, candidate_path: Path, out_path: Path) -> dict:
    train, val, test = (pd.read_csv(p) for p in (train_path, val_path, test_path))
    results = {
        "fixed_fpr_target": FIXED_FPR,
        "test_path": str(test_path),
        "lens_ablation": {},
    }
    for name, features in (("NBD-only", NBD), ("PCD-only", PCD), ("fusion-all-37", NBD + PCD)):
        train_primary = train[train.top_level_label != "Sensor Malfunction"]
        val_primary = val[val.top_level_label != "Sensor Malfunction"]
        test_primary = test[test.top_level_label != "Sensor Malfunction"]
        y_val = (val_primary.top_level_label == "Cyber Intrusion").astype(int).to_numpy()
        y_test = (test_primary.top_level_label == "Cyber Intrusion").astype(int).to_numpy()
        s_val = _fit_score(train, val_primary, features)
        s_test = _fit_score(train, test_primary, features)
        threshold, val_fpr, val_tpr = _threshold_at_fpr(y_val, s_val)
        results["lens_ablation"][name] = {
            "feature_count": len(features), "features": features,
            "validation_threshold": threshold, "validation_fpr": val_fpr, "validation_tpr": val_tpr,
            "test": _metrics(y_test, s_test, threshold),
        }

    bundle = joblib.load(candidate_path)
    subtype_model = bundle["subtype_model"]
    schema = bundle["feature_schema"]
    cyber = test[test.top_level_label == "Cyber Intrusion"]
    subtype_pred = subtype_model.predict(cyber[schema])
    subtype_recall = {}
    for subtype in sorted(cyber.subtype_label.unique()):
        mask = cyber.subtype_label.to_numpy() == subtype
        subtype_recall[subtype] = {"recall": float((subtype_pred[mask] == subtype).mean()), "support": int(mask.sum())}

    top_model = bundle["top_level_model"]
    top_pred = top_model.predict(test[schema])
    test = test.copy(); test["predicted_top_level"] = top_pred
    attack = test.top_level_label == "Cyber Intrusion"
    test["tick_attack"] = test.top_level_label.eq("Cyber Intrusion")
    test["tick_pred_cyber"] = test.predicted_top_level.eq("Cyber Intrusion")
    tick = test.groupby("tick").agg(true_attack=("tick_attack", "max"), pred_cyber=("tick_pred_cyber", "max"))
    episodes = 0; detected = 0; delays = []
    in_ep = False; start = None
    for tick_value, row in tick.iterrows():
        if row.true_attack and not in_ep:
            episodes += 1; detected = detected + 0
            in_ep = True; start = int(tick_value); caught = None
        if in_ep and row.pred_cyber and caught is None:
            caught = int(tick_value)
        if in_ep and not row.true_attack:
            if caught is not None: detected += 1; delays.append(caught - start)
            in_ep = False
    if in_ep:
        if caught is not None: detected += 1; delays.append(caught - start)
    results["candidate"] = {
        "artifact": str(candidate_path),
        "threshold": bundle.get("decision_threshold"),
        "subtype_recall": subtype_recall,
        "episode_count": episodes, "episodes_detected": detected,
        "episode_detection_rate": detected / episodes if episodes else None,
        "episode_delays_seconds": delays,
        "median_delay_seconds": float(np.median(delays)) if delays else None,
        "p90_delay_seconds": float(np.percentile(delays, 90)) if delays else None,
    }
    out_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    return results


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--train", type=Path, required=True)
    ap.add_argument("--val", type=Path, required=True)
    ap.add_argument("--test", type=Path, required=True)
    ap.add_argument("--candidate", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    print(json.dumps(run(args.train, args.val, args.test, args.candidate, args.out), indent=2))
