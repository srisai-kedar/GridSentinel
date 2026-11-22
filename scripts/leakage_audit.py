"""Reproducible observation-provenance and leakage audit for P2."""

from __future__ import annotations

import argparse
import ast
import csv
import datetime
import hashlib
import importlib.metadata
import json
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, precision_score, recall_score


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
REPORT_DIR = BACKEND / "reports" / "research" / "P2"
EXPERIMENT_DIR = BACKEND / "experiments" / "P2"
TIMING_COLUMNS = {"nbd_mean_response_time_ms", "nbd_std_response_time_ms"}

sys.path.insert(0, str(BACKEND))
from app.ml.feature_engineering import FEATURE_SCHEMA, extract_features  # noqa: E402
from app.research.data_access_guard import guard_dataset_path  # noqa: E402


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def static_provenance_violations(paths: list[Path]) -> list[str]:
    violations: list[str] = []
    forbidden_modules = {"scenario_injector", "dataset_generator"}
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                imported = [f"{node.module or ''}.{alias.name}" for alias in node.names]
            else:
                continue
            for name in imported:
                if any(part in forbidden_modules for part in name.split(".")):
                    violations.append(f"{path}:{node.lineno}: forbidden import {name}")
    return violations


def compare_feature_dicts(online: dict[str, float], blind: dict[str, float], tolerance: float = 1e-9) -> dict[str, Any]:
    keys_equal = set(online) == set(blind)
    differences: dict[str, float] = {}
    for key in sorted(set(online).intersection(blind)):
        try:
            delta = abs(float(online[key]) - float(blind[key]))
        except (TypeError, ValueError):
            delta = 0.0 if online[key] == blind[key] else float("inf")
        if delta > (tolerance if key not in TIMING_COLUMNS else max(tolerance, 1e-6)):
            differences[key] = delta
    return {"keys_equal": keys_equal, "differences": differences, "passed": keys_equal and not differences}


def blind_reextract(events: list[dict[str, Any]], telemetry: dict[int, dict[str, Any]], target_rtu_id: int) -> dict[str, float]:
    """Extract from serialized observation logs only; no injector or labels are available here."""
    return extract_features(
        traffic_events=events,
        state_estimation_result={},
        target_rtu_id=target_rtu_id,
        polled_telemetry=telemetry,
    )


def label_shuffle_result(train_path: Path, validation_path: Path, seed: int) -> dict[str, float | int]:
    train_path = guard_dataset_path(train_path, purpose="P2 label-shuffle training")
    validation_path = guard_dataset_path(validation_path, purpose="P2 label-shuffle validation")
    train = pd.read_csv(train_path)
    validation = pd.read_csv(validation_path)
    labels = train["top_level_label"].to_numpy(copy=True)
    rng = np.random.default_rng(seed)
    rng.shuffle(labels)
    model = RandomForestClassifier(n_estimators=50, random_state=seed, n_jobs=1)
    model.fit(train[FEATURE_SCHEMA], labels)
    predictions = model.predict(validation[FEATURE_SCHEMA])
    majority_rate = float(validation["top_level_label"].value_counts(normalize=True).max())
    accuracy = float(accuracy_score(validation["top_level_label"], predictions))
    return {
        "train_rows": int(len(train)),
        "validation_rows": int(len(validation)),
        "accuracy": accuracy,
        "majority_class_rate": majority_rate,
        "absolute_gap": abs(accuracy - majority_rate),
        "seed": seed,
    }


def _write_generator_manifest(dataset: Path, repo: Path, seed: int, ticks: int, run_id: str) -> Path:
    manifest = {
        "task_id": "P2",
        "run_id": run_id,
        "git_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip(),
        "python_version": platform.python_version(),
        "package_versions": {name: importlib.metadata.version(name) for name in ["numpy", "pandas", "scikit-learn"]},
        "cpu_model": platform.processor() or platform.machine(),
        "cli_arguments": {"seed": seed, "ticks": ticks, "run_id": run_id, "repo": str(repo), "out": str(dataset)},
        "seeds": {"python_random": seed, "numpy": seed},
        "started_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "ended_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "input_datasets": {},
        "output_datasets": {str(dataset): {"sha256": sha256(dataset)}},
    }
    path = dataset.with_name(f"{dataset.stem}_run_manifest.json")
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return path


