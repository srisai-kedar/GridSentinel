"""Render the machine-produced P7 final results into comparison tables."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    payload = json.loads(args.results.read_text(encoding="utf-8"))
    args.out_dir.mkdir(parents=True, exist_ok=True)
    matrix = args.out_dir / "matrix.csv"
    fields = ["method", "reading_recall", "precision", "f1", "false_positive_rate", "roc_auc", "pr_auc", "episode_recall", "false_alarm_per_hour", "latency_median_ms_per_row"]
    with matrix.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for method, result in sorted(payload["results"].items()):
            reading = result["reading_metrics"]
            writer.writerow({"method": method, "reading_recall": reading["recall"], "precision": reading["precision"], "f1": reading["f1"], "false_positive_rate": reading["false_positive_rate"], "roc_auc": reading["roc_auc"], "pr_auc": reading["pr_auc"], "episode_recall": result["episode"]["recall"], "false_alarm_per_hour": result["false_alarms"]["per_hour"], "latency_median_ms_per_row": result["latency"]["median_ms_per_row"]})
    complement = args.out_dir / "complementarity.csv"
    with complement.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["method", "scenario", "episodes", "detected", "recall"])
        writer.writeheader()
        for method, result in sorted(payload["results"].items()):
            for scenario, values in sorted(result["per_type"].items()):
                writer.writerow({"method": method, "scenario": scenario, "episodes": values["episodes"], "detected": values["detected"], "recall": values["recall"]})
    manifest = {"task_id": "P7-matrix", "git_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=Path(__file__).resolve().parents[2], text=True).strip(), "python_version": sys.version, "cpu_model": platform.processor() or platform.machine(), "cli_arguments": {key: str(value) for key, value in vars(args).items()}, "seeds": {}, "started_at_utc": datetime.now(timezone.utc).isoformat(), "ended_at_utc": datetime.now(timezone.utc).isoformat(), "input_datasets": {str(args.results): digest(args.results)}, "output_datasets": {str(path): digest(path) for path in [matrix, complement]}}
    (args.out_dir / "matrix_run_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
