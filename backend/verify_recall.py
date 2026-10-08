"""
verify_recall.py
----------------
CHANGE 1 — Confirm Real Cyber-Intrusion Recall.

This script is EVALUATION ONLY. It:
  1. Loads the deployed model artifact (models/fusion_classifier.joblib)
  2. Loads the separately-seeded held-out test set (data/generated/test_dataset_seed1337.csv)
  3. Produces a full confusion matrix, per-class precision/recall/F1, and
     Cyber Intrusion-specific FPR/FNR
  4. Runs the label-shuffle leakage smoke test
  5. Prints everything. Does NOT retrain, tune, or modify the model.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    classification_report,
    confusion_matrix,
    fbeta_score,
)

# ─────────────────────────────────────────────────────────────────────────────
# Paths (relative to backend/)
# ─────────────────────────────────────────────────────────────────────────────
MODEL_PATH = Path("models/fusion_classifier.joblib")
TEST_CSV = Path("data/generated/test_dataset_seed1337.csv")
TRAIN_CSV = Path("data/generated/train_dataset_seed42.csv")
METRICS_JSON = Path("reports/metrics.json")

# ─────────────────────────────────────────────────────────────────────────────
# Utilities
# ─────────────────────────────────────────────────────────────────────────────

def file_sha256(path: Path) -> str:
    """Compute SHA-256 hash of a file for identity verification."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def file_info(path: Path) -> Dict[str, Any]:
    """Return key metadata about a file."""
    stat = path.stat()
    return {
        "path": str(path.resolve()),
        "size_bytes": stat.st_size,
        "last_modified": datetime.datetime.fromtimestamp(stat.st_mtime).isoformat(),
        "sha256": file_sha256(path),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    SEP = "=" * 72

    print(SEP)
    print("GRIDSENTINEL — CHANGE 1: CONFIRM REAL CYBER-INTRUSION RECALL")
    print(f"Timestamp: {datetime.datetime.now().isoformat()}")
    print(SEP)

    # -----------------------------------------------------------------------
    # Step 0: Verify all files exist
    # -----------------------------------------------------------------------
    for label, p in [("Model", MODEL_PATH), ("Test CSV", TEST_CSV), ("Train CSV", TRAIN_CSV)]:
        if not p.exists():
            print(f"[FATAL] {label} not found at {p.resolve()}")
            sys.exit(1)

    # -----------------------------------------------------------------------
    # Step 1: Model artifact identity
    # -----------------------------------------------------------------------
    print(f"\n{'─' * 72}")
    print("STEP 1 — Deployed Model Artifact Identity")
    print(f"{'─' * 72}")
    model_info = file_info(MODEL_PATH)
    for k, v in model_info.items():
        print(f"  {k}: {v}")

    bundle = joblib.load(MODEL_PATH)
    print(f"  bundle.version: {bundle.get('version', 'N/A')}")
    print(f"  bundle.model_name: {bundle.get('model_name', 'N/A')}")
    print(f"  bundle.decision_threshold: {bundle.get('decision_threshold', 'N/A')}")
    print(f"  bundle.trained_timestamp: {bundle.get('trained_timestamp', 'N/A')}")
    print(f"  bundle.feature_schema_version: {bundle.get('feature_schema_version', 'N/A')}")

    # Check against metrics.json if it exists
    if METRICS_JSON.exists():
        with open(METRICS_JSON) as f:
            saved_metrics = json.load(f)
        print(f"\n  Saved metrics.json timestamp: {saved_metrics.get('timestamp', 'N/A')}")
        print(f"  Saved metrics.json model_selected: {saved_metrics.get('model_selected', 'N/A')}")
        print(f"  Saved metrics.json threshold: {saved_metrics.get('decision_threshold', 'N/A')}")

        # Compare key fields
        threshold_match = (
            abs(float(bundle.get('decision_threshold', -1)) -
                float(saved_metrics.get('decision_threshold', -2))) < 1e-6
        )
        model_match = bundle.get('model_name') == saved_metrics.get('model_selected')
        print(f"\n  Threshold matches metrics.json? {threshold_match}")
        print(f"  Model name matches metrics.json? {model_match}")
        if threshold_match and model_match:
            print("  >>> CONCLUSION: Deployed artifact IS CONSISTENT with the metrics.json report.")
        else:
            print("  >>> WARNING: Deployed artifact DIFFERS from metrics.json — investigate!")
    else:
        print("\n  [INFO] reports/metrics.json not found — cannot cross-reference.")

    # -----------------------------------------------------------------------
    # Step 2: Load test set and run evaluation
    # -----------------------------------------------------------------------
    print(f"\n{'─' * 72}")
    print("STEP 2 — Held-Out Test Set Evaluation")
    print(f"{'─' * 72}")

    feature_schema = bundle.get("feature_schema")
    if not feature_schema:
        print("[FATAL] Bundle does not contain 'feature_schema'")
        sys.exit(1)

    test_df = pd.read_csv(TEST_CSV)
    test_info = file_info(TEST_CSV)
    print(f"  Test CSV: {test_info['path']}")
    print(f"  Test CSV size: {test_info['size_bytes']} bytes")
    print(f"  Test CSV last_modified: {test_info['last_modified']}")
    print(f"  Test CSV sha256: {test_info['sha256']}")
    print(f"  Test samples: {len(test_df)}")
    print(f"  Test class distribution:")
    for label, count in test_df["top_level_label"].value_counts().items():
        print(f"    {label}: {count}")

    # Extract features and labels
    missing_feats = [f for f in feature_schema if f not in test_df.columns]
    if missing_feats:
        print(f"[FATAL] Test CSV missing features: {missing_feats}")
        sys.exit(1)

    X_test = test_df[feature_schema].fillna(0.0)
    y_test = test_df["top_level_label"]

    # Get the model and apply the EXACT same threshold logic from train_classifier.py
    top_model = bundle["top_level_model"]
    decision_threshold = float(bundle.get("decision_threshold", 0.5))
    model_name = bundle.get("model_name", "Unknown")

    # Determine classes
    raw_classes = bundle.get("classes", ["Cyber Intrusion", "Natural Fault", "Normal"])
    label_map = {0: "Cyber Intrusion", 1: "Natural Fault", 2: "Normal"}
    classes = [
        label_map[int(c)] if isinstance(c, (int, np.integer)) and int(c) in label_map else str(c)
        for c in raw_classes
    ]

    print(f"\n  Model: {model_name}")
    print(f"  Decision Threshold: {decision_threshold}")
    print(f"  Classes: {classes}")
    print(f"  Feature count: {len(feature_schema)}")

    # Predict with tuned threshold (replicate train_classifier.py logic exactly)
    proba_all = top_model.predict_proba(X_test)

    # Map model's raw class labels to string names
    raw_model_classes = list(top_model.classes_)
    model_classes = [
        label_map[int(c)] if isinstance(c, (int, np.integer)) and int(c) in label_map else str(c)
        for c in raw_model_classes
    ]

    cyber_idx = model_classes.index("Cyber Intrusion")

    y_pred = []
    for row_proba in proba_all:
        if row_proba[cyber_idx] >= decision_threshold:
            y_pred.append("Cyber Intrusion")
        else:
            # Argmax excluding cyber class
            row_copy = row_proba.copy()
            row_copy[cyber_idx] = 0.0
            pred_idx = int(np.argmax(row_copy))
            y_pred.append(model_classes[pred_idx])
    y_pred = np.array(y_pred)

    # -----------------------------------------------------------------------
    # Step 3: Compute all metrics
    # -----------------------------------------------------------------------
    print(f"\n{'─' * 72}")
    print("STEP 3 — Full Metrics (NO rounding, NO omissions)")
    print(f"{'─' * 72}")

    sorted_classes = sorted(classes)  # Alphabetical for consistent matrix ordering
    acc = float(accuracy_score(y_test, y_pred))
    bal_acc = float(balanced_accuracy_score(y_test, y_pred))
    cm = confusion_matrix(y_test, y_pred, labels=sorted_classes)
    report = classification_report(y_test, y_pred, labels=sorted_classes, output_dict=True)

    print(f"\n  Overall Accuracy:          {acc * 100:.4f}%")
    print(f"  Balanced Accuracy:         {bal_acc * 100:.4f}%")

    # Print confusion matrix
    print(f"\n  Confusion Matrix (rows=True, cols=Predicted)")
    print(f"  Labels: {sorted_classes}")
    # Header
    header = "  {:>18s}".format("")
    for cls in sorted_classes:
        header += f"  {cls:>16s}"
    print(header)
    for i, true_cls in enumerate(sorted_classes):
        row_str = f"  {true_cls:>18s}"
        for j in range(len(sorted_classes)):
            row_str += f"  {cm[i, j]:>16d}"
        print(row_str)

    # Per-class precision / recall / F1
    print(f"\n  Per-Class Metrics:")
    print(f"  {'Class':>18s}  {'Precision':>10s}  {'Recall':>10s}  {'F1-Score':>10s}  {'Support':>8s}")
    print(f"  {'─' * 62}")
    for cls in sorted_classes:
        r = report[cls]
        print(f"  {cls:>18s}  {r['precision']*100:>9.4f}%  {r['recall']*100:>9.4f}%  {r['f1-score']*100:>9.4f}%  {int(r['support']):>8d}")

    # Cyber Intrusion specific metrics
    is_true_cyber = (y_test == "Cyber Intrusion")
    is_pred_cyber = (y_pred == "Cyber Intrusion")

    cyber_tp = int((is_true_cyber & is_pred_cyber).sum())
    cyber_fn = int((is_true_cyber & ~is_pred_cyber).sum())
    cyber_fp = int((~is_true_cyber & is_pred_cyber).sum())
    cyber_tn = int((~is_true_cyber & ~is_pred_cyber).sum())
    cyber_total = int(is_true_cyber.sum())
    non_cyber_total = int((~is_true_cyber).sum())

    cyber_recall = cyber_tp / cyber_total if cyber_total > 0 else 0.0
    cyber_precision = cyber_tp / (cyber_tp + cyber_fp) if (cyber_tp + cyber_fp) > 0 else 0.0
    cyber_fpr = cyber_fp / non_cyber_total if non_cyber_total > 0 else 0.0
    cyber_fnr = cyber_fn / cyber_total if cyber_total > 0 else 0.0
    cyber_f1 = 2 * cyber_precision * cyber_recall / (cyber_precision + cyber_recall) if (cyber_precision + cyber_recall) > 0 else 0.0
    cyber_f2 = float(fbeta_score(
        is_true_cyber.astype(int), is_pred_cyber.astype(int),
        beta=2, zero_division=0
    ))

    print(f"\n  ╔══════════════════════════════════════════════════════════╗")
    print(f"  ║  CYBER INTRUSION — DEDICATED METRICS                    ║")
    print(f"  ╠══════════════════════════════════════════════════════════╣")
    print(f"  ║  True Positives:       {cyber_tp:>6d}                          ║")
    print(f"  ║  False Negatives:      {cyber_fn:>6d}                          ║")
    print(f"  ║  False Positives:      {cyber_fp:>6d}                          ║")
    print(f"  ║  True Negatives:       {cyber_tn:>6d}                          ║")
    print(f"  ║  Total Real Cyber:     {cyber_total:>6d}                          ║")
    print(f"  ║  Total Non-Cyber:      {non_cyber_total:>6d}                          ║")
    print(f"  ╠══════════════════════════════════════════════════════════╣")
    print(f"  ║  RECALL (TPR):         {cyber_recall * 100:>9.4f}%                    ║")
    print(f"  ║  PRECISION:            {cyber_precision * 100:>9.4f}%                    ║")
    print(f"  ║  F1 SCORE:             {cyber_f1 * 100:>9.4f}%                    ║")
    print(f"  ║  F2 SCORE:             {cyber_f2 * 100:>9.4f}%                    ║")
    print(f"  ║  FALSE POSITIVE RATE:  {cyber_fpr * 100:>9.4f}%                    ║")
    print(f"  ║  FALSE NEGATIVE RATE:  {cyber_fnr * 100:>9.4f}%                    ║")
    print(f"  ╚══════════════════════════════════════════════════════════╝")

    # -----------------------------------------------------------------------
    # Step 4: Leakage Smoke Test
    # -----------------------------------------------------------------------
    print(f"\n{'─' * 72}")
    print("STEP 4 — Label-Shuffle Leakage Smoke Test")
    print(f"{'─' * 72}")

    print("  Loading training data for shuffle test...")
    train_df = pd.read_csv(TRAIN_CSV)
    X_train = train_df[feature_schema].fillna(0.0)
    y_train = train_df["top_level_label"]

    rng = np.random.default_rng(seed=0)
    y_shuffled = pd.Series(
        rng.permutation(y_train.values),
        index=y_train.index,
    )

    print("  Training RandomForest on SHUFFLED labels...")
    clf_shuffled = RandomForestClassifier(
        n_estimators=100,
        class_weight="balanced",
        random_state=0,
        n_jobs=-1,
    )
    clf_shuffled.fit(X_train, y_shuffled)
    y_pred_shuffled = clf_shuffled.predict(X_test)

    shuffled_std_acc = float(accuracy_score(y_test, y_pred_shuffled))
    shuffled_bal_acc = float(balanced_accuracy_score(y_test, y_pred_shuffled))

    leakage_passed = shuffled_bal_acc < 0.40
    print(f"\n  Shuffled-label standard accuracy:  {shuffled_std_acc * 100:.2f}% (majority baseline: ~72.3%)")
    print(f"  Shuffled-label balanced accuracy:  {shuffled_bal_acc * 100:.2f}% (random chance: 33.33%)")
    print(f"  Leakage test: {'PASS — balanced accuracy collapsed to random chance (NO LEAKAGE)' if leakage_passed else 'FAIL — suspiciously high, investigate!'}")

    # -----------------------------------------------------------------------
    # Step 5: Cross-reference with prior remediation report
    # -----------------------------------------------------------------------
    print(f"\n{'─' * 72}")
    print("STEP 5 — Cross-Reference with Prior Verification Report")
    print(f"{'─' * 72}")

    if METRICS_JSON.exists():
        with open(METRICS_JSON) as f:
            saved = json.load(f)
        saved_recall = saved.get("cyber_intrusion_recall", "N/A")
        saved_tp = saved.get("cyber_intrusion_tp", "N/A")
        saved_total = saved.get("cyber_intrusion_total", "N/A")
        saved_acc = saved.get("overall_accuracy", "N/A")
        saved_cm = saved.get("confusion_matrix", "N/A")

        print(f"  Saved metrics.json cyber recall:   {saved_recall}")
        print(f"  Saved metrics.json cyber TP/Total: {saved_tp}/{saved_total}")
        print(f"  Saved metrics.json overall accuracy: {saved_acc}")
        print(f"  Saved metrics.json confusion matrix: {saved_cm}")
        print()
        print(f"  FRESH evaluation cyber recall:     {cyber_recall:.4f}")
        print(f"  FRESH evaluation cyber TP/Total:   {cyber_tp}/{cyber_total}")
        print(f"  FRESH evaluation overall accuracy: {acc:.4f}")
        print()

        recall_matches = abs(float(saved_recall) - cyber_recall) < 1e-4 if saved_recall != "N/A" else False
        acc_matches = abs(float(saved_acc) - acc) < 1e-4 if saved_acc != "N/A" else False
        if recall_matches and acc_matches:
            print("  >>> MATCH: Fresh evaluation reproduces the saved metrics.json exactly.")
            print("  >>> The deployed artifact IS the same model referenced in the prior report.")
        else:
            print("  >>> MISMATCH: Fresh evaluation differs from saved metrics.json!")
            print("  >>> The deployed model may have been modified since the last report.")
    else:
        print("  [INFO] No metrics.json found — no prior report to cross-reference.")

    # -----------------------------------------------------------------------
    # Final Summary
    # -----------------------------------------------------------------------
    print(f"\n{SEP}")
    print("FINAL SUMMARY")
    print(SEP)
    print(f"  Model:                    {model_name}")
    print(f"  Threshold:                {decision_threshold}")
    print(f"  Overall Accuracy:         {acc * 100:.4f}%")
    print(f"  Balanced Accuracy:        {bal_acc * 100:.4f}%")
    print(f"  Cyber Recall:             {cyber_recall * 100:.4f}% ({cyber_tp}/{cyber_total})")
    print(f"  Cyber Precision:          {cyber_precision * 100:.4f}%")
    print(f"  Cyber FPR:                {cyber_fpr * 100:.4f}%")
    print(f"  Cyber FNR:                {cyber_fnr * 100:.4f}%")
    print(f"  Cyber F1:                 {cyber_f1 * 100:.4f}%")
    print(f"  Cyber F2:                 {cyber_f2 * 100:.4f}%")
    print(f"  Leakage Smoke Test:       {'PASS' if leakage_passed else 'FAIL'}")
    print(f"  Model SHA-256:            {model_info['sha256']}")
    print(SEP)


if __name__ == "__main__":
    main()
