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

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))
from eval.metrics import evaluate  # noqa: E402
from app.research.data_access_guard import append_test_access_log, guard_dataset_path  # noqa: E402


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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--validation", required=True, type=Path)
    parser.add_argument("--test", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--budget", type=float, choices=[1.0, 5.0, 20.0], default=5.0)
    parser.add_argument("--seed", type=int, default=5005)
    args = parser.parse_args()
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
