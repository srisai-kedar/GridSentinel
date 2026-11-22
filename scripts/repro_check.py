"""Run the P0 same-seed reproducibility audit."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT_ROOT = ROOT / "backend" / "experiments" / "P0" / "repro"
REPORT_ROOT = ROOT / "backend" / "reports" / "research" / "P0"
TIMING_COLUMNS = {"nbd_mean_response_time_ms", "nbd_std_response_time_ms"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_generation(seed: int, port_base: int, run_id: str, output: Path, ticks: int) -> dict:
    command = [
        sys.executable,
        "-m",
        "app.ml.dataset_generator",
        "--seed",
        str(seed),
        "--ticks",
        str(ticks),
        "--mode",
        "scenario_mix",
        "--port-base",
        str(port_base),
        "--run-id",
        run_id,
        "--out",
        str(output),
    ]
    started = time.perf_counter()
    completed = subprocess.run(command, cwd=ROOT / "backend", text=True, capture_output=True)
    return {
        "command": command,
        "returncode": completed.returncode,
        "elapsed_seconds": round(time.perf_counter() - started, 6),
        "stdout": completed.stdout[-4000:],
        "stderr": completed.stderr[-4000:],
        "output": str(output),
    }


def compare_csv(left_path: Path, right_path: Path) -> dict:
    left = pd.read_csv(left_path)
    right = pd.read_csv(right_path)
    if list(left.columns) != list(right.columns):
        return {"columns_equal": False, "rows_equal": False, "identical_non_timing": False, "timing": {}}
    if len(left) != len(right):
        return {"columns_equal": True, "rows_equal": False, "identical_non_timing": False, "timing": {}}
    non_timing = [column for column in left.columns if column not in TIMING_COLUMNS]
    mismatches = {
        column: int((left[column] != right[column]).sum())
        for column in non_timing
        if not left[column].equals(right[column])
    }
    timing = {}
    for column in sorted(TIMING_COLUMNS.intersection(left.columns)):
        values = (left[column].astype(float) - right[column].astype(float)).abs()
        timing[column] = {"max_absolute_difference": float(values.max()), "rows_different": int((values != 0).sum())}
    return {
        "columns_equal": True,
        "rows_equal": True,
        "labels_equal": left[["top_level_label", "subtype_label"]].equals(right[["top_level_label", "subtype_label"]]),
        "identical_non_timing": not mismatches,
        "non_timing_mismatches": mismatches,
        "timing": timing,
        "rows": len(left),
        "columns": list(left.columns),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--ticks", type=int, default=40)
    parser.add_argument("--port-a", type=int, default=15021)
    parser.add_argument("--port-b", type=int, default=16021)
    args = parser.parse_args()
    EXPERIMENT_ROOT.mkdir(parents=True, exist_ok=True)
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    left_path = EXPERIMENT_ROOT / "run_a" / "generated.csv"
    right_path = EXPERIMENT_ROOT / "run_b" / "generated.csv"
    left = run_generation(args.seed, args.port_a, "repro-a", left_path, args.ticks)
    right = run_generation(args.seed, args.port_b, "repro-b", right_path, args.ticks)
    result = {
        "task_id": "P0",
        "seed": args.seed,
        "ticks": args.ticks,
        "port_bases": [args.port_a, args.port_b],
        "runs": [left, right],
        "input_datasets": {},
    }
    if left["returncode"] == 0 and right["returncode"] == 0:
        result["comparison"] = compare_csv(left_path, right_path)
        result["outputs"] = {
            str(left_path): sha256(left_path),
            str(right_path): sha256(right_path),
        }
        result["run_manifests"] = [
            json.loads((left_path.parent / "run_manifest.json").read_text(encoding="utf-8")),
            json.loads((right_path.parent / "run_manifest.json").read_text(encoding="utf-8")),
        ]
    else:
        result["comparison"] = {"status": "not_run_due_to_generation_failure"}
    report_path = REPORT_ROOT / "repro_check.json"
    report_path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    comparison = result["comparison"]
    return 0 if comparison.get("identical_non_timing") and comparison.get("labels_equal") else 1


if __name__ == "__main__":
    raise SystemExit(main())
