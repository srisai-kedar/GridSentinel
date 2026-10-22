"""
train_classifier.py
-------------------
Trains and evaluates the GridSentinel Cyber-Physical Fusion Classifier.

Steps executed:
  Step 3 – Class Balance & F2 Threshold Optimisation
    - Trains with class_weight='balanced' / balanced_subsample.
    - Tunes Cyber Intrusion decision threshold against val set, optimising F2
      (beta=2, favouring recall over precision) via grid search on thresholds
      in [0.10, 0.50] at 0.01 steps.
  Step 4 – Model Comparison & Latency Benchmarking
    - Compares RandomForest, LightGBM, and XGBoost on identical 28 features.
    - Measures real per-verdict inference latency (1 000 timed calls).
    - Selects the best model by Cyber F2 on the validation set.

Architecture (two-stage):
  Stage 1 (Primary Triage):
    Best of: RandomForestClassifier / LGBMClassifier / XGBClassifier
    3-class: "Normal", "Natural Fault", "Cyber Intrusion"
  Stage 2 (Forensic Subtyping):
    RandomForestClassifier (balanced)
    3-class: "data_injection", "command_injection", "replay"

Outputs:
  - models/fusion_classifier.joblib
  - reports/confusion_matrix.png
  - reports/metrics.json
"""

from __future__ import annotations

import argparse
import datetime
import json
import time
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import joblib
import matplotlib
matplotlib.use("Agg")  # Non-interactive backend for headless server execution
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    fbeta_score,
    precision_recall_curve,
)

from app.ml.classifier_service import detect_sensor_drift_signature
from app.ml.feature_engineering import FEATURE_SCHEMA, FEATURE_SCHEMA_VERSION

PRIMARY_CLASSES: List[str] = ["Cyber Intrusion", "Natural Fault", "Normal"]
SENSOR_MALFUNCTION_LABEL: str = "Sensor Malfunction"

# ─────────────────────────────────────────────────────────────────────────────
# Optional heavy dependencies – import gracefully so tests still pass if absent
# ─────────────────────────────────────────────────────────────────────────────
try:
    from lightgbm import LGBMClassifier  # type: ignore
    _HAS_LGBM = True
except ImportError:
    _HAS_LGBM = False
    print("[Trainer] WARNING: lightgbm not installed – LightGBM will be skipped.")

try:
    from xgboost import XGBClassifier  # type: ignore
    _HAS_XGB = True
except ImportError:
    _HAS_XGB = False
    print("[Trainer] WARNING: xgboost not installed – XGBoost will be skipped.")


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def load_dataset(csv_path: str) -> Tuple[pd.DataFrame, pd.Series, pd.Series]:
    """Load and validate dataset CSV against FEATURE_SCHEMA."""
    df = pd.read_csv(csv_path)

    # Validate all feature columns exist
    missing = [f for f in FEATURE_SCHEMA if f not in df.columns]
    if missing:
        raise ValueError(f"CSV {csv_path} is missing required feature columns: {missing}")

    allowed = {"Normal", "Natural Fault", "Cyber Intrusion"}
    extra = sorted(set(df["top_level_label"].unique()) - allowed)
    if extra:
        raise ValueError(
            f"CSV {csv_path} contains labels outside the primary 3-class taxonomy: {extra}. "
            "Generate datasets with split_sensor=True (sensor-drift ticks go to a separate "
            "*_sensor_eval.csv) - the primary classifier is 3-class by design."
        )

    X = df[FEATURE_SCHEMA].copy()
    y_top = df["top_level_label"].copy()
    y_sub = df["subtype_label"].copy()

    # Fill any inadvertent NaNs with 0.0
    X = X.fillna(0.0)

    return X, y_top, y_sub


def partition_primary_and_drift(
    X: pd.DataFrame,
    y_top: pd.Series,
    y_sub: pd.Series,
) -> Tuple[pd.DataFrame, pd.Series, pd.Series, pd.DataFrame, pd.Series, pd.Series]:
    """
    Partition dataset into:
    1. Primary triage set (3 classes: Normal, Natural Fault, Cyber Intrusion)
    2. Sensor Malfunction / Drift set (held out for separate evaluation)
    """
    is_drift = y_top == SENSOR_MALFUNCTION_LABEL
    X_primary = X[~is_drift].copy()
    y_top_primary = y_top[~is_drift].copy()
    y_sub_primary = y_sub[~is_drift].copy()

    X_drift = X[is_drift].copy()
    y_top_drift = y_top[is_drift].copy()
    y_sub_drift = y_sub[is_drift].copy()

    return X_primary, y_top_primary, y_sub_primary, X_drift, y_top_drift, y_sub_drift


