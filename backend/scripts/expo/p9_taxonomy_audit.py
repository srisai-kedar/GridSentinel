"""Audit P9 taxonomy-study readiness without training or reading held-out data."""
from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.metadata
import json
import platform
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
REPO = ROOT.parent


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def scenario_metadata(paths: list[Path]) -> dict:
    rows = []
    for path in paths:
        frame = pd.read_csv(path)
        for value in frame.get("scenario_params", pd.Series(dtype=str)).dropna().astype(str):
            try:
                rows.append(json.loads(value))
            except json.JSONDecodeError:
                continue
    sigmas = sorted({item["sigma_multiple"] for item in rows if "sigma_multiple" in item})
    drift_modes = sorted({item["mode"] for item in rows if item.get("target") in {"V", "P", "Q", "mixed"} and "mode" in item})
    return {"scenario_param_records": len(rows), "fdi_sigma_multiples_observed": sigmas, "drift_modes_observed": drift_modes, "scenario_param_keys": sorted({key for item in rows for key in item})}


def rule_source_audit(source: Path) -> dict:
    text = source.read_text(encoding="utf-8")
    tree = ast.parse(text)
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "detect_sensor_drift_signature")
    segment = ast.get_source_segment(text, function) or ""
    return {
        "source": str(source),
        "has_concentration_comparison": bool(re.search(r"concentration\s*>=\s*0\.70", segment)),
        "has_always_true_key_presence_clause": "pcd_resid_concentration\" in features" in segment,
        "source_lines": {"start": function.lineno, "end": getattr(function, "end_lineno", function.lineno)},
        "threshold_literals": sorted(set(re.findall(r"(?:concentration|v_dev|breadth_count|anomaly_rate|pcd_max_lnr|pcd_target_rtu_v_residual).*?(?:>=|<=|==|>)\s*[0-9.]+", segment))),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=ROOT / "experiments" / "P6-complete" / "generated")
    parser.add_argument("--out-dir", type=Path, default=ROOT / "experiments" / "P9")
    args = parser.parse_args()
    started = datetime.now(timezone.utc)
    paths = sorted(args.data_dir.glob("train_seed*.csv")) + sorted(args.data_dir.glob("validation_seed*.csv"))
    if not paths:
        raise FileNotFoundError(f"no non-held-out P6 files found in {args.data_dir}")
    metadata = scenario_metadata(paths)
    rule = rule_source_audit(ROOT / "app" / "ml" / "classifier_service.py")
    required_sigmas = [1, 2, 3, 5, 10, 25]
    required_modes = ["ramp", "step", "gain_error", "stuck_at", "noise_increase"]
    missing_sigmas = sorted(set(required_sigmas) - set(metadata["fdi_sigma_multiples_observed"]))
    missing_modes = sorted(set(required_modes) - set(metadata["drift_modes_observed"]))
    status = "BLOCKED" if missing_sigmas or missing_modes or rule["has_always_true_key_presence_clause"] else "READY_FOR_TARGETED_GENERATION"
    out = args.out_dir
    out.mkdir(parents=True, exist_ok=True)
    matrix_path = out / "confusion.csv"
    labels = ["Normal-Operational", "Fault", "FDI/replay/command", "Drift", "Unknown/Unavailable"]
    matrix = pd.DataFrame([["" for _ in labels] for _ in labels], index=labels, columns=labels)
    matrix.index.name = "actual\\predicted"
    matrix.to_csv(matrix_path)
    result_path = out / "taxonomy_readiness.json"
    payload = {"task_id": "P9", "status": status, "rule_audit": rule, "available_input_files": [str(path) for path in paths], "available_input_metadata": metadata, "required_fdi_sigma_multiples": required_sigmas, "missing_fdi_sigma_multiples": missing_sigmas, "required_drift_modes": required_modes, "missing_drift_modes": missing_modes, "learned_four_class_model": "not trained because the required systematic study and independent held-out runs are unavailable", "confusion_matrix": "unavailable; confusion.csv is an empty schema only", "started_at_utc": started.isoformat(), "ended_at_utc": datetime.now(timezone.utc).isoformat()}
    result_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    manifest = {"task_id": "P9", "git_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip(), "python_version": sys.version, "package_versions": {name: importlib.metadata.version(name) for name in ["numpy", "pandas", "scikit-learn"]}, "cpu_model": platform.processor() or platform.machine(), "cli_arguments": {key: str(value) for key, value in vars(args).items()}, "seeds": {}, "started_at_utc": started.isoformat(), "ended_at_utc": datetime.now(timezone.utc).isoformat(), "input_datasets": {str(path): digest(path) for path in paths}, "output_datasets": {str(result_path): digest(result_path), str(matrix_path): digest(matrix_path)}}
    (out / "run_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({"status": status, "missing_fdi_sigma_multiples": missing_sigmas, "missing_drift_modes": missing_modes, "output": str(result_path)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
