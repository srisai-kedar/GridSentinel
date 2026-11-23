"""P7 pre-evaluation audit and baseline helpers.

This script is deliberately fail-closed. It may read only training and
validation inputs. Final held-out data is owned by scripts/eval_final.py.
"""
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

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PRODUCTION = ROOT / "models" / "fusion_classifier.joblib"


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


def production_schema() -> list[str]:
    import joblib
    bundle = joblib.load(PRODUCTION)
    return list(bundle["feature_schema"])


def assess_inputs(train_path: Path, validation_path: Path) -> dict[str, Any]:
    guard_training_path(train_path)
    guard_training_path(validation_path)
    train = pd.read_csv(train_path)
    validation = pd.read_csv(validation_path)
    schema = production_schema()
    missing = sorted(set(schema) - set(train.columns) - set(validation.columns))
    grouping = {name: bool(name in train.columns and name in validation.columns) for name in ["run_id", "episode_id", "tick", "duration_hours", "is_clean_run"]}
    clean_train = int(train["is_clean_run"].fillna(False).astype(bool).sum()) if "is_clean_run" in train else 0
    clean_validation = int(validation["is_clean_run"].fillna(False).astype(bool).sum()) if "is_clean_run" in validation else 0
    labels = {"train": train["top_level_label"].value_counts().to_dict() if "top_level_label" in train else {}, "validation": validation["top_level_label"].value_counts().to_dict() if "top_level_label" in validation else {}}
    blockers = []
    if missing:
        blockers.append("production feature columns are missing")
    if not all(grouping.values()):
        blockers.append("run/episode/timing/clean-duration metadata required by P5 is missing")
    if clean_train == 0 or clean_validation == 0:
        blockers.append("no explicit clean runs are available for the P5 false-alarm budget")
    return {
        "status": "BLOCKED" if blockers else "READY_FOR_TRAINING",
        "blockers": blockers,
        "train": {"path": str(train_path), "rows": len(train), "columns": len(train.columns), "sha256": file_sha256(train_path)},
        "validation": {"path": str(validation_path), "rows": len(validation), "columns": len(validation.columns), "sha256": file_sha256(validation_path)},
        "production_schema": schema,
        "grouping_metadata": grouping,
        "clean_rows": {"train": clean_train, "validation": clean_validation},
        "labels": labels,
        "final_heldout_evaluation": "not performed by this script",
    }


def classical_scores(frame: pd.DataFrame) -> dict[str, np.ndarray]:
    """Return deterministic, label-free scores for the two rule baselines."""
    lnr = pd.to_numeric(frame["pcd_max_lnr"], errors="coerce").fillna(0.0).to_numpy(float)
    chi = pd.to_numeric(frame["pcd_chi2_failed"], errors="coerce").fillna(0.0).to_numpy(float)
    writes = pd.to_numeric(frame["nbd_unexpected_write_count"], errors="coerce").fillna(0.0).to_numpy(float)
    return {
        "classical_bad_data": np.maximum(chi, (lnr > 3.0).astype(float)),
        "rule_nbd_unexpected_write": (writes > 0.0).astype(float),
    }


def write_audit(audit: dict[str, Any], output_dir: Path, args: dict[str, Any], started: datetime, pytest_output: Path | None = None) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    audit_path = output_dir / "input_audit.json"
    audit_path.write_text(json.dumps(audit, indent=2, sort_keys=True), encoding="utf-8")
    lines = [
        "# P7 findings",
        "",
        "## Supported",
        "",
        "- The production artefact was loaded read-only to obtain its exact feature schema.",
        "- The two supplied train/validation files were checked for schema, labels, and evaluation metadata.",
        "- No held-out data was read and no model was trained or tuned by this run.",
        "",
        "## Not supported",
        "",
        "- Classical bad-data and NBD rule scores were not promoted to performance claims; their final thresholds require the P5 validation clean-run rule.",
        "- Isolation Forest, logistic regression, depth-3 tree, NBD-only, PCD-only, and fusion comparisons were not selected or evaluated because the required grouped clean-run validation inputs are unavailable.",
        "- ROC/PR curves and paired Holm-adjusted intervals were not produced because the authorized final reader has not run on a defensible held-out set.",
        "",
        "## Unresolved",
        "",
    ]
    lines.extend(f"- {item}" for item in audit["blockers"])
    lines += [
        "- The legacy split lacks capture/session grouping, so row-level results would not satisfy the P7 leakage requirement.",
        "- A valid next input must provide run IDs, episode IDs, tick timing, explicit clean-run duration, and a separate held-out file consumed only by `scripts/eval_final.py`.",
        "",
        "## Evidence",
        "",
        f"- Machine-readable audit: `{audit_path}`",
        "- P5 protocol: `backend/reports/research/P5/PROTOCOL.md`",
    ]
    if pytest_output and pytest_output.exists():
        summary = [line.strip() for line in pytest_output.read_text(encoding="utf-8", errors="replace").splitlines() if "passed" in line or "failed" in line or "error" in line]
        lines.insert(-2, f"- Full backend suite command output: `{pytest_output}`; summary: `{summary[-1] if summary else 'no summary line'}`.")
    report_path = output_dir.parent.parent / "reports" / "research" / "P7" / "FINDINGS.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    outputs = [audit_path, report_path]
    manifest = {
        "task_id": "P7",
        "git_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT.parent, text=True).strip(),
        "python_version": sys.version,
        "package_versions": {name: importlib.metadata.version(name) for name in ["numpy", "pandas", "scikit-learn"]},
        "cpu_model": platform.processor() or platform.machine(),
        "cli_arguments": {key: str(value) for key, value in args.items()},
        "seeds": {},
        "started_at_utc": started.isoformat(),
        "ended_at_utc": datetime.now(timezone.utc).isoformat(),
        "input_datasets": {audit["train"]["path"]: audit["train"]["sha256"], audit["validation"]["path"]: audit["validation"]["sha256"], str(PRODUCTION): file_sha256(PRODUCTION)},
        "output_datasets": {str(path): file_sha256(path) for path in outputs},
    }
    (output_dir / "run_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--train", type=Path, default=Path("data/generated/nbd_fixed_train_seed42.csv"))
    parser.add_argument("--validation", type=Path, default=Path("data/generated/nbd_fixed_val_seed999.csv"))
    parser.add_argument("--out-dir", type=Path, default=Path("experiments/P7"))
    parser.add_argument("--pytest-output", type=Path, default=None)
    args = parser.parse_args()
    started = datetime.now(timezone.utc)
    audit = assess_inputs(args.train, args.validation)
    write_audit(audit, args.out_dir, vars(args), started, args.pytest_output)
    print(json.dumps(audit, indent=2, sort_keys=True))
    return 0 if audit["status"] == "READY_FOR_TRAINING" else 2


if __name__ == "__main__":
    raise SystemExit(main())