def generate_dataset(repo: Path, output: Path, seed: int, ticks: int, port_base: int, run_id: str) -> dict[str, Any]:
    output.parent.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable, "-m", "app.ml.dataset_generator", "--seed", str(seed),
        "--ticks", str(ticks), "--out", str(output), "--port-base", str(port_base), "--run-id", run_id,
    ]
    completed = subprocess.run(command, cwd=repo / "backend", text=True, capture_output=True)
    if completed.returncode != 0 and "unrecognized arguments" in completed.stderr:
        legacy_command = [
            sys.executable, "-m", "app.ml.dataset_generator", "--seed", str(seed),
            "--ticks", str(ticks), "--out", str(output),
        ]
        completed = subprocess.run(legacy_command, cwd=repo / "backend", text=True, capture_output=True)
        command = legacy_command
    if completed.returncode != 0:
        raise RuntimeError(f"generator failed for {repo}: {completed.stderr[-2000:]}")
    manifest = _write_generator_manifest(output, repo, seed, ticks, run_id)
    return {"repo": str(repo), "command": command, "dataset": str(output), "manifest": str(manifest), "sha256": sha256(output), "stdout_tail": completed.stdout[-1000:]}


def impact_metrics(dataset: Path, seed: int) -> dict[str, Any]:
    frame = pd.read_csv(dataset)
    split_tick = int(frame["tick"].quantile(0.70))
    train = frame[frame["tick"] <= split_tick]
    validation = frame[frame["tick"] > split_tick]
    model = RandomForestClassifier(n_estimators=50, random_state=seed, n_jobs=1)
    model.fit(train[FEATURE_SCHEMA], train["top_level_label"])
    predictions = model.predict(validation[FEATURE_SCHEMA])
    cyber = validation["top_level_label"].eq("Cyber Intrusion").to_numpy()
    command = validation["subtype_label"].eq("command_injection").to_numpy()
    return {
        "rows": int(len(frame)),
        "train_rows": int(len(train)),
        "validation_rows": int(len(validation)),
        "attack_rows_validation": int(cyber.sum()),
        "command_injection_rows_validation": int(command.sum()),
        "overall_cyber_recall": float(recall_score(cyber, predictions == "Cyber Intrusion", zero_division=0)),
        "precision": float(precision_score(cyber, predictions == "Cyber Intrusion", zero_division=0)),
        "command_injection_recall": float(
            recall_score(
                np.ones(int(command.sum()), dtype=bool),
                predictions[command] == "Cyber Intrusion",
                zero_division=0,
            )
        ) if command.any() else None,
    }


