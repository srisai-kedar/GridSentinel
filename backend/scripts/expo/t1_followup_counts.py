"""Read-only T1 follow-up counts and operating-point analysis."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import confusion_matrix, roc_auc_score, roc_curve
from sklearn.pipeline import make_pipeline

NBD = ["nbd_unexpected_write_count", "nbd_mean_response_time_ms", "nbd_std_response_time_ms", "nbd_distinct_sources_count", "nbd_fc3_read_count", "nbd_fc6_write_count", "nbd_fc16_write_count", "nbd_error_count", "nbd_traffic_volume", "nbd_modbus_anomaly_rate"]
PCD = ["pcd_max_lnr", "pcd_is_target_rtu_max_lnr", "pcd_chi2_statistic", "pcd_chi2_ratio", "pcd_chi2_failed", "pcd_target_rtu_v_residual", "pcd_target_rtu_p_residual", "pcd_target_rtu_is_flagged", "pcd_global_bad_data_flag", "pcd_voltage_pu_reported", "pcd_voltage_dev_nominal", "pcd_p_mw_reported", "pcd_status_code", "pcd_physics_network_disagreement_index", "pcd_temporal_dv_dt_3tick", "pcd_temporal_dp_dt_3tick", "pcd_temporal_dq_dt_3tick", "pcd_cross_rtu_voltage_divergence", "pcd_resid_jump", "pcd_resid_persist", "pcd_resid_concentration", "pcd_resid_rtu_share", "pcd_resid_breadth_count", "pcd_resid_breadth_frac", "dpn_legacy", "dpn_ing_delta", "dpn_ing_resid"]


def wilson(success: int, total: int) -> dict:
    if total:
        z = 1.959963984540054
        phat = success / total
        denom = 1 + z * z / total
        centre = (phat + z * z / (2 * total)) / denom
        half = z * ((phat * (1 - phat) / total + z * z / (4 * total * total)) ** 0.5) / denom
        lo, hi = centre - half, centre + half
    else:
        lo, hi = 0.0, 0.0
    return {"success": int(success), "total": int(total), "estimate": success / total if total else None, "wilson_95_low": float(lo), "wilson_95_high": float(hi)}


def episodes(values: list[int]) -> int:
    return sum(i == 0 or values[i] != values[i - 1] + 1 for i in range(len(values)))


def binary_counts(y: np.ndarray, pred: np.ndarray) -> dict:
    tn, fp, fn, tp = confusion_matrix(y, pred, labels=[0, 1]).ravel().tolist()
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn, "recall": wilson(tp, tp + fn), "precision": wilson(tp, tp + fp), "fpr": wilson(fp, fp + tn)}


def model_binary(model_bundle: dict, frame: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    schema = model_bundle["feature_schema"]
    score = model_bundle["top_level_model"].predict_proba(frame[schema])
    classes = list(model_bundle.get("classes", model_bundle["top_level_model"].classes_))
    cyber_idx = classes.index("Cyber Intrusion")
    threshold = float(model_bundle.get("decision_threshold", 0.5))
    pred = []
    for row in score:
        if row[cyber_idx] >= threshold:
            pred.append("Cyber Intrusion")
        else:
            non_cyber = row.copy(); non_cyber[cyber_idx] = -1.0
            pred.append(classes[int(np.argmax(non_cyber))])
    pred = np.asarray(pred)
    return score[:, cyber_idx], pred


def select_threshold(y: np.ndarray, score: np.ndarray, target: float) -> float:
    fpr, _, thresholds = roc_curve(y, score)
    eligible = np.flatnonzero(fpr <= target)
    return float(thresholds[eligible[-1]]) if len(eligible) else float(thresholds[np.argmin(fpr)])


def lens_result(train: pd.DataFrame, val: pd.DataFrame, test: pd.DataFrame, features: list[str]) -> dict:
    tr = train[train.top_level_label != "Sensor Malfunction"]
    va = val[val.top_level_label != "Sensor Malfunction"]
    te = test[test.top_level_label != "Sensor Malfunction"]
    ytr = tr.top_level_label.eq("Cyber Intrusion").astype(int)
    yva = va.top_level_label.eq("Cyber Intrusion").astype(int).to_numpy()
    yte = te.top_level_label.eq("Cyber Intrusion").astype(int).to_numpy()
    model = make_pipeline(SimpleImputer(strategy="median"), RandomForestClassifier(n_estimators=200, class_weight="balanced_subsample", random_state=42, n_jobs=-1))
    model.fit(tr[features], ytr)
    sv, st = model.predict_proba(va[features])[:, 1], model.predict_proba(te[features])[:, 1]
    out = {"feature_count": len(features), "roc_auc": float(roc_auc_score(yte, st)), "operating_points": {}}
    for target in (0.005, 0.01):
        threshold = select_threshold(yva, sv, target)
        pred = (st >= threshold).astype(int)
        counts = binary_counts(yte, pred)
        out["operating_points"][str(target)] = {"validation_threshold": threshold, "test_fpr": counts["fpr"]["estimate"], "test_tpr": counts["recall"]["estimate"], "test_counts": {k: counts[k] for k in ("tp", "fp", "fn", "tn")}}
    return out


def main(args: argparse.Namespace) -> dict:
    train, val, test = [pd.read_csv(p) for p in (args.train, args.val, args.test)]
    candidate = joblib.load(args.candidate)
    y_full = test.top_level_label.eq("Cyber Intrusion").to_numpy().astype(int)
    score, pred_labels = model_binary(candidate, test)
    threshold = float(candidate["decision_threshold"])
    pred_cyber = pred_labels == "Cyber Intrusion"
    primary = test.top_level_label != "Sensor Malfunction"
    y_primary = y_full[primary]
    pred_primary = pred_cyber[primary]
    primary_counts = binary_counts(y_primary, pred_primary)
    cm = confusion_matrix(test.loc[primary, "top_level_label"], pred_labels[primary], labels=["Cyber Intrusion", "Natural Fault", "Normal"]).tolist()

    cyber_rows = test[test.top_level_label == "Cyber Intrusion"]
    subtypes = {}
    sub_pred = candidate["subtype_model"].predict(cyber_rows[candidate["feature_schema"]])
    for subtype in sorted(cyber_rows.subtype_label.unique()):
        mask = cyber_rows.subtype_label.to_numpy() == subtype
        subtypes[subtype] = {"counts": wilson(int((sub_pred[mask] == subtype).sum()), int(mask.sum()))}

    ticks = test.groupby("tick").agg(true_attack=("top_level_label", lambda s: bool((s == "Cyber Intrusion").any())), pred_attack=("pred", "max")) if False else None
    tick_true = test.groupby("tick").top_level_label.apply(lambda s: bool((s == "Cyber Intrusion").any()))
    tick_pred = test.assign(pred_cyber=pred_cyber).groupby("tick").pred_cyber.max()
    attack_ticks = [int(t) for t, v in tick_true.items() if v]
    attack_pred_ticks = {int(t) for t, v in tick_pred.items() if v}
    attack_episode_starts = set(t for i, t in enumerate(attack_ticks) if i == 0 or t != attack_ticks[i - 1] + 1)
    detected = [t for t in attack_episode_starts if any(x in attack_pred_ticks for x in range(t, max(attack_ticks) + 1))]
    delays = []
    for start in attack_episode_starts:
        after = [x for x in attack_pred_ticks if x >= start and x <= max(attack_ticks)]
        if after: delays.append(min(after) - start)
    non_attack_pred = sorted(attack_pred_ticks.difference(set(attack_ticks)))
    false_alarm_episodes = episodes(non_attack_pred)

    model_prod = joblib.load(args.production)
    prod_score, prod_pred = model_binary(model_prod, test)
    prod_primary_counts = binary_counts(y_primary, (prod_pred[primary] == "Cyber Intrusion"))
    prod_cm = confusion_matrix(test.loc[primary, "top_level_label"], prod_pred[primary], labels=["Cyber Intrusion", "Natural Fault", "Normal"]).tolist()
    importance = candidate["top_level_model"].feature_importances_
    schema = candidate["feature_schema"]
    ranked = sorted(zip(schema, importance), key=lambda x: x[1], reverse=True)
    nbd_rank = next(i + 1 for i, (name, _) in enumerate(ranked) if name == "nbd_unexpected_write_count")
    nbd_share = float(dict(ranked)["nbd_unexpected_write_count"] / sum(importance))
    result = {"inputs": {"train": str(args.train), "validation": str(args.val), "test": str(args.test)}, "candidate_threshold": {"value": threshold, "source": "candidate bundle; validation-only selection recorded by trainer"}, "test_row_count": len(test), "attack_readings": int(y_full.sum()), "attack_prevalence": float(y_full.mean()), "candidate_primary_confusion_matrix": {"labels": ["Cyber Intrusion", "Natural Fault", "Normal"], "matrix": cm}, "candidate_primary_binary": primary_counts, "candidate_subtype_recall": subtypes, "production_model": {"schema_count": len(model_prod["feature_schema"]), "schema": model_prod["feature_schema"], "threshold": model_prod.get("decision_threshold"), "primary_confusion_matrix": {"labels": ["Cyber Intrusion", "Natural Fault", "Normal"], "matrix": prod_cm}, "primary_binary": prod_primary_counts}, "lens_ablation": {"NBD-only": lens_result(train, val, test, NBD), "PCD-only": lens_result(train, val, test, PCD), "fusion-all-37": lens_result(train, val, test, NBD + PCD)}, "feature_importance": {"nbd_unexpected_write_count_rank": nbd_rank, "nbd_unexpected_write_count_share": nbd_share, "top_10": [{"feature": n, "importance": float(v), "share": float(v / sum(importance))} for n, v in ranked[:10]]}, "episodes": {"attack_episode_count": len(attack_episode_starts), "detected": len(detected), "detection_rate": len(detected) / len(attack_episode_starts), "delays_seconds": delays, "median_delay_seconds": float(np.median(delays)), "p90_delay_seconds": float(np.percentile(delays, 90)), "false_alarm_episode_count_non_attack_ticks": false_alarm_episodes, "duration_hours": float((test.tick.max() - test.tick.min() + 1) / 3600), "false_alarm_episodes_per_hour": float(false_alarm_episodes / ((test.tick.max() - test.tick.min() + 1) / 3600))}, "old_vs_new_generation": {"corrected_test_ticks": int(test.tick.max()), "corrected_schedule": "seed=1337; total_ticks=700; random scenario transitions with probabilities 25% Normal, 25% Natural Fault, 25% Sensor Malfunction, 25% Cyber Intrusion; durations depend on seeded random.randint calls", "older_reported_episodes": 22, "corrected_observed_episodes": len(attack_episode_starts), "comparison_note": "The repository's older test_dataset_seed1337.csv has 22 cyber episodes; the corrected nbd_fixed_test_seed1337.csv has 17. They are distinct files; the safe probe is not claimed byte-identical to the documented historical hash."}, "model_compatibility": {"production_scored_read_only": True, "production_schema_compatible_with_test_columns": all(x in test.columns for x in model_prod["feature_schema"])}}
    args.out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--train", type=Path, required=True); ap.add_argument("--val", type=Path, required=True); ap.add_argument("--test", type=Path, required=True); ap.add_argument("--candidate", type=Path, required=True); ap.add_argument("--production", type=Path, required=True); ap.add_argument("--out", type=Path, required=True)
    main(ap.parse_args())
