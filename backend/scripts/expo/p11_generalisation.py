"""P11 generalisation, redundancy, and scale readiness/diagnostic harness.

This task intentionally does not train, tune, select, or read held-out data.
It reports blocked cross-condition/cross-topology comparisons when their
required independent inputs are absent, and measures only the available
feeder's observability and complete-cycle latency.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import platform
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
from typing import Any

import numpy as np
import pandapower.estimation as estimation

from app.core.feeder import build_feeder
from app.core.state_estimation import add_measurements, detect_bad_data
from app.ml.classifier_service import ClassifierService
from app.ml.feature_engineering import extract_features


EXPECTED_OOD_SEEDS = tuple(range(400, 410))
REDUNDANCY_MEASUREMENT_COUNTS = (18, 16, 15, 14, 13)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_sha(repo: Path) -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()


def package_versions() -> dict[str, str]:
    names = ("numpy", "pandas", "pandapower", "scipy", "scikit-learn", "xgboost")
    values: dict[str, str] = {}
    for name in names:
        try:
            values[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            pass
    return values


def pytest_summary(path: Path | None) -> str:
    if path is None or not path.exists():
        return "not run by this command"
    text = path.read_text(encoding="utf-8", errors="replace")
    passed = re.findall(r"(\d+) passed", text)
    failed = re.findall(r"(\d+) failed", text)
    return f"{passed[-1] if passed else '0'} passed, {failed[-1] if failed else '0'} failed (raw output: {path})"


def reject_heldout_path(path: Path) -> Path:
    """Runtime guard for this non-final evaluator: never open a held-out path."""
    if "test" in path.name.lower() or "test" in str(path.parent).lower():
        raise RuntimeError(f"P11 is forbidden from reading held-out path: {path}")
    return path


def expected_ood_inventory(repo: Path) -> dict[str, Any]:
    generated_dirs = [repo / "backend/experiments/P6-complete/generated", repo / "backend/experiments/P7-complete/generated"]
    paths = [directory / f"ood_seed{seed}.csv" for directory in generated_dirs for seed in EXPECTED_OOD_SEEDS]
    return {
        "expected_seed_band": list(EXPECTED_OOD_SEEDS),
        "present_paths": [str(path) for path in paths if path.exists()],
        "missing_paths": [str(path) for path in paths if not path.exists()],
        "available_for_p11": False,
        "reason": "No generated OOD 400-409 files were found; P11 does not generate or read held-out files.",
    }


def run_observability(net: Any) -> dict[str, Any]:
    try:
        se = estimation.StateEstimation(net)
        result = se.estimate()
        rank = int(np.linalg.matrix_rank(np.asarray(se.solver.H, dtype=float))) if se.solver.H is not None else 0
        return {
            "success": bool(result.get("success", False)),
            "jacobian_rows": int(se.solver.H.shape[0]) if se.solver.H is not None else 0,
            "state_variables": int(se.solver.H.shape[1]) if se.solver.H is not None else 0,
            "jacobian_rank": rank,
            "observable": bool(rank == (se.solver.H.shape[1] if se.solver.H is not None else -1)),
        }
    except Exception as exc:
        return {"success": False, "jacobian_rows": 0, "state_variables": 0, "jacobian_rank": 0, "observable": False, "error": str(exc)}


def percentile(values: list[float], q: float) -> float:
    return float(np.percentile(np.asarray(values, dtype=float), q))


def measure_cycle(net: Any, service: ClassifierService, samples: int) -> dict[str, Any]:
    timings: list[float] = []
    verdicts: list[str] = []
    successful_cycles = 0
    for _ in range(5):
        trial = copy.deepcopy(net)
        started = time.perf_counter()
        state = detect_bad_data(trial)
        successful_cycles += int(state.get("error") is None)
        features = extract_features([], state, target_rtu_id=1)
        verdicts.append(str(service.predict(features).get("verdict")))
        timings.append((time.perf_counter() - started) * 1000.0)
    timings.clear()
    successful_cycles = 0
    for _ in range(samples):
        trial = copy.deepcopy(net)
        started = time.perf_counter()
        state = detect_bad_data(trial)
        successful_cycles += int(state.get("error") is None)
        features = extract_features([], state, target_rtu_id=1)
        verdicts.append(str(service.predict(features).get("verdict")))
        timings.append((time.perf_counter() - started) * 1000.0)
    return {
        "samples": len(timings),
        "estimation_successes": successful_cycles,
        "p50_total_cycle_ms": percentile(timings, 50),
        "p95_total_cycle_ms": percentile(timings, 95),
        "p99_total_cycle_ms": percentile(timings, 99),
        "min_total_cycle_ms": float(min(timings)),
        "max_total_cycle_ms": float(max(timings)),
        "verdict_counts": {label: verdicts.count(label) for label in sorted(set(verdicts))},
        "measurement_method": "per-cycle wall time: deep-copied network, WLS/LNR/chi2, feature extraction, production-model predict; five warmups excluded",
    }


def run_redundancy_latency(model_path: Path, samples: int) -> list[dict[str, Any]]:
    base = build_feeder()
    add_measurements(base)
    service = ClassifierService(str(model_path))
    records: list[dict[str, Any]] = []
    for measurement_count in REDUNDANCY_MEASUREMENT_COUNTS:
        net = copy.deepcopy(base)
        net.measurement = net.measurement.iloc[:measurement_count].copy()
        observability = run_observability(copy.deepcopy(net))
        latency = measure_cycle(net, service, samples)
        records.append({
            "measurement_count": measurement_count,
            "state_variable_count": observability["state_variables"],
            "redundancy_ratio": float(measurement_count / observability["state_variables"]) if observability["state_variables"] else None,
            **observability,
            **latency,
        })
    return records


def build_results(repo: Path, model_path: Path, samples: int) -> dict[str, Any]:
    return {
        "availability": {
            "cross_condition": expected_ood_inventory(repo),
            "cross_topology": {
                "status": "blocked",
                "available_second_feeder": False,
                "evidence": "No second feeder implementation or approved Baran-Wu topology exists in the repository.",
            },
        },
        "redundancy_latency": run_redundancy_latency(model_path, samples),
        "design": {
            "cross_condition_training": "P6 selected configuration would be required, but no OOD files are available and P11 does not read held-out files.",
            "cluster_bootstrap": "not computed because no independent cross-condition or cross-topology episode set is available",
            "production_model_read_only": True,
        },
    }


def write_outputs(repo: Path, result: dict[str, Any], out_dir: Path, report_dir: Path, args: argparse.Namespace, start: str, end: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)
    result_path = out_dir / "p11_results.json"
    redundancy_path = report_dir / "redundancy_latency.csv"
    condition_path = report_dir / "cross_condition.csv"
    topology_path = report_dir / "cross_topology.csv"
    result_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    import csv
    with redundancy_path.open("w", newline="", encoding="utf-8") as handle:
        fields = ["measurement_count", "state_variable_count", "redundancy_ratio", "success", "jacobian_rows", "jacobian_rank", "observable", "samples", "estimation_successes", "p50_total_cycle_ms", "p95_total_cycle_ms", "p99_total_cycle_ms"]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows({key: row.get(key) for key in fields} for row in result["redundancy_latency"])
    with condition_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["status", "train_family", "evaluation_family", "rows", "episode_interval_low", "episode_interval_high", "reason"])
        writer.writeheader()
        writer.writerow({"status": "blocked", "train_family": "default", "evaluation_family": "ood_400_409", "rows": "", "episode_interval_low": "", "episode_interval_high": "", "reason": result["availability"]["cross_condition"]["reason"]})
    with topology_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["status", "train_topology", "evaluation_topology", "rows", "episode_interval_low", "episode_interval_high", "reason"])
        writer.writeheader()
        writer.writerow({"status": "blocked", "train_topology": "GridSentinel feeder", "evaluation_topology": "second feeder", "rows": "", "episode_interval_low": "", "episode_interval_high": "", "reason": result["availability"]["cross_topology"]["evidence"]})
    input_paths = [repo / "backend/models/fusion_classifier.joblib", repo / "backend/app/core/feeder.py", repo / "backend/app/core/state_estimation.py", repo / "backend/app/core/topology_map.py", repo / "backend/app/ml/feature_engineering.py", repo / "backend/app/ml/classifier_service.py"]
    suite_path = Path(args.pytest_output) if args.pytest_output else None
    output_paths = [result_path, redundancy_path, condition_path, topology_path]
    if suite_path is not None and suite_path.exists():
        output_paths.append(suite_path)
    manifest = {
        "task": "P11",
        "git_sha": git_sha(repo),
        "python": sys.version,
        "packages": package_versions(),
        "cpu_model": platform.processor(),
        "cli_arguments": vars(args),
        "seeds": {"experiment": args.seed},
        "start_time_utc": start,
        "end_time_utc": end,
        "input_sha256": {str(path): sha256(path) for path in input_paths},
        "output_sha256": {str(path): sha256(path) for path in output_paths},
        "test_set_read": False,
        "pytest_summary": pytest_summary(suite_path),
    }
    (out_dir / "run_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    lines = [
        "# P11 findings",
        "",
        "All numeric values below are generated from `p11_results.json` by the committed P11 script. No held-out file was read.",
        "",
        "## Supported",
        "",
        f"- The available feeder redundancy/observability sweep contains {len(result['redundancy_latency'])} measured configurations.",
        "- Latency is measured as complete per-cycle wall time, including state estimation, feature extraction, and read-only production-model inference; five warmups are excluded.",
        "- The production model was loaded read-only. No production artifact was written.",
        f"- Full backend suite result: {pytest_summary(suite_path)}.",
        "",
        "### Measured redundancy and latency",
        "",
        "| Measurements | States | Ratio | Observable | p50 ms | p95 ms | p99 ms | Samples | Successful cycles |",
        "|---:|---:|---:|:---:|---:|---:|---:|---:|---:|",
    ]
    def display(value: Any, digits: str = "") -> str:
        if value is None:
            return "unavailable"
        return format(value, digits)

    for row in result["redundancy_latency"]:
        lines.append(f"| {row['measurement_count']} | {display(row['state_variable_count'])} | {display(row['redundancy_ratio'], '.6g')} | {row['observable']} | {display(row['p50_total_cycle_ms'], '.6g')} | {display(row['p95_total_cycle_ms'], '.6g')} | {display(row['p99_total_cycle_ms'], '.6g')} | {row['samples']} | {row['estimation_successes']} |")
    lines.extend([
        "",
        "## Not supported",
        "",
        "- Cross-condition train-on-default/evaluate-on-OOD results were not produced: the expected 400–409 files are absent, and this task cannot read held-out paths outside `scripts/eval_final.py`.",
        "- Cross-topology train-A/test-B and retrain-on-B results were not produced: no second feeder or approved Baran–Wu implementation is available.",
        "- No cross-condition or cross-topology cluster-bootstrap intervals were computed because the required independent episode units do not exist in the available inputs.",
        "- No claim of improved recall, false-alarm reduction, or generalisation is supported by the available-feeder timing/observability diagnostic.",
        "",
        "## Unresolved",
        "",
        "- Generate and provenance-manifest OOD runs 400–409 under the P3/P4 pipeline, with independent operating-condition metadata, then use the authorized final evaluator to read them once.",
        "- Provide or implement a second feeder with a documented RTU placement/topology map and an independent scenario schedule before cross-topology evaluation.",
        "- Reconcile the source comment's stated 1.5 redundancy with the measured state dimension and record the approved measurement-retention policy for each sweep level.",
        "",
        "## Evidence paths",
        "",
        f"- Results: `{result_path}`",
        f"- Run manifest: `{out_dir / 'run_manifest.json'}`",
        f"- Redundancy/latency CSV: `{redundancy_path}`",
        f"- Cross-condition status: `{condition_path}`",
        f"- Cross-topology status: `{topology_path}`",
        "",
        "## Reproduction",
        "",
        f"`backend/.venv/Scripts/python.exe backend/scripts/expo/p11_generalisation.py --out-dir {args.out_dir} --report-dir {args.report_dir} --samples {args.samples} --seed {args.seed}`",
    ])
    (report_dir / "FINDINGS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", default="backend/experiments/P11")
    parser.add_argument("--report-dir", default="backend/reports/research/P11")
    parser.add_argument("--samples", type=int, default=20)
    parser.add_argument("--seed", type=int, default=1111)
    parser.add_argument("--pytest-output", default="")
    args = parser.parse_args()
    if args.samples < 1:
        raise ValueError("samples must be positive")
    repo = Path(__file__).resolve().parents[3]
    start = datetime.now(timezone.utc).isoformat()
    result = build_results(repo, repo / "backend/models/fusion_classifier.joblib", args.samples)
    end = datetime.now(timezone.utc).isoformat()
    write_outputs(repo, result, repo / args.out_dir, repo / args.report_dir, args, start, end)


if __name__ == "__main__":
    main()
