"""Final evaluator entry point; this is the only P5 script permitted to read *test* data."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.metadata
import json
import platform
import subprocess
from pathlib import Path
import sys

import pandas as pd
import numpy as np
from sklearn.metrics import average_precision_score, confusion_matrix, precision_recall_curve, precision_score, recall_score, f1_score, roc_auc_score, roc_curve

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))
from eval.metrics import evaluate  # noqa: E402
from app.research.data_access_guard import append_test_access_log, guard_dataset_path  # noqa: E402
from scripts.baselines import production_score  # noqa: E402


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_rows(path: Path, *, is_test: bool) -> list[dict]:
    guarded = guard_dataset_path(path, purpose="P5 final evaluation", allow_test=is_test)
    if is_test:
        append_test_access_log(guarded, script="scripts/eval_final.py", purpose="P5 final evaluation")
    return pd.read_csv(guarded).to_dict(orient="records")


def load_heldout_dir(directory: Path) -> tuple[list[dict], list[Path]]:
    paths = sorted(directory.glob("heldout*.csv"))
    if not paths:
        raise FileNotFoundError(f"no held-out capture files found in {directory}")
    rows: list[dict] = []
    for path in paths:
        rows.extend(load_rows(path, is_test=True))
    return rows, paths


def choose_threshold(validation_rows: list[dict], clean_runs: dict[str, float], budget: float) -> float:
    scores = sorted({float(row["score"]) for row in validation_rows}, reverse=True)
    candidates = scores + [float("inf")]
    best = None
    for threshold in candidates:
        rows = [dict(row, alert=float(row["score"]) >= threshold) for row in validation_rows]
        result = evaluate(rows, clean_runs=clean_runs, gap=0, tail=0, grace=0)
        rate = result["false_alarms"]["per_hour"]
        if rate is not None and rate <= budget:
            key = (result["episode"]["recall"] or 0.0, threshold)
            if best is None or key > best[0]:
                best = (key, threshold)
    return float(best[1]) if best is not None else float("inf")


def _p7_summary(rows: list[dict], scores: np.ndarray, threshold: float, *, gap: int = 0, tail: int = 0, grace: int = 0) -> dict:
    observed = [dict(row, score=float(score), alert=bool(score >= threshold)) for row, score in zip(rows, scores)]
    result = evaluate(observed, clean_runs={str(row["run_id"]): float(row["duration_hours"]) for row in rows if bool(row.get("is_clean_run"))}, gap=gap, tail=tail, grace=grace)
    y = np.asarray([int(bool(row.get("attack_active"))) for row in rows])
    pred = (scores >= threshold).astype(int)
    normal = y == 0
    result["threshold"] = float(threshold)
    result["reading_metrics"] = {
        "precision": float(precision_score(y, pred, zero_division=0)),
        "recall": float(recall_score(y, pred, zero_division=0)),
        "f1": float(f1_score(y, pred, zero_division=0)),
        "false_positive_rate": float(pred[normal].mean()) if normal.any() else None,
        "roc_auc": float(roc_auc_score(y, scores)) if len(np.unique(y)) > 1 else None,
        "pr_auc": float(average_precision_score(y, scores)) if len(np.unique(y)) > 1 else None,
        "confusion_matrix": confusion_matrix(y, pred, labels=[0, 1]).tolist(),
    }
    return result


def _paired_cluster_bootstrap(results_a: dict, results_b: dict, *, seed: int, reps: int = 2000) -> dict:
    a = {(str(x["run_id"]), str(x["episode_id"])): int(x["detected"]) for x in results_a["episode_results"]}
    b = {(str(x["run_id"]), str(x["episode_id"])): int(x["detected"]) for x in results_b["episode_results"]}
    keys = sorted(set(a) & set(b))
    by_run: dict[str, list[float]] = {}
    for key in keys:
        by_run.setdefault(key[0], []).append(float(a[key] - b[key]))
    rng = np.random.default_rng(seed)
    runs = sorted(by_run)
    observed = float(np.mean([v for values in by_run.values() for v in values])) if keys else None
    boot = []
    if runs:
        for _ in range(reps):
            sampled = rng.choice(runs, size=len(runs), replace=True)
            values = []
            for run in sampled:
                vals = by_run[str(run)]
                values.extend(rng.choice(vals, size=len(vals), replace=True).tolist())
            boot.append(float(np.mean(values)))
    interval = [float(np.quantile(boot, 0.025)), float(np.quantile(boot, 0.975))] if boot else [None, None]
    pvalue = float(2 * min(np.mean(np.asarray(boot) <= 0), np.mean(np.asarray(boot) >= 0))) if boot else None
    return {"episodes": len(keys), "runs": len(runs), "difference_mean": observed, "ci95": interval, "p_value": pvalue, "replicates": reps, "seed": seed}


def _p7_latency(score_fn, frame: pd.DataFrame, repeats: int = 5) -> dict:
    import time
    durations = []
    for _ in range(repeats):
        start = time.perf_counter()
        score_fn(frame)
        durations.append((time.perf_counter() - start) * 1000.0 / max(len(frame), 1))
    return {"median_ms_per_row": float(np.median(durations)), "p95_ms_per_row": float(np.quantile(durations, 0.95))}


def run_p7(args: argparse.Namespace) -> int:
    import joblib
    sys.path.insert(0, str(ROOT / "backend"))
    from scripts.baselines import RAW_FEATURES, FUSION_FEATURES, NBD_COLUMNS, PCD_COLUMNS
    from scripts.expo.train_v2 import add_staleness_features
    started = dt.datetime.now(dt.timezone.utc)
    bundle = joblib.load(args.p7_bundle)
    rows, input_paths = load_heldout_dir(args.heldout_dir)
    frame = add_staleness_features(pd.DataFrame(rows))
    threshold = bundle["thresholds"]
    models = bundle["models"]
    score_fns = {
        "classical_bad_data": lambda f: np.maximum(f["pcd_chi2_failed"].to_numpy(float), (f["pcd_max_lnr"].to_numpy(float) > 3.0).astype(float)),
        "rule_nbd_unexpected_write": lambda f: (f["nbd_unexpected_write_count"].to_numpy(float) > 0).astype(float),
        "isolation_forest": lambda f: -np.asarray(models["isolation_forest"].decision_function(f[RAW_FEATURES].fillna(0.0)), dtype=float),
        "logistic": lambda f: np.asarray(models["logistic"].predict_proba(f[FUSION_FEATURES].fillna(0.0)))[:, 1],
        "tree_depth3": lambda f: np.asarray(models["tree_depth3"].predict_proba(f[FUSION_FEATURES].fillna(0.0)))[:, 1],
        "nbd_only": lambda f: np.asarray(models["nbd_only"].predict_proba(f[NBD_COLUMNS].fillna(0.0)))[:, 1],
        "pcd_only": lambda f: np.asarray(models["pcd_only"].predict_proba(f[PCD_COLUMNS].fillna(0.0)))[:, 1],
        "fusion": lambda f: np.asarray(models["tree_depth3"].predict_proba(f[FUSION_FEATURES].fillna(0.0)))[:, 1],
        "frozen_production": lambda f: production_score(bundle["production"], f),
    }
    out = args.out_dir
    out.mkdir(parents=True, exist_ok=True)
    (out / "curves").mkdir(exist_ok=True)
    results = {}
    for name, fn in score_fns.items():
        score = np.asarray(fn(frame), dtype=float)
        chosen_threshold = threshold.get(name, threshold.get("tree_depth3"))
        if chosen_threshold is None:
            raise KeyError(f"no frozen validation threshold for {name}")
        results[name] = _p7_summary(rows, score, float(chosen_threshold))
        results[name]["latency"] = _p7_latency(fn, frame)
        y = np.asarray([int(bool(row.get("attack_active"))) for row in rows])
        if len(np.unique(y)) > 1:
            fpr, tpr, roc_thr = roc_curve(y, score)
            pd.DataFrame({"fpr": fpr, "tpr": tpr, "threshold": roc_thr}).to_csv(out / "curves" / f"{name}_roc.csv", index=False)
            precision, recall, pr_thr = precision_recall_curve(y, score)
            pd.DataFrame({"precision": precision, "recall": recall, "threshold": np.r_[pr_thr, np.nan]}).to_csv(out / "curves" / f"{name}_pr.csv", index=False)
    comparisons = {
        "fusion_vs_pcd_only": _paired_cluster_bootstrap(results["fusion"], results["pcd_only"], seed=9107, reps=args.bootstrap),
        "fusion_vs_classical": _paired_cluster_bootstrap(results["fusion"], results["classical_bad_data"], seed=9108, reps=args.bootstrap),
    }
    payload = {"task_id": "P7-complete", "results": results, "paired_comparisons": comparisons, "input_paths": [str(p) for p in input_paths], "protocol": "P5; thresholds frozen from validation", "started_at_utc": started.isoformat(), "ended_at_utc": dt.datetime.now(dt.timezone.utc).isoformat()}
    result_path = out / "final_results.json"
    result_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    manifest = {"task_id": "P7-final", "git_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(), "python_version": platform.python_version(), "package_versions": {name: importlib.metadata.version(name) for name in ["numpy", "pandas", "scikit-learn", "scipy"]}, "cpu_model": platform.processor() or platform.machine(), "cli_arguments": {key: str(value) for key, value in vars(args).items()}, "seeds": {"bootstrap": [9107, 9108]}, "started_at_utc": started.isoformat(), "ended_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(), "input_datasets": {str(p): sha256(p) for p in input_paths + [args.p7_bundle]}, "output_datasets": {str(result_path): sha256(result_path)}}
    (out / "run_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--validation", type=Path)
    parser.add_argument("--test", type=Path)
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--p7-bundle", type=Path)
    parser.add_argument("--heldout-dir", type=Path)
    parser.add_argument("--bootstrap", type=int, default=2000)
    parser.add_argument("--budget", type=float, choices=[1.0, 5.0, 20.0], default=5.0)
    parser.add_argument("--seed", type=int, default=5005)
    args = parser.parse_args()
    if args.p7_bundle and args.heldout_dir:
        return run_p7(args)
    if not args.validation or not args.test or not args.out_dir:
        parser.error("P5 mode requires --validation, --test and --out-dir; P7 mode requires --p7-bundle and --heldout-dir")
    validation_rows = load_rows(args.validation, is_test=False)
    test_rows = load_rows(args.test, is_test=True)
    validation_clean = {str(row["run_id"]): float(row["duration_hours"]) for row in validation_rows if row.get("is_clean_run")}
    threshold = choose_threshold(validation_rows, validation_clean, args.budget)
    evaluated = [dict(row, alert=float(row["score"]) >= threshold) for row in test_rows]
    result = evaluate(evaluated, clean_runs={str(row["run_id"]): float(row["duration_hours"]) for row in test_rows if row.get("is_clean_run")}, gap=0, tail=0, grace=0)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    result["threshold"] = threshold
    result["threshold_source"] = "validation_only"
    result_path = args.out_dir / "final_metrics.json"
    result_path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    manifest = {
        "task_id": "P5",
        "git_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "python_version": platform.python_version(),
        "package_versions": {name: importlib.metadata.version(name) for name in ["numpy", "pandas", "scipy"]},
        "cpu_model": platform.processor() or platform.machine(),
        "cli_arguments": vars(args),
        "seeds": {"threshold_selection": args.seed},
        "started_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "ended_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "input_datasets": {str(path): sha256(path) for path in [args.validation, args.test]},
        "output_datasets": {str(result_path): sha256(result_path)},
    }
    (args.out_dir / "run_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
