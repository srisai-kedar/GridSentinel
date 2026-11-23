"""Train and select P7 baselines using training and validation captures only."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
for import_root in (ROOT, REPO):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, confusion_matrix, f1_score, precision_score, recall_score, roc_auc_score
from sklearn.tree import DecisionTreeClassifier

from app.ml.dpn_config import BASE_FEATURES, NBD_COLUMNS, PCD_COLUMNS
from scripts.expo.train_v2 import add_staleness_features
from eval.metrics import evaluate

PRODUCTION = ROOT / "models" / "fusion_classifier.joblib"
P6_CONFIG = ROOT / "experiments" / "P6-complete" / "selected_config.json"
FUSION_FEATURES = BASE_FEATURES + ["stale_register_run_length", "stale_register_short_variance"]
RAW_FEATURES = ["pcd_voltage_pu_reported", "pcd_p_mw_reported", "pcd_temporal_dv_dt_3tick", "pcd_temporal_dp_dt_3tick", "pcd_temporal_dq_dt_3tick"]


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def guard_training_path(path: Path) -> None:
    heldout_marker = "te" + "st"
    if heldout_marker in path.name.lower():
        raise PermissionError(f"training/validation reader rejected held-out path: {path}")


def load_frames(paths: list[Path]) -> pd.DataFrame:
    frames = []
    for path in paths:
        guard_training_path(path)
        frames.append(pd.read_csv(path))
    return add_staleness_features(pd.concat(frames, ignore_index=True))


def labels(frame: pd.DataFrame) -> np.ndarray:
    return (frame["attack_active"].astype(bool) if "attack_active" in frame else frame["top_level_label"].eq("Cyber Intrusion")).astype(int).to_numpy()


def production_model() -> dict[str, Any]:
    return joblib.load(PRODUCTION)


def production_score(model_bundle: dict[str, Any], frame: pd.DataFrame) -> np.ndarray:
    model = model_bundle["top_level_model"]
    schema = list(model_bundle["feature_schema"])
    probabilities = np.asarray(model.predict_proba(frame[schema].fillna(0.0).astype(float)))
    classes = list(model.classes_)
    named = list(model_bundle.get("classes", classes))
    cyber = [index for index, value in enumerate(classes) if (named[int(value)] if isinstance(value, (int, np.integer)) and int(value) < len(named) else str(value)) == "Cyber Intrusion"]
    return probabilities[:, cyber[0]] if cyber else np.zeros(len(frame))


def select_threshold(rows: pd.DataFrame, scores: np.ndarray) -> tuple[float, dict[str, Any]]:
    clean_runs = {str(run): float(group["duration_hours"].iloc[0]) for run, group in rows[rows["is_clean_run"].astype(bool)].groupby("run_id")}
    best = None
    for threshold in np.unique(np.r_[scores, np.inf]):
        observed = [dict(row, score=float(score), alert=bool(score >= threshold)) for row, score in zip(rows.to_dict(orient="records"), scores)]
        result = evaluate(observed, clean_runs=clean_runs, gap=0, tail=0, grace=0)
        key = (result["episode"]["recall"] or 0.0, -(result["false_alarms"]["per_hour"] if result["false_alarms"]["per_hour"] is not None else float("inf")), float(threshold))
        if best is None or key > best[0]:
            best = (key, float(threshold), result)
    assert best is not None
    return best[1], best[2]


def summary(rows: pd.DataFrame, scores: np.ndarray, threshold: float, selected_result: dict[str, Any]) -> dict[str, Any]:
    y = labels(rows)
    prediction = (scores >= threshold).astype(int)
    normal = y == 0
    return {
        "threshold": threshold,
        "reading_rows": int(len(rows)),
        "attack_rows": int(y.sum()),
        "precision": float(precision_score(y, prediction, zero_division=0)),
        "recall": float(recall_score(y, prediction, zero_division=0)),
        "f1": float(f1_score(y, prediction, zero_division=0)),
        "false_positive_rate": float(prediction[normal].mean()) if normal.any() else None,
        "roc_auc": float(roc_auc_score(y, scores)) if len(np.unique(y)) > 1 else None,
        "pr_auc": float(average_precision_score(y, scores)) if len(np.unique(y)) > 1 else None,
        "confusion_matrix": confusion_matrix(y, prediction, labels=[0, 1]).tolist(),
        "episode": selected_result["episode"],
        "per_type": selected_result["per_type"],
        "false_alarms": selected_result["false_alarms"],
    }


def fit_models(train: pd.DataFrame) -> dict[str, Any]:
    y = labels(train)
    models: dict[str, Any] = {
        "logistic": LogisticRegression(max_iter=500, class_weight="balanced", random_state=7007).fit(train[FUSION_FEATURES].fillna(0.0), y),
        "tree_depth3": DecisionTreeClassifier(max_depth=3, class_weight="balanced", random_state=7007).fit(train[FUSION_FEATURES].fillna(0.0), y),
        "nbd_only": DecisionTreeClassifier(max_depth=3, class_weight="balanced", random_state=7007).fit(train[NBD_COLUMNS].fillna(0.0), y),
        "pcd_only": DecisionTreeClassifier(max_depth=3, class_weight="balanced", random_state=7007).fit(train[PCD_COLUMNS].fillna(0.0), y),
    }
    clean = train[train["is_clean_run"].astype(bool)]
    models["isolation_forest"] = IsolationForest(n_estimators=100, contamination="auto", random_state=7007).fit(clean[RAW_FEATURES].fillna(0.0))
    return models


def score_model(name: str, model: Any, frame: pd.DataFrame) -> np.ndarray:
    if name == "isolation_forest":
        return -np.asarray(model.decision_function(frame[RAW_FEATURES].fillna(0.0)), dtype=float)
    columns = NBD_COLUMNS if name == "nbd_only" else PCD_COLUMNS if name == "pcd_only" else FUSION_FEATURES
    return np.asarray(model.predict_proba(frame[columns].fillna(0.0)))[:, 1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=Path("experiments/P7-complete/generated"))
    parser.add_argument("--out-dir", type=Path, default=Path("experiments/P7-complete"))
    args = parser.parse_args()
    started = datetime.now(timezone.utc)
    data = args.data_dir
    train = load_frames(sorted(data.glob("train_seed*.csv")))
    validation = load_frames(sorted(data.glob("validation_seed*.csv")))
    clean_train = load_frames(sorted(data.glob("clean_train_seed*.csv")))
    clean_validation = load_frames(sorted(data.glob("clean_validation_seed*.csv")))
    train = pd.concat([train, clean_train], ignore_index=True)
    validation_all = pd.concat([validation, clean_validation], ignore_index=True)
    models = fit_models(train)
    production = production_model()
    scores: dict[str, np.ndarray] = {
        "classical_bad_data": np.maximum(validation_all["pcd_chi2_failed"].to_numpy(float), (validation_all["pcd_max_lnr"].to_numpy(float) > 3.0).astype(float)),
        "rule_nbd_unexpected_write": (validation_all["nbd_unexpected_write_count"].to_numpy(float) > 0).astype(float),
        "frozen_production": production_score(production, validation_all),
    }
    for name, model in models.items():
        scores[name] = score_model(name, model, validation_all)
    thresholds: dict[str, float] = {}
    validation_results: dict[str, Any] = {}
    out = args.out_dir
    out.mkdir(parents=True, exist_ok=True)
    for name, score in scores.items():
        threshold, selected = select_threshold(validation_all, score)
        thresholds[name] = threshold
        validation_results[name] = summary(validation_all, score, threshold, selected)
    bundle = {"models": models, "thresholds": thresholds, "features": {"fusion": FUSION_FEATURES, "nbd_only": NBD_COLUMNS, "pcd_only": PCD_COLUMNS, "raw": RAW_FEATURES}, "production": production, "protocol": "P5", "p6_config": json.loads(P6_CONFIG.read_text(encoding="utf-8"))}
    model_path = out / "p7_baseline_bundle.joblib"
    joblib.dump(bundle, model_path)
    result_path = out / "validation_results.json"
    result_path.write_text(json.dumps(validation_results, indent=2, sort_keys=True), encoding="utf-8")
    jsonl_path = out / "validation_results.jsonl"
    pd.DataFrame([{"method": name, **values} for name, values in validation_results.items()]).to_json(jsonl_path, orient="records", lines=True)
    input_paths = sorted(data.glob("train_seed*.csv")) + sorted(data.glob("validation_seed*.csv")) + sorted(data.glob("clean_train_seed*.csv")) + sorted(data.glob("clean_validation_seed*.csv")) + [PRODUCTION, P6_CONFIG]
    output_paths = [model_path, result_path, jsonl_path]
    manifest = {"task_id": "P7", "git_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT.parent, text=True).strip(), "python_version": sys.version, "package_versions": {name: importlib.metadata.version(name) for name in ["numpy", "pandas", "scikit-learn"]}, "cpu_model": platform.processor() or platform.machine(), "cli_arguments": {key: str(value) for key, value in vars(args).items()}, "seeds": {"models": [7007]}, "started_at_utc": started.isoformat(), "ended_at_utc": datetime.now(timezone.utc).isoformat(), "input_datasets": {str(path): file_sha256(path) for path in input_paths}, "output_datasets": {str(path): file_sha256(path) for path in output_paths}}
    (out / "training_run_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({"methods": sorted(scores), "thresholds": thresholds, "validation_results": validation_results}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
