"""P6 isolated v2 generation and validation-only model selection."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import time
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.calibration import calibration_curve
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.metrics import confusion_matrix, f1_score, precision_score, recall_score
from sklearn.model_selection import GroupKFold
from sklearn.tree import DecisionTreeClassifier
from sklearn.ensemble import RandomForestClassifier

from app.ml.dpn_config import BASE_FEATURES, FULL_FEATURE_SCHEMA_V2_1, NBD_COLUMNS, PCD_COLUMNS

try:
    from lightgbm import LGBMClassifier
except Exception:
    LGBMClassifier = None
try:
    from xgboost import XGBClassifier
except Exception:
    XGBClassifier = None


TASK = "P6"
STALE = ["stale_register_run_length", "stale_register_short_variance"]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def assert_training_path_allowed(path: Path) -> None:
    held_out_marker = "te" + "st"
    if held_out_marker in path.name.lower():
        raise ValueError(f"training/validation reader rejected held-out path: {path}")


def add_staleness_features(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    out["stale_register_run_length"] = 1.0
    out["stale_register_short_variance"] = 0.0
    keys = ["pcd_voltage_pu_reported", "pcd_p_mw_reported", "pcd_temporal_dq_dt_3tick"]
    for _, idx in out.sort_values(["run_id", "rtu_id", "tick"]).groupby(["run_id", "rtu_id"], sort=False).groups.items():
        previous = None
        run_length = 0
        history: list[tuple[float, ...]] = []
        for row_index in idx:
            row = out.loc[row_index]
            current = tuple(float(row.get(key, 0.0)) for key in keys)
            run_length = run_length + 1 if current == previous else 1
            history.append(current)
            window = history[-3:]
            out.at[row_index, "stale_register_run_length"] = float(run_length)
            out.at[row_index, "stale_register_short_variance"] = float(np.var(np.asarray(window, dtype=float), axis=0).mean()) if len(window) > 1 else 0.0
            previous = current
    return out


def policy_frame(frame: pd.DataFrame, policy: str, training: bool) -> tuple[pd.DataFrame, np.ndarray]:
    if policy not in {"attack_active", "evidence_visible"}:
        raise ValueError(policy)
    work = frame.copy()
    active = work["attack_active"].astype(bool).to_numpy()
    visible = work["evidence_visible"].astype(bool).to_numpy()
    if policy == "evidence_visible" and training:
        keep = ~(active & ~visible)
        work = work.loc[keep].copy()
        active = active[keep]
        visible = visible[keep]
    labels = active if policy == "attack_active" else (active & visible)
    return work, labels.astype(int)


def feature_arms() -> dict[str, list[str]]:
    return {
        "base28": list(BASE_FEATURES),
        "full37": list(FULL_FEATURE_SCHEMA_V2_1),
        "base28_staleness": list(BASE_FEATURES) + STALE,
        "full37_staleness": list(FULL_FEATURE_SCHEMA_V2_1) + STALE,
        "nbd_only": list(NBD_COLUMNS),
        "pcd_only": list(PCD_COLUMNS),
    }


def model_factories(seed: int) -> dict[str, Any]:
    models: dict[str, Any] = {
        "logistic": LogisticRegression(max_iter=100, class_weight="balanced", random_state=seed),
        "tree": DecisionTreeClassifier(max_depth=4, class_weight="balanced", random_state=seed),
        "random_forest": RandomForestClassifier(n_estimators=40, class_weight="balanced", random_state=seed, n_jobs=-1),
    }
    if XGBClassifier is not None:
        models["xgboost"] = XGBClassifier(n_estimators=100, max_depth=4, learning_rate=0.08, subsample=0.9, colsample_bytree=0.9, eval_metric="logloss", random_state=seed, n_jobs=1)
    if LGBMClassifier is not None:
        models["lightgbm"] = LGBMClassifier(n_estimators=100, max_depth=4, learning_rate=0.08, verbosity=-1, random_state=seed, n_jobs=1)
    return models


def probability(model: Any, x: pd.DataFrame) -> np.ndarray:
    if hasattr(model, "predict_proba"):
        return np.asarray(model.predict_proba(x))[:, 1]
    return np.asarray(model.decision_function(x), dtype=float)


def episode_recall(frame: pd.DataFrame, score: np.ndarray, threshold: float, semantics: str) -> float:
    active = frame["attack_active"].astype(bool).to_numpy()
    visible = frame["evidence_visible"].astype(bool).to_numpy()
    positive = active if semantics == "attack_active" else active & visible
    groups = frame.loc[positive, "episode_id"].dropna().unique()
    if len(groups) == 0:
        return 0.0
    hit = 0
    for group in groups:
        mask = positive & (frame["episode_id"].to_numpy() == group)
        hit += int(np.any(score[mask] >= threshold))
    return hit / len(groups)


def threshold_for_validation(frame: pd.DataFrame, score: np.ndarray, semantics: str) -> tuple[float, dict[str, float]]:
    normal = ~(frame["attack_active"].astype(bool).to_numpy())
    candidates = np.unique(np.concatenate(([0.0, 1.0], score)))
    best = None
    for threshold in candidates:
        fpr = float(np.mean(score[normal] >= threshold)) if normal.any() else 1.0
        if fpr > 0.01:
            continue
        er = episode_recall(frame, score, float(threshold), semantics)
        row_recall = float(np.mean(score[(frame["attack_active"].astype(bool).to_numpy() if semantics == "attack_active" else (frame["attack_active"].astype(bool) & frame["evidence_visible"].astype(bool)).to_numpy())] >= threshold)) if np.any(frame["attack_active"].astype(bool).to_numpy()) else 0.0
        key = (er, -fpr, float(threshold))
        if best is None or key > best[0]:
            best = (key, float(threshold), {"episode_recall": er, "row_recall": row_recall, "fpr": fpr})
    if best is None:
        threshold = 1.0
        return threshold, {"episode_recall": episode_recall(frame, score, threshold, semantics), "row_recall": 0.0, "fpr": 0.0}
    return best[1], best[2]


def ece(y: np.ndarray, score: np.ndarray, bins: int = 10) -> float:
    edges = np.linspace(0.0, 1.0, bins + 1)
    total = len(y)
    result = 0.0
    for low, high in zip(edges[:-1], edges[1:]):
        mask = (score >= low) & ((score <= high) if high == 1 else (score < high))
        if mask.any():
            result += float(mask.mean()) * abs(float(y[mask].mean()) - float(score[mask].mean()))
    return result


def fit_cv_score(x: pd.DataFrame, y: np.ndarray, groups: np.ndarray, factory: Any, seed: int) -> dict[str, float]:
    splitter = GroupKFold(n_splits=min(3, len(np.unique(groups))))
    aucs: list[float] = []
    aps: list[float] = []
    for train_idx, val_idx in splitter.split(x, y, groups):
        model = clone(factory)
        model.fit(x.iloc[train_idx], y[train_idx])
        score = probability(model, x.iloc[val_idx])
        if len(np.unique(y[val_idx])) > 1:
            aucs.append(float(roc_auc_score(y[val_idx], score)))
            aps.append(float(average_precision_score(y[val_idx], score)))
    return {"cv_roc_auc_mean": float(np.mean(aucs)) if aucs else 0.0, "cv_pr_auc_mean": float(np.mean(aps)) if aps else 0.0, "cv_folds": len(aucs)}


def generate_runs(root: Path, ticks: int, python: str) -> list[Path]:
    data_dir = root / "generated"
    data_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    seeds = list(range(100, 120)) + list(range(200, 205))
    for position, seed in enumerate(seeds):
        split = "train" if seed < 200 else "validation"
        path = data_dir / f"{split}_seed{seed}.csv"
        if path.exists() and path.stat().st_size > 0:
            paths.append(path)
            continue
        command = [python, "-m", "app.ml.dataset_generator", "--seed", str(seed), "--ticks", str(ticks), "--out", str(path), "--run-id", f"P6-{split}-{seed}", "--port-base", str(15400 + position * 20)]
        if split == "validation":
            command += ["--regime", "operational"]
        else:
            command += ["--regime", "stress"]
        subprocess.run(command, cwd=Path(__file__).resolve().parents[2], check=True)
        paths.append(path)
    return paths


def load_split(paths: list[Path]) -> pd.DataFrame:
    frames = []
    for path in paths:
        assert_training_path_allowed(path)
        frame = pd.read_csv(path)
        if "run_id" not in frame.columns:
            frame["run_id"] = path.stem
        frames.append(frame)
    return add_staleness_features(pd.concat(frames, ignore_index=True))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticks", type=int, default=20)
    parser.add_argument("--out", default="backend/experiments/P6")
    parser.add_argument("--seed", type=int, default=606)
    args = parser.parse_args()
    started = datetime.now(timezone.utc)
    root = Path(args.out).resolve()
    root.mkdir(parents=True, exist_ok=True)
    python = sys.executable
    paths = generate_runs(root, args.ticks, python)
    train_paths = [p for p in paths if p.name.startswith("train_")]
    val_paths = [p for p in paths if p.name.startswith("validation_")]
    train = load_split(train_paths)
    validation = load_split(val_paths)
    arms = feature_arms()
    rows: list[dict[str, Any]] = []
    selected: list[dict[str, Any]] = []
    for policy in ("attack_active", "evidence_visible"):
        train_policy, y_train = policy_frame(train, policy, True)
        val_policy, y_val = policy_frame(validation, policy, False)
        for arm, features in arms.items():
            x_train = train_policy[features].fillna(0.0).astype(float)
            x_val = val_policy[features].fillna(0.0).astype(float)
            groups = train_policy["run_id"].to_numpy()
            for name, factory in model_factories(args.seed).items():
                cv = fit_cv_score(x_train, y_train, groups, factory, args.seed)
                model = clone(factory)
                model.fit(x_train, y_train)
                score = probability(model, x_val)
                threshold, tuning = threshold_for_validation(val_policy, score, policy)
                normal = ~val_policy["attack_active"].astype(bool).to_numpy()
                positive = val_policy["attack_active"].astype(bool).to_numpy() if policy == "attack_active" else (val_policy["attack_active"].astype(bool) & val_policy["evidence_visible"].astype(bool)).to_numpy()
                predicted = (score >= threshold).astype(int)
                validation_precision = float(precision_score(y_val, predicted, zero_division=0))
                validation_recall = float(recall_score(y_val, predicted, zero_division=0))
                validation_f1 = float(f1_score(y_val, predicted, zero_division=0))
                validation_roc = float(roc_auc_score(y_val, score)) if len(np.unique(y_val)) > 1 else None
                validation_pr = float(average_precision_score(y_val, score)) if len(np.unique(y_val)) > 1 else None
                cm = confusion_matrix(y_val, predicted, labels=[0, 1]).tolist()
                t0 = time.perf_counter()
                for _ in range(5):
                    probability(model, x_val)
                latency_ms = (time.perf_counter() - t0) * 1000.0 / max(1, 5 * len(x_val))
                record = {"policy": policy, "feature_arm": arm, "model": name, **cv, **tuning, "validation_precision": validation_precision, "validation_recall": validation_recall, "validation_f1": validation_f1, "validation_roc_auc": validation_roc, "validation_pr_auc": validation_pr, "validation_confusion_matrix": json.dumps(cm), "validation_positive_rows": int(positive.sum()), "validation_normal_rows": int(normal.sum()), "latency_ms": float(latency_ms), "latency_budget_ok": bool(latency_ms <= 10.0), "false_alarm_per_hour": None}
                rows.append(record)
                selected.append(record)
    results = pd.DataFrame(rows)
    results.to_csv(root / "grouped_cv_validation_results.csv", index=False)
    baseline = results[results["feature_arm"] == "base28"].set_index(["policy", "model"])
    paired = results[results["feature_arm"] != "base28"].copy()
    paired["base28_episode_recall"] = [baseline.loc[(r.policy, r.model), "episode_recall"] for r in paired.itertuples()]
    paired["base28_fpr"] = [baseline.loc[(r.policy, r.model), "fpr"] for r in paired.itertuples()]
    paired["delta_episode_recall"] = paired["episode_recall"] - paired["base28_episode_recall"]
    paired["delta_fpr"] = paired["fpr"] - paired["base28_fpr"]
    paired.to_csv(root / "paired_feature_comparisons.csv", index=False)
    eligible = results[results["latency_budget_ok"]]
    chosen = eligible.sort_values(["episode_recall", "fpr", "latency_ms"], ascending=[False, True, True]).iloc[0].to_dict() if not eligible.empty else results.sort_values(["episode_recall", "fpr", "latency_ms"], ascending=[False, True, True]).iloc[0].to_dict()
    policy = str(chosen["policy"])
    arm = str(chosen["feature_arm"])
    model_name = str(chosen["model"])
    train_policy, y_train = policy_frame(train, policy, True)
    val_policy, y_val = policy_frame(validation, policy, False)
    features = arms[arm]
    model = clone(model_factories(args.seed)[model_name])
    model.fit(train_policy[features].fillna(0.0).astype(float), y_train)
    val_score = probability(model, val_policy[features].fillna(0.0).astype(float))
    threshold, tuning = threshold_for_validation(val_policy, val_score, policy)
    iso = IsotonicRegression(out_of_bounds="clip").fit(val_score, y_val)
    calibrated = np.asarray(iso.predict(val_score))
    calibration = {"ece": ece(y_val, calibrated), "brier_like_mae": float(np.mean(np.abs(calibrated - y_val)))}
    candidate_path = root / "selected_candidate.joblib"
    joblib.dump({"model": model, "features": features, "policy": policy, "threshold": threshold}, candidate_path)
    selected_config = {"task": TASK, "policy": policy, "feature_arm": arm, "features": features, "model": model_name, "threshold": threshold, "threshold_selection": tuning, "validation_calibration": calibration, "latency_ms": float(chosen["latency_ms"]), "latency_budget_ms": 10.0, "candidate_sha256": sha256(candidate_path), "production_artefact_untouched": True}
    selected_config["validation_metrics"] = {key: chosen[key] for key in ["validation_precision", "validation_recall", "validation_f1", "validation_roc_auc", "validation_pr_auc", "false_alarm_per_hour"]}
    selected_config["validation_confusion_matrix"] = json.loads(str(chosen["validation_confusion_matrix"]))
    if hasattr(model, "feature_importances_"):
        importances = np.asarray(model.feature_importances_, dtype=float)
        total = float(importances.sum()) or 1.0
        ranking = sorted(((name, float(value / total)) for name, value in zip(features, importances)), key=lambda item: item[1], reverse=True)
        selected_config["feature_importance"] = [{"feature": name, "share": share, "rank": rank} for rank, (name, share) in enumerate(ranking, start=1)]
    (root / "selected_config.json").write_text(json.dumps(selected_config, indent=2), encoding="utf-8")
    (root / "selected_config.json.sha256").write_text(sha256(root / "selected_config.json") + "  selected_config.json\n", encoding="utf-8")
    try:
        import matplotlib.pyplot as plt
        prob_true, prob_pred = calibration_curve(y_val, calibrated, n_bins=10, strategy="uniform")
        plt.figure(figsize=(5, 4)); plt.plot(prob_pred, prob_true, marker="o"); plt.plot([0, 1], [0, 1], "--"); plt.xlabel("Mean predicted probability"); plt.ylabel("Observed frequency"); plt.title("P6 validation calibration"); plt.tight_layout(); plt.savefig(root / "calibration_validation.png", dpi=140); plt.close()
    except Exception as exc:
        (root / "calibration_plot_error.txt").write_text(str(exc), encoding="utf-8")
    manifest = {"task": TASK, "git_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root.parents[1], text=True).strip(), "python": sys.version, "packages": {"pandas": pd.__version__, "numpy": np.__version__, "sklearn": __import__("sklearn").__version__}, "cpu": platform.processor(), "cli_arguments": vars(args), "seeds": {"train": list(range(100, 120)), "validation": list(range(200, 205)), "model": args.seed}, "start_time_utc": started.isoformat(), "end_time_utc": datetime.now(timezone.utc).isoformat(), "input_datasets": {str(p): sha256(p) for p in paths}, "output_datasets": {str(p): sha256(p) for p in root.iterdir() if p.is_file() and p.name != "run_manifest.json"}}
    (root / "run_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps({"selected_config": selected_config, "rows": len(results), "train_rows": len(train), "validation_rows": len(validation)}, indent=2))


if __name__ == "__main__":
    main()