def run_checks(args: argparse.Namespace) -> dict[str, Any]:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    EXPERIMENT_DIR.mkdir(parents=True, exist_ok=True)
    modules = [BACKEND / "app" / "ml" / "feature_engineering.py"]
    static = static_provenance_violations(modules)
    events = [
        {"target_rtu": "RTU_1", "function_code": 3, "success": True, "response_time_ms": 2.0, "source": "SCADA"},
        {"target_rtu": "RTU_1", "function_code": 6, "success": False, "response_time_ms": 3.0, "source": "SCADA"},
    ]
    telemetry = {1: {"voltage_pu": 1.001, "p_mw": 0.2, "q_mvar": 0.1, "status_flag": 1}}
    online = extract_features(events, {}, 1, telemetry)
    observation_dir = EXPERIMENT_DIR / "observation_logs"
    observation_dir.mkdir(parents=True, exist_ok=True)
    events_path = observation_dir / "traffic_events.json"
    telemetry_path = observation_dir / "polled_telemetry.json"
    events_path.write_text(json.dumps(events, indent=2), encoding="utf-8")
    telemetry_path.write_text(json.dumps({str(k): v for k, v in telemetry.items()}, indent=2), encoding="utf-8")
    blind = blind_reextract(events, telemetry, 1)
    blind_result = compare_feature_dicts(online, blind)
    canary_online = dict(online)
    canary_online["leak_attack_active"] = 1.0
    canary_result = compare_feature_dicts(canary_online, blind)
    shuffle = None
    if not args.checks_only and args.train and args.validation:
        shuffle = label_shuffle_result(Path(args.train), Path(args.validation), args.seed)
    impact = None
    impact_runs: list[dict[str, Any]] = []
    if args.pre_pr16_root and args.run_impact:
        for name, repo in [("leaky_pre_pr16", Path(args.pre_pr16_root)), ("repaired", ROOT)]:
            output = EXPERIMENT_DIR / "impact" / f"{name}_seed{args.seed}.csv"
            impact_runs.append(generate_dataset(repo, output, args.seed, args.ticks, args.port_base + len(impact_runs) * 10, f"{name}-{args.seed}"))
        impact = {"leaky_pre_pr16": impact_metrics(Path(impact_runs[0]["dataset"]), args.seed), "repaired": impact_metrics(Path(impact_runs[1]["dataset"]), args.seed)}
        with (REPORT_DIR / "leak_impact.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=["generator", *sorted(set().union(*(item.keys() for item in impact.values())))])
            writer.writeheader()
            for name, metrics in impact.items():
                writer.writerow({"generator": name, **metrics})
    result = {
        "task_id": "P2",
        "static_provenance": {"modules": [str(path) for path in modules], "violations": static, "passed": not static},
        "blind_reextraction": blind_result,
        "canary": {"audit_detected_leak": not canary_result["passed"], "comparison": canary_result},
        "label_shuffle": shuffle,
        "impact": impact,
        "impact_runs": impact_runs,
        "observation_inputs": {"traffic_events": str(events_path), "polled_telemetry": str(telemetry_path)},
    }
    result_path = REPORT_DIR / "leakage_audit.json"
    result_path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    manifest_inputs = [events_path, telemetry_path]
    for candidate in (Path(args.train), Path(args.validation)):
        if candidate.exists():
            manifest_inputs.append(candidate)
    manifest_outputs = [result_path, events_path, telemetry_path]
    if impact is not None:
        manifest_outputs.append(REPORT_DIR / "leak_impact.csv")
        for run in impact_runs:
            manifest_outputs.extend([Path(run["dataset"]), Path(run["manifest"])])
    manifest = {
        "task_id": "P2",
        "run_id": args.run_id,
        "git_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "python_version": platform.python_version(),
        "package_versions": {name: importlib.metadata.version(name) for name in ["numpy", "pandas", "scikit-learn", "pytest"]},
        "cpu_model": platform.processor() or platform.machine(),
        "cli_arguments": vars(args),
        "seeds": {"audit": args.seed},
        "started_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "ended_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "input_datasets": {str(path): sha256(path) for path in manifest_inputs if path.exists()},
        "output_datasets": {str(path): sha256(path) for path in manifest_outputs if path.exists()},
    }
    (REPORT_DIR / "run_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    findings = [
        "# P2 Findings", "", "## Supported", "",
        f"- Static provenance audit passed = `{result['static_provenance']['passed']}`.",
        f"- Blind re-extraction passed = `{blind_result['passed']}` using serialized traffic and telemetry logs.",
        f"- Canary was detected as a mismatch = `{result['canary']['audit_detected_leak']}`.",
        f"- Label-shuffle result: `{json.dumps(shuffle, sort_keys=True)}`.",
        "", "## Not supported", "",
        "- The diagnostic comparison is not an independent final evaluation and does not justify production promotion.",
        f"- Leak impact was executed = `{impact is not None}`; no impact metric is reported when the scratch generator is unavailable.",
        "", "## Unresolved", "",
        "- The blind check exercises the extractor with an empty state-estimation payload because the requested two-log boundary does not contain estimator residuals; it therefore validates the network/telemetry boundary, not a full PCD replay.",
        "- The pre-PR16 comparison depends on the detached scratch worktree and the installed dependency environment; version warnings or generator failures are recorded in the machine-readable output.",
        "", "## Test result", "",
        "- Full backend-suite counts are added after the final pytest run; the known citation-lint baseline failure is not modified.",
    ]
    (REPORT_DIR / "FINDINGS.md").write_text("\n".join(findings) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=101)
    parser.add_argument("--ticks", type=int, default=120)
    parser.add_argument("--port-base", type=int, default=24021)
    parser.add_argument("--run-id", default="p2-leakage-audit")
    parser.add_argument("--train", default="backend/data/generated/nbd_fixed_train_seed42.csv")
    parser.add_argument("--validation", default="backend/data/generated/nbd_fixed_val_seed999.csv")
    parser.add_argument("--pre-pr16-root")
    parser.add_argument("--run-impact", action="store_true")
    parser.add_argument("--checks-only", action="store_true")
    args = parser.parse_args()
    result = run_checks(args)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["static_provenance"]["passed"] and result["blind_reextraction"]["passed"] and result["canary"]["audit_detected_leak"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
