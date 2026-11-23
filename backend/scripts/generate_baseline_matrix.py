"""Create the P7 matrix scaffold from machine-produced baseline results."""
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


METHODS = ["classical_bad_data", "rule_nbd_unexpected_write", "isolation_forest", "logistic", "tree_depth3", "nbd_only", "pcd_only", "fusion"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit", type=Path, default=Path("experiments/P7/input_audit.json"))
    parser.add_argument("--out-dir", type=Path, default=Path("reports/research/P7"))
    args = parser.parse_args()
    audit = json.loads(args.audit.read_text(encoding="utf-8"))
    started = datetime.now(timezone.utc)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "curves").mkdir(exist_ok=True)
    with (args.out_dir / "matrix.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["method", "scenario", "episode_recall", "paired_interval_95", "status"])
        writer.writeheader()
        for method in METHODS:
            writer.writerow({"method": method, "scenario": "unavailable", "episode_recall": "", "paired_interval_95": "", "status": "blocked_by_input_metadata" if audit["status"] == "BLOCKED" else "pending_final_evaluation"})
    (args.out_dir / "curves" / "README.md").write_text("Final ROC/PR curves are intentionally absent until the authorized final evaluator has a defensible held-out input.\n", encoding="utf-8")
    def digest(path: Path) -> str:
        h = hashlib.sha256()
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                h.update(block)
        return h.hexdigest()
    outputs = [args.out_dir / "matrix.csv", args.out_dir / "curves" / "README.md"]
    manifest = {
        "task_id": "P7-matrix",
        "git_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=Path(__file__).resolve().parents[2], text=True).strip(),
        "python_version": sys.version,
        "cpu_model": platform.processor() or platform.machine(),
        "cli_arguments": {key: str(value) for key, value in vars(args).items()},
        "seeds": {},
        "started_at_utc": started.isoformat(),
        "ended_at_utc": datetime.now(timezone.utc).isoformat(),
        "input_datasets": {str(args.audit): digest(args.audit)},
        "output_datasets": {str(path): digest(path) for path in outputs},
    }
    (args.out_dir / "matrix_run_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
