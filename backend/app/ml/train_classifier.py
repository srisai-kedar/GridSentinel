"""
train_classifier.py
-------------------
Trains and evaluates the GridSentinel Cyber-Physical Fusion Classifier.

Architecture:
  Stage 1 (Primary Triage):
    RandomForestClassifier (3-class: "Normal", "Natural Fault", "Cyber Intrusion")
    - Justification: Random Forest delivers sub-millisecond inference latency (essential
      for real-time SCADA polling loops), handles non-linear cross-correlations between
      network traffic metrics and physical residuals, and provides robust balanced class
      weighting without gradient instability.
  Stage 2 (Forensic Subtyping):
    RandomForestClassifier (3-class: "data_injection", "command_injection", "replay")
    - Justification: A two-stage hierarchical model decouples the primary operational triage
      from forensic subtyping, ensuring high-precision attack attribution without
      diluting the physics-vs-cyber boundary.

Outputs:
  - models/fusion_classifier.joblib
  - reports/confusion_matrix.png
  - reports/metrics.json
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Tuple

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
    f1_score,
    precision_score,
    recall_score,
)

from app.ml.feature_engineering import FEATURE_SCHEMA


def load_dataset(csv_path: str) -> Tuple[pd.DataFrame, pd.Series, pd.Series]:
    """Load and validate dataset CSV against FEATURE_SCHEMA."""
    df = pd.read_csv(csv_path)

    # Validate all feature columns exist
    missing = [f for f in FEATURE_SCHEMA if f not in df.columns]
    if missing:
        raise ValueError(f"CSV {csv_path} is missing required feature columns: {missing}")

    X = df[FEATURE_SCHEMA].copy()
    y_top = df["top_level_label"].copy()
    y_sub = df["subtype_label"].copy()

    # Fill any inadvertent NaNs with 0.0
    X = X.fillna(0.0)

    return X, y_top, y_sub


def train_and_evaluate(
    train_csv: str = "data/generated/train_dataset_seed42.csv",
    test_csv: str = "data/generated/test_dataset_seed1337.csv",
    model_out: str = "models/fusion_classifier.joblib",
    report_dir: str = "reports",
) -> Dict[str, Any]:
    """
    Train fusion classifier on train_csv and evaluate on held-out test_csv.
    """
    print(f"\n[Trainer] Loading training set from {train_csv}...")
    X_train, y_top_train, y_sub_train = load_dataset(train_csv)
    print(f"  Training samples: {len(X_train)} rows across {len(FEATURE_SCHEMA)} features")
    print(f"  Training class distribution:\n{y_top_train.value_counts()}")

    print(f"\n[Trainer] Loading held-out test set from {test_csv}...")
    X_test, y_top_test, y_sub_test = load_dataset(test_csv)
    print(f"  Test samples: {len(X_test)} rows")
    print(f"  Test class distribution:\n{y_top_test.value_counts()}")

    # -----------------------------------------------------------------------
    # Stage 1: Primary 3-Class Triage Model
    # -----------------------------------------------------------------------
    print("\n[Trainer] Training Primary 3-Way Triage Model (Random Forest)...")
    top_model = RandomForestClassifier(
        n_estimators=100,
        max_depth=12,
        class_weight="balanced",
        random_state=42,
        n_jobs=-1,
    )
    top_model.fit(X_train, y_top_train)

    # -----------------------------------------------------------------------
    # Stage 2: Secondary Cyber Subtype Model
    # -----------------------------------------------------------------------
    print("[Trainer] Training Secondary Forensic Cyber Subtyping Model...")
    cyber_mask_train = y_top_train == "Cyber Intrusion"
    X_train_cyber = X_train[cyber_mask_train]
    y_sub_train_cyber = y_sub_train[cyber_mask_train]

    subtype_model = RandomForestClassifier(
        n_estimators=100,
        max_depth=10,
        class_weight="balanced",
        random_state=42,
        n_jobs=-1,
    )
    subtype_model.fit(X_train_cyber, y_sub_train_cyber)

    # -----------------------------------------------------------------------
    # Evaluation on Held-Out Test Set
    # -----------------------------------------------------------------------
    print("\n[Trainer] Evaluating on Held-Out Test Set...")
    y_top_pred = top_model.predict(X_test)
    y_top_proba = top_model.predict_proba(X_test)

    acc = float(accuracy_score(y_top_test, y_top_pred))
    classes = sorted(list(top_model.classes_))
    cm = confusion_matrix(y_top_test, y_top_pred, labels=classes)

    clf_report = classification_report(y_top_test, y_top_pred, output_dict=True)

    # Compute False Positive Rate specifically for "Cyber Intrusion"
    # FPR = (Normal/Fault classified as Cyber) / (Total True Normal + True Fault)
    is_true_cyber = (y_top_test == "Cyber Intrusion")
    is_pred_cyber = (y_top_pred == "Cyber Intrusion")

    total_non_cyber = int((~is_true_cyber).sum())
    false_positives_cyber = int(((~is_true_cyber) & is_pred_cyber).sum())
    fpr_cyber = float(false_positives_cyber / total_non_cyber) if total_non_cyber > 0 else 0.0

    print(f"\n=======================================================")
    print(f"EVALUATION METRICS (HELD-OUT TEST SET):")
    print(f"=======================================================")
    print(f"Overall Accuracy:                  {acc * 100:.2f}%")
    print(f"Cyber Intrusion False Positive Rate: {fpr_cyber * 100:.2f}% ({false_positives_cyber}/{total_non_cyber})")
    print(f"Confusion Matrix (labels={classes}):\n{cm}")
    print("\nPer-class Classification Report:")
    for cls in classes:
        p = clf_report[cls]["precision"]
        r = clf_report[cls]["recall"]
        f1 = clf_report[cls]["f1-score"]
        supp = clf_report[cls]["support"]
        print(f"  {cls:<18} Precision: {p*100:.2f}% | Recall: {r*100:.2f}% | F1: {f1*100:.2f}% | Support: {supp}")

    # Evaluate Subtyping on Cyber instances in test set
    cyber_mask_test = y_top_test == "Cyber Intrusion"
    if cyber_mask_test.sum() > 0:
        X_test_cyber = X_test[cyber_mask_test]
        y_sub_test_cyber = y_sub_test[cyber_mask_test]
        y_sub_pred_cyber = subtype_model.predict(X_test_cyber)
        sub_acc = float(accuracy_score(y_sub_test_cyber, y_sub_pred_cyber))
        print(f"\nCyber Subtype Accuracy:            {sub_acc * 100:.2f}%")
    else:
        sub_acc = 0.0

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
        title="GridSentinel Fusion Classifier Confusion Matrix",
        ylabel="True Class",
        xlabel="Predicted Class",
    )
    plt.setp(ax.get_xticklabels(), rotation=30, ha="right", rotation_mode="anchor")

    # Loop over data dimensions and create text annotations
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
        "overall_accuracy": round(acc, 4),
        "cyber_intrusion_fpr": round(fpr_cyber, 4),
        "cyber_subtype_accuracy": round(sub_acc, 4),
        "classes": classes,
        "confusion_matrix": cm.tolist(),
        "classification_report": clf_report,
        "train_samples_count": len(X_train),
        "test_samples_count": len(X_test),
        "feature_schema_version": "1.0.0",
        "feature_count": len(FEATURE_SCHEMA),
    }

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
        "top_level_model": top_model,
        "subtype_model": subtype_model,
        "feature_schema": FEATURE_SCHEMA,
        "classes": classes,
        "subtype_classes": list(subtype_model.classes_),
        "version": "1.0.0",
        "trained_timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "metrics_summary": {
            "accuracy": acc,
            "cyber_fpr": fpr_cyber,
            "subtype_accuracy": sub_acc,
        },
    }

    joblib.dump(bundle, model_file_path)
    print(f"[Trainer] Saved Model Bundle to {model_file_path}")

    return metrics_data


def main_cli():
    parser = argparse.ArgumentParser(description="GridSentinel Model Trainer")
    parser.add_argument("--train", type=str, default="data/generated/train_dataset_seed42.csv", help="Train CSV")
    parser.add_argument("--test", type=str, default="data/generated/test_dataset_seed1337.csv", help="Test CSV")
    parser.add_argument("--out", type=str, default="models/fusion_classifier.joblib", help="Model joblib path")
    parser.add_argument("--report", type=str, default="reports", help="Reports dir")

    args = parser.parse_args()
    train_and_evaluate(
        train_csv=args.train,
        test_csv=args.test,
        model_out=args.out,
        report_dir=args.report,
    )


if __name__ == "__main__":
    main_cli()