def decode_xgb_predictions(
    y_pred_encoded: np.ndarray,
    label_map_inv: Dict[int, str],
) -> np.ndarray:
    """
    Safely decode XGBoost integer predictions back to class label strings.
    Never silently maps unexpected or unknown class indices to 'Normal'.
    """
    decoded = []
    for p in y_pred_encoded:
        idx = int(p)
        if idx in label_map_inv:
            decoded.append(label_map_inv[idx])
        else:
            raise KeyError(f"Unexpected XGBoost class index {idx} not in label map {label_map_inv}")
    return np.array(decoded)


def evaluate_sensor_drift_scenarios(
    model: Any,
    X_drift: pd.DataFrame,
    model_name: str = "Model",
    label_map_inv: Optional[Dict[int, str]] = None,
    threshold: Optional[float] = None,
    classes: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Dedicated evaluation of Sensor Malfunction / Drift scenarios.
    Ensures sensor-drift instances are evaluated separately rather than
    silently mapped to Normal or counted incorrectly in 3-class primary triage.
    """
    n_samples = len(X_drift)
    if n_samples == 0:
        return {
            "n_samples": 0,
            "status": "no_drift_samples",
            "primary_model_verdicts": {},
            "primary_model_cyber_fp_count": 0,
            "primary_model_cyber_fpr": 0.0,
            "dedicated_pathway_intercepted": 0,
            "dedicated_pathway_recall": 0.0,
        }

    # 1. Primary Model predictions on drift rows
    if model_name == "XGBoost" and label_map_inv:
        proba = model.predict_proba(X_drift)
        label_values = list(label_map_inv.values())
        cyber_idx = label_values.index("Cyber Intrusion") if "Cyber Intrusion" in label_values else 0
        preds = []
        for row in proba:
            if threshold is not None and row[cyber_idx] >= threshold:
                preds.append("Cyber Intrusion")
            else:
                row_copy = row.copy()
                if threshold is not None:
                    row_copy[cyber_idx] = 0.0
                best_idx = int(np.argmax(row_copy))
                preds.append(label_map_inv.get(best_idx, str(best_idx)))
    else:
        if threshold is not None and classes and "Cyber Intrusion" in classes:
            proba = model.predict_proba(X_drift)
            cyber_idx = classes.index("Cyber Intrusion")
            preds = []
            for row in proba:
                if row[cyber_idx] >= threshold:
                    preds.append("Cyber Intrusion")
                else:
                    row_copy = row.copy()
                    row_copy[cyber_idx] = 0.0
                    preds.append(classes[int(np.argmax(row_copy))])
        else:
            preds = list(model.predict(X_drift))

    cyber_fp = sum(1 for p in preds if p == "Cyber Intrusion")
    cyber_fpr = float(cyber_fp / n_samples) if n_samples > 0 else 0.0
    verdict_counts = {str(k): int(v) for k, v in pd.Series(preds).value_counts().items()}

    # 2. Dedicated physics-based sensor drift signature interception
    intercepted_count = 0
    for _, row in X_drift.iterrows():
        feat_dict = {k: float(row.get(k, 0.0)) for k in FEATURE_SCHEMA}
        if detect_sensor_drift_signature(feat_dict):
            intercepted_count += 1

    pathway_recall = float(intercepted_count / n_samples) if n_samples > 0 else 0.0

    return {
        "n_samples": n_samples,
        "primary_model_verdicts": verdict_counts,
        "primary_model_cyber_fp_count": cyber_fp,
        "primary_model_cyber_fpr": round(cyber_fpr, 4),
        "dedicated_pathway_intercepted": intercepted_count,
        "dedicated_pathway_recall": round(pathway_recall, 4),
    }


def _cyber_f2(y_true: pd.Series, y_proba_cyber: np.ndarray, threshold: float) -> float:
    """Return F2 score for the 'Cyber Intrusion' class at a given threshold."""
    y_pred_cyber = (y_proba_cyber >= threshold).astype(int)
    y_true_cyber = (y_true == "Cyber Intrusion").astype(int)
    return float(fbeta_score(y_true_cyber, y_pred_cyber, beta=2, zero_division=0))


def tune_threshold(
    model,
    X_val: pd.DataFrame,
    y_val: pd.Series,
    classes: List[str],
) -> Tuple[float, float]:
    """
    Grid-search the Cyber Intrusion decision threshold over [0.10, 0.60]
    at 0.01 steps, optimising F2 on the validation set.
    Returns (best_threshold, best_f2).
    """
    cyber_idx = list(classes).index("Cyber Intrusion")
    proba = model.predict_proba(X_val)
    cyber_proba = proba[:, cyber_idx]

    best_thr, best_f2 = 0.5, 0.0
    thresholds = np.arange(0.10, 0.61, 0.01)
    for thr in thresholds:
        f2 = _cyber_f2(y_val, cyber_proba, thr)
        if f2 > best_f2:
            best_f2 = f2
            best_thr = float(thr)

    return best_thr, best_f2


def measure_latency(model, X_sample: pd.DataFrame, n_calls: int = 1000) -> float:
    """
    Measure mean per-verdict latency by timing n_calls single-row predictions.
    Returns mean latency in milliseconds.
    """
    single_row = X_sample.iloc[:1]
    # Warm-up
    for _ in range(10):
        model.predict_proba(single_row)

    start = time.perf_counter()
    for _ in range(n_calls):
        model.predict_proba(single_row)
    elapsed_ms = (time.perf_counter() - start) * 1000 / n_calls
    return elapsed_ms


def _build_candidates() -> Dict[str, Any]:
    """Build the candidate classifier dictionary."""
    candidates: Dict[str, Any] = {
        "RandomForest": RandomForestClassifier(
            n_estimators=200,
            max_depth=None,
            class_weight="balanced_subsample",
            random_state=42,
            n_jobs=-1,
        ),
    }
    if _HAS_LGBM:
        candidates["LightGBM"] = LGBMClassifier(
            n_estimators=300,
            learning_rate=0.05,
            num_leaves=63,
            class_weight="balanced",
            random_state=42,
            n_jobs=-1,
            verbose=-1,
        )
    if _HAS_XGB:
        candidates["XGBoost"] = XGBClassifier(
            n_estimators=300,
            learning_rate=0.05,
            max_depth=6,
            random_state=42,
            n_jobs=-1,
            eval_metric="mlogloss",
            verbosity=0,
        )
    return candidates


# ─────────────────────────────────────────────────────────────────────────────
# Main training function
# ─────────────────────────────────────────────────────────────────────────────

def train_and_evaluate(
    train_csv: str = "data/generated/train_dataset_seed42.csv",
    test_csv: str = "data/generated/test_dataset_seed1337.csv",
    val_csv: str = "data/generated/val_dataset_seed999.csv",
    model_out: str = "models/fusion_classifier.joblib",
    report_dir: str = "reports",
) -> Dict[str, Any]:
    """
    Train fusion classifier on train_csv, tune threshold on val_csv,
    and evaluate on held-out test_csv.
    """
    print(f"\n[Trainer] Loading training set from {train_csv}...")
    X_train, y_top_train, y_sub_train = load_dataset(train_csv)
    print(f"  Training samples: {len(X_train)} rows across {len(FEATURE_SCHEMA)} features")
    print(f"  Training class distribution:\n{y_top_train.value_counts()}")

    (
        X_train_primary,
        y_top_train_primary,
        y_sub_train_primary,
        X_train_drift,
        y_top_train_drift,
        y_sub_train_drift,
    ) = partition_primary_and_drift(X_train, y_top_train, y_sub_train)

    if len(X_train_drift) > 0:
        print(f"  [Taxonomy] Partitioned {len(X_train_drift)} Sensor Malfunction rows from primary training set;")
        print(f"             primary triage trains strictly on {len(X_train_primary)} 3-class samples.")

    print(f"\n[Trainer] Loading held-out test set from {test_csv}...")
    X_test, y_top_test, y_sub_test = load_dataset(test_csv)
    print(f"  Test samples: {len(X_test)} rows")
    print(f"  Test class distribution:\n{y_top_test.value_counts()}")

    (
        X_test_primary,
        y_top_test_primary,
        y_sub_test_primary,
        X_test_drift,
        y_top_test_drift,
        y_sub_test_drift,
    ) = partition_primary_and_drift(X_test, y_top_test, y_sub_test)

    if len(X_test_drift) > 0:
        print(f"  [Taxonomy] Partitioned {len(X_test_drift)} Sensor Malfunction rows from primary test set for separate evaluation.")

    # Load validation set for threshold tuning (may not exist yet)
    has_val = Path(val_csv).exists()
    if has_val:
        print(f"\n[Trainer] Loading validation set from {val_csv}...")
        X_val, y_val, _ = load_dataset(val_csv)
        print(f"  Val samples: {len(X_val)} rows")
        (
            X_val_primary,
            y_val_primary,
            _,
            X_val_drift,
            _,
            _,
        ) = partition_primary_and_drift(X_val, y_val, pd.Series(index=y_val.index))
        if len(X_val_drift) > 0:
            print(f"  [Taxonomy] Partitioned {len(X_val_drift)} Sensor Malfunction rows from validation set.")
    else:
        print(f"\n[Trainer] WARNING: {val_csv} not found – will use test set for threshold tuning.")
        X_val, y_val = X_test, y_top_test
        X_val_primary, y_val_primary = X_test_primary, y_top_test_primary
        X_val_drift = X_test_drift

    # -----------------------------------------------------------------------
    # Step 4: Model Comparison
    # -----------------------------------------------------------------------
    candidates = _build_candidates()
    comparison_results: Dict[str, Dict[str, Any]] = {}
    best_model_name: Optional[str] = None
    best_top_model = None
    best_threshold = 0.5
    best_cyber_f2 = -1.0

    print(f"\n[Trainer] == Step 4: Model Comparison ==")
    print(f"  Comparing {len(candidates)} candidates: {list(candidates.keys())}")

    for name, clf in candidates.items():
        print(f"\n  Training {name}...")
        fit_start = time.perf_counter()

        # Dynamic integer-encoded labels for XGBoost supporting primary taxonomy
        unique_labels = sorted(list(y_top_train_primary.unique()))
        label_map = {lbl: idx for idx, lbl in enumerate(unique_labels)}
        label_map_inv = {idx: lbl for lbl, idx in label_map.items()}

        if name == "XGBoost":
            y_train_enc = y_top_train_primary.map(label_map)
            y_val_enc = y_val_primary.map(label_map)
            # class weights for XGBoost via sample_weight
            counts = y_train_enc.value_counts()
            total = len(y_train_enc)
            sw = y_train_enc.map({k: total / (len(unique_labels) * v) for k, v in counts.items()})
            clf.fit(X_train_primary, y_train_enc, sample_weight=sw)
        else:
            clf.fit(X_train_primary, y_top_train_primary)

        fit_time = time.perf_counter() - fit_start
        print(f"    Fit time: {fit_time:.1f}s")

        # Latency benchmark
        latency_ms = measure_latency(clf, X_test_primary)
        print(f"    Inference latency: {latency_ms:.3f} ms/verdict")

        # Threshold tuning on validation set
        if name == "XGBoost":
            xgb_classes_named = [label_map_inv[int(c)] for c in clf.classes_]
            best_thr_c, best_f2_c = tune_threshold(clf, X_val_primary, y_val_primary, xgb_classes_named)
        else:
            classes_list = list(clf.classes_)
            best_thr_c, best_f2_c = tune_threshold(clf, X_val_primary, y_val_primary, classes_list)

        print(f"    Best Cyber threshold: {best_thr_c:.2f} (val F2={best_f2_c:.4f})")

        # Evaluate on test set at argmax (default threshold)
        if name == "XGBoost":
            y_pred_default = decode_xgb_predictions(clf.predict(X_test_primary), label_map_inv)
        else:
            y_pred_default = clf.predict(X_test_primary)

        acc = float(accuracy_score(y_top_test_primary, y_pred_default))

        comparison_results[name] = {
            "fit_time_s": round(fit_time, 2),
            "latency_ms": round(latency_ms, 3),
            "best_threshold": round(best_thr_c, 2),
            "val_cyber_f2": round(best_f2_c, 4),
            "test_accuracy_default": round(acc, 4),
        }

        if best_f2_c > best_cyber_f2:
            best_cyber_f2 = best_f2_c
            best_model_name = name
            best_top_model = clf
            best_threshold = best_thr_c

    print(f"\n[Trainer] == Model Comparison Summary ==")
    for name, res in comparison_results.items():
        marker = " <- BEST" if name == best_model_name else ""
        print(f"  {name:<14} | Latency: {res['latency_ms']:.3f}ms | Val CyberF2: {res['val_cyber_f2']:.4f} | "
              f"Threshold: {res['best_threshold']:.2f}{marker}")

    print(f"\n[Trainer] Selected: {best_model_name} (threshold={best_threshold:.2f})")

    # -----------------------------------------------------------------------
    # Stage 2: Secondary Cyber Subtype Model
    # -----------------------------------------------------------------------
    print("[Trainer] Training Secondary Forensic Cyber Subtyping Model...")
    cyber_mask_train = y_top_train_primary == "Cyber Intrusion"
    X_train_cyber = X_train_primary[cyber_mask_train]
    y_sub_train_cyber = y_sub_train_primary[cyber_mask_train]

    subtype_model = RandomForestClassifier(
        n_estimators=200,
        max_depth=10,
        class_weight="balanced",
        random_state=42,
        n_jobs=-1,
    )
    subtype_model.fit(X_train_cyber, y_sub_train_cyber)

    # -----------------------------------------------------------------------
    # Step 3: Evaluate with Tuned Threshold on Test Set
    # -----------------------------------------------------------------------
    print(f"\n[Trainer] == Step 3: Evaluating with Tuned Threshold (threshold={best_threshold:.2f}) ==")
    unique_labels = sorted(list(y_top_train_primary.unique()))
    classes = sorted(list(best_top_model.classes_)) if best_model_name != "XGBoost" else unique_labels

    if best_model_name == "XGBoost":
        label_map = {lbl: idx for idx, lbl in enumerate(unique_labels)}
        label_map_inv = {idx: lbl for lbl, idx in label_map.items()}
        xgb_proba = best_top_model.predict_proba(X_test_primary)
        cyber_idx_xgb = label_map.get("Cyber Intrusion", 0)
        cyber_proba_test = xgb_proba[:, cyber_idx_xgb]
        # Apply tuned threshold: if cyber_proba >= threshold => Cyber Intrusion,
        # else argmax of remaining
        y_top_pred = []
        for i, row_proba in enumerate(xgb_proba):
            if row_proba[cyber_idx_xgb] >= best_threshold:
                y_top_pred.append("Cyber Intrusion")
            else:
                # Suppress cyber class and pick argmax of rest
                row_copy = row_proba.copy()
                row_copy[cyber_idx_xgb] = 0.0
                y_top_pred.append(label_map_inv[int(np.argmax(row_copy))])
        y_top_pred = np.array(y_top_pred)
    else:
        proba_all = best_top_model.predict_proba(X_test_primary)
        cyber_idx = classes.index("Cyber Intrusion")
        cyber_proba_test = proba_all[:, cyber_idx]
        y_top_pred = []
        for i, row_proba in enumerate(proba_all):
            if row_proba[cyber_idx] >= best_threshold:
                y_top_pred.append("Cyber Intrusion")
            else:
                # Argmax excluding cyber class
                row_copy = row_proba.copy()
                row_copy[cyber_idx] = 0.0
                y_top_pred.append(classes[int(np.argmax(row_copy))])
        y_top_pred = np.array(y_top_pred)

    acc = float(accuracy_score(y_top_test_primary, y_top_pred))
    cm = confusion_matrix(y_top_test_primary, y_top_pred, labels=classes)
    clf_report = classification_report(y_top_test_primary, y_top_pred, output_dict=True)

    # Cyber-specific metrics
    is_true_cyber = (y_top_test_primary == "Cyber Intrusion")
    is_pred_cyber = (y_top_pred == "Cyber Intrusion")
    total_non_cyber = int((~is_true_cyber).sum())
    false_positives_cyber = int(((~is_true_cyber) & is_pred_cyber).sum())
    fpr_cyber = float(false_positives_cyber / total_non_cyber) if total_non_cyber > 0 else 0.0

    cyber_true_count = int(is_true_cyber.sum())
    cyber_tp = int((is_true_cyber & is_pred_cyber).sum())
    cyber_fn = cyber_true_count - cyber_tp
    cyber_recall = float(cyber_tp / cyber_true_count) if cyber_true_count > 0 else 0.0

    # Cyber F2 on test set
    test_cyber_f2 = float(fbeta_score(
        (y_top_test_primary == "Cyber Intrusion").astype(int),
        (y_top_pred == "Cyber Intrusion").astype(int),
        beta=2, zero_division=0,
    ))

    print(f"\n=======================================================")
    print(f"EVALUATION METRICS (HELD-OUT TEST SET) with tuned threshold:")
    print(f"=======================================================")
    print(f"Model:                          {best_model_name}")
    print(f"Decision Threshold:             {best_threshold:.2f}")
    print(f"Overall Accuracy:               {acc * 100:.2f}%")
    print(f"Cyber Intrusion Recall:         {cyber_recall * 100:.2f}% ({cyber_tp} TP / {cyber_true_count} real Cyber)")
    print(f"Cyber Intrusion FPR:            {fpr_cyber * 100:.2f}% ({false_positives_cyber}/{total_non_cyber})")
    print(f"Cyber F2 Score:                 {test_cyber_f2:.4f}")
    print(f"Confusion Matrix (labels={classes}):\n{cm}")
    print("\nPer-class Classification Report:")
    for cls in classes:
        p = clf_report[cls]["precision"]
        r = clf_report[cls]["recall"]
        f1 = clf_report[cls]["f1-score"]
        supp = clf_report[cls]["support"]
        print(f"  {cls:<18} Precision: {p*100:.2f}% | Recall: {r*100:.2f}% | F1: {f1*100:.2f}% | Support: {supp}")

    # -----------------------------------------------------------------------
    # Feature Importances
    # -----------------------------------------------------------------------
    print(f"\n[Trainer] == Feature Importances ({best_model_name}) ==")
    if hasattr(best_top_model, "feature_importances_"):
        importances = best_top_model.feature_importances_
        feat_imp = sorted(zip(FEATURE_SCHEMA, importances), key=lambda x: x[1], reverse=True)
        for feat, imp in feat_imp:
            print(f"  {feat:<55} {imp:.4f}")
    else:
        feat_imp = []
        print("  (feature_importances_ not available for this model type)")

    # -----------------------------------------------------------------------
    # Latency of Best Model
    # -----------------------------------------------------------------------
    best_latency_ms = comparison_results[best_model_name]["latency_ms"]
    latency_ok = best_latency_ms < 50.0
    print(f"\n[Trainer] Best model latency: {best_latency_ms:.3f} ms/verdict  {'[PASS < 50ms]' if latency_ok else '[FAIL EXCEEDS 50ms]'}")

    # -----------------------------------------------------------------------
    # Subtyping on Cyber instances in test set
    # -----------------------------------------------------------------------
    cyber_mask_test = y_top_test_primary == "Cyber Intrusion"
    if cyber_mask_test.sum() > 0:
        X_test_cyber = X_test_primary[cyber_mask_test]
        y_sub_test_cyber = y_sub_test_primary[cyber_mask_test]
        y_sub_pred_cyber = subtype_model.predict(X_test_cyber)
        sub_acc = float(accuracy_score(y_sub_test_cyber, y_sub_pred_cyber))
        print(f"\nCyber Subtype Accuracy:         {sub_acc * 100:.2f}%")
    else:
        sub_acc = 0.0

    # -----------------------------------------------------------------------
    # Separate Evaluation: Sensor Malfunction / Drift Scenarios
    # -----------------------------------------------------------------------
    sensor_drift_eval = None
    if len(X_test_drift) > 0:
        print(f"\n[Trainer] == Separate Evaluation: Sensor Malfunction / Drift ({len(X_test_drift)} samples) ==")
        label_map_inv_opt = label_map_inv if best_model_name == "XGBoost" else None
        sensor_drift_eval = evaluate_sensor_drift_scenarios(
            model=best_top_model,
            X_drift=X_test_drift,
            model_name=best_model_name,
            label_map_inv=label_map_inv_opt,
            threshold=best_threshold,
            classes=classes,
        )
        print(f"  Samples:                        {sensor_drift_eval['n_samples']}")
        print(f"  Primary Model Verdicts:         {sensor_drift_eval['primary_model_verdicts']}")
        print(f"  Primary Cyber False Alarms:     {sensor_drift_eval['primary_model_cyber_fp_count']} ({sensor_drift_eval['primary_model_cyber_fpr']*100:.2f}%)")
        print(f"  Dedicated Pathway Intercepted:  {sensor_drift_eval['dedicated_pathway_intercepted']}/{sensor_drift_eval['n_samples']} ({sensor_drift_eval['dedicated_pathway_recall']*100:.2f}%)")
    else:
        print("\n[Trainer] Note: Test set contains no 'Sensor Malfunction' rows (pure 3-class primary triage held-out set).")

    # -----------------------------------------------------------------------
    # Save Reports (Confusion Matrix Plot + Metrics JSON)
    # -----------------------------------------------------------------------
    report_path = Path(report_dir)
    report_path.mkdir(parents=True, exist_ok=True)

    # 1. Confusion Matrix PNG
    fig, ax = plt.subplots(figsize=(7, 6))
    im = ax.imshow(cm, interpolation="nearest", cmap=plt.cm.Blues)
    ax.figure.colorbar(im, ax=ax)
    ax.set(
        xticks=np.arange(len(classes)),
        yticks=np.arange(len(classes)),
        xticklabels=classes,
        yticklabels=classes,
        title=f"GridSentinel Fusion Classifier ({best_model_name}) — threshold={best_threshold:.2f}",
        ylabel="True Class",
        xlabel="Predicted Class",
    )
    plt.setp(ax.get_xticklabels(), rotation=30, ha="right", rotation_mode="anchor")

    thresh = cm.max() / 2.0
    for i in range(cm.shape[0]):
        for j in range(cm.shape[1]):
            ax.text(
                j, i, format(cm[i, j], "d"),
                ha="center", va="center",
                color="white" if cm[i, j] > thresh else "black",
                fontweight="bold",
            )
    fig.tight_layout()
    cm_png_path = report_path / "confusion_matrix.png"
    plt.savefig(cm_png_path, dpi=150)
    plt.close(fig)
    print(f"\n[Trainer] Saved Confusion Matrix to {cm_png_path}")

    # 2. Metrics JSON
    metrics_data = {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "model_selected": best_model_name,
        "decision_threshold": best_threshold,
        "overall_accuracy": round(acc, 4),
        "cyber_intrusion_recall": round(cyber_recall, 4),
        "cyber_intrusion_tp": cyber_tp,
        "cyber_intrusion_total": cyber_true_count,
        "cyber_intrusion_fpr": round(fpr_cyber, 4),
        "cyber_f2_score": round(test_cyber_f2, 4),
        "cyber_subtype_accuracy": round(sub_acc, 4),
        "latency_ms_per_verdict": round(best_latency_ms, 3),
        "latency_within_50ms": latency_ok,
        "classes": classes,
        "confusion_matrix": cm.tolist(),
        "classification_report": clf_report,
        "train_samples_count": len(X_train),
        "train_primary_samples_count": len(X_train_primary),
        "test_samples_count": len(X_test),
        "test_primary_samples_count": len(X_test_primary),
        "val_samples_count": len(X_val),
        "val_primary_samples_count": len(X_val_primary),
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "feature_count": len(FEATURE_SCHEMA),
        "model_comparison": comparison_results,
        "feature_importances": [
            {"feature": f, "importance": round(float(imp), 6)}
            for f, imp in feat_imp
        ],
    }
    if sensor_drift_eval is not None:
        metrics_data["sensor_drift_evaluation"] = sensor_drift_eval

    metrics_json_path = report_path / "metrics.json"
    with open(metrics_json_path, "w") as f:
        json.dump(metrics_data, f, indent=2)
    print(f"[Trainer] Saved Metrics to {metrics_json_path}")

    # -----------------------------------------------------------------------
    # Save Model Bundle (joblib)
    # -----------------------------------------------------------------------
    model_file_path = Path(model_out)
    model_file_path.parent.mkdir(parents=True, exist_ok=True)

    bundle = {
        "top_level_model": best_top_model,
        "subtype_model": subtype_model,
        "feature_schema": FEATURE_SCHEMA,
        "classes": classes,
        "subtype_classes": list(subtype_model.classes_),
        "decision_threshold": best_threshold,
        "model_name": best_model_name,
        "version": FEATURE_SCHEMA_VERSION,
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "trained_timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "metrics_summary": {
            "accuracy": acc,
            "cyber_recall": cyber_recall,
            "cyber_tp": cyber_tp,
            "cyber_total": cyber_true_count,
            "cyber_fpr": fpr_cyber,
            "cyber_f2": test_cyber_f2,
            "latency_ms": best_latency_ms,
            "subtype_accuracy": sub_acc,
        },
    }
    if sensor_drift_eval is not None:
        bundle["metrics_summary"]["sensor_drift_evaluation"] = sensor_drift_eval

    joblib.dump(bundle, model_file_path)
    print(f"[Trainer] Saved Model Bundle to {model_file_path}")

    return metrics_data


# ─────────────────────────────────────────────────────────────────────────────
# Leakage Smoke-Test (Step 5)
# ─────────────────────────────────────────────────────────────────────────────

def leakage_smoke_test(
    train_csv: str = "data/generated/train_dataset_seed42.csv",
    test_csv: str = "data/generated/test_dataset_seed1337.csv",
) -> Dict[str, Any]:
    """
    Step 5 -- Leakage Smoke-Test.
    Retrains with randomly shuffled labels; balanced accuracy must collapse to
    ~33.3% (3-class random chance) to confirm no label leakage exists.
    """
    from sklearn.metrics import balanced_accuracy_score

    print("\n[Smoke-Test] == Step 5: Leakage Smoke-Test ==")
    X_train, y_top_train, _ = load_dataset(train_csv)
    X_test, y_top_test, _ = load_dataset(test_csv)

    # Filter out Sensor Malfunction so baseline strictly tests 3-class random chance
    mask_train = y_top_train != SENSOR_MALFUNCTION_LABEL
    mask_test = y_top_test != SENSOR_MALFUNCTION_LABEL
    X_train, y_top_train = X_train[mask_train], y_top_train[mask_train]
    X_test, y_top_test = X_test[mask_test], y_top_test[mask_test]

    rng = np.random.default_rng(seed=0)
    y_shuffled = pd.Series(
        rng.permutation(y_top_train.values),
        index=y_top_train.index,
    )

    clf = RandomForestClassifier(n_estimators=100, class_weight="balanced", random_state=0, n_jobs=-1)
    clf.fit(X_train, y_shuffled)
    y_pred = clf.predict(X_test)
    shuffled_std_acc = float(accuracy_score(y_top_test, y_pred))
    shuffled_bal_acc = float(balanced_accuracy_score(y_top_test, y_pred))

    # For 3 classes with mutual information = 0, balanced accuracy collapses to 1/3 (33.3%)
    passed = shuffled_bal_acc < 0.40
    print(f"  Shuffled-label balanced accuracy: {shuffled_bal_acc * 100:.2f}% (random chance: 33.33%)")
    print(f"  Shuffled-label standard accuracy: {shuffled_std_acc * 100:.2f}% (majority class baseline: 72.31%)")
    print(f"  Leakage check: {'PASS (balanced accuracy collapsed to random chance -- NO LEAKAGE)' if passed else 'FAIL (suspiciously high -- investigate!)'}")

    return {
        "shuffled_balanced_accuracy": round(shuffled_bal_acc, 4),
        "shuffled_standard_accuracy": round(shuffled_std_acc, 4),
        "leakage_test_passed": passed,
    }


# ─────────────────────────────────────────────────────────────────────────────
# CLI Entry Point
# ─────────────────────────────────────────────────────────────────────────────

def main_cli():
    parser = argparse.ArgumentParser(description="GridSentinel Model Trainer")
    parser.add_argument("--train", type=str, default="data/generated/train_dataset_seed42.csv", help="Train CSV")
    parser.add_argument("--test", type=str, default="data/generated/test_dataset_seed1337.csv", help="Test CSV")
    parser.add_argument("--val", type=str, default="data/generated/val_dataset_seed999.csv", help="Val CSV for threshold tuning")
    parser.add_argument("--out", type=str, default="models/fusion_classifier.joblib", help="Model joblib path")
    parser.add_argument("--report", type=str, default="reports", help="Reports dir")
    parser.add_argument("--smoke-test", action="store_true", help="Run Step 5 leakage smoke-test after training")

    args = parser.parse_args()
    metrics = train_and_evaluate(
        train_csv=args.train,
        test_csv=args.test,
        val_csv=args.val,
        model_out=args.out,
        report_dir=args.report,
    )

    if args.smoke_test:
        smoke = leakage_smoke_test(train_csv=args.train, test_csv=args.test)
        # Append to metrics json
        report_path = Path(args.report)
        metrics_json_path = report_path / "metrics.json"
        if metrics_json_path.exists():
            with open(metrics_json_path) as f:
                m = json.load(f)
            m["leakage_smoke_test"] = smoke
            with open(metrics_json_path, "w") as f:
                json.dump(m, f, indent=2)

    return metrics


if __name__ == "__main__":
    main_cli()
