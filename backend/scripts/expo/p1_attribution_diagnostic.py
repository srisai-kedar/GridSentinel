"""Diagnostic before/after attribution run for P1.

The simulation is executed once. The corrected and legacy attribution functions
consume the same residual stream, while the same pre-existing model bundle is
scored on both feature tables. This is a diagnostic, not a production change.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime
import hashlib
import importlib.metadata
import json
import platform
import subprocess
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from app.ml import dataset_generator as generator
from app.ml import feature_engineering
from app.ml.feature_engineering import FEATURE_SCHEMA


LEGACY_RTU_BINDINGS = {
    1: {("bus", 1), ("line", 0)},
    2: {("bus", 2), ("line", 1)},
    3: {("bus", 3), ("line", 2)},
    4: {("bus", 4), ("line", 3)},
    5: {("bus", 5), ("line", 4)},
}


def legacy_measurement_matches_rtu(element_type: str, element: int, rtu_id: int) -> bool:
    return (str(element_type).lower(), int(element)) in LEGACY_RTU_BINDINGS[int(rtu_id)]


def subtype_recall(frame: pd.DataFrame, predictions: np.ndarray) -> dict[str, dict[str, float | int]]:
    result: dict[str, dict[str, float | int]] = {}
    attack_rows = frame[frame["top_level_label"] == "Cyber Intrusion"]
    for subtype in sorted(attack_rows["subtype_label"].unique()):
        mask = (frame["top_level_label"].eq("Cyber Intrusion") & frame["subtype_label"].eq(subtype)).to_numpy()
        result[str(subtype)] = {"support": int(mask.sum()), "recall": float(predictions[mask].mean()) if mask.any() else 0.0}
    return result


def attack_recall(frame: pd.DataFrame, predictions: np.ndarray) -> float | None:
    mask = frame["top_level_label"].eq("Cyber Intrusion").to_numpy()
    return float(predictions[mask].mean()) if mask.any() else None


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


async def run(args: argparse.Namespace) -> dict[str, Any]:
    started_at = datetime.datetime.now(datetime.timezone.utc)
    output_dir = Path(args.out_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    old_features: list[dict[str, float]] = []
    old_history: list[dict[int, list[float]]] = []
    original_extract = generator.extract_features
    original_match = feature_engineering.measurement_matches_rtu

    def dual_extract(*, traffic_events, state_estimation_result, target_rtu_id,
                     polled_telemetry=None, telemetry_history=None, residual_history=None):
        current = original_extract(
            traffic_events=traffic_events,
            state_estimation_result=state_estimation_result,
            target_rtu_id=target_rtu_id,
            polled_telemetry=polled_telemetry,
            telemetry_history=telemetry_history,
            residual_history=residual_history,
        )
        if target_rtu_id == 1:
            all_residuals = state_estimation_result.get("all_residuals", [])
            old_history.append({
                rid: [
                    float(item.get("normalised_residual", 0.0))
                    for item in all_residuals
                    if legacy_measurement_matches_rtu(item.get("element_type", ""), item.get("element", -1), rid)
                ]
                for rid in range(1, 6)
            })
            del old_history[:-6]
        feature_engineering.measurement_matches_rtu = legacy_measurement_matches_rtu
        try:
            legacy = original_extract(
                traffic_events=traffic_events,
                state_estimation_result=state_estimation_result,
                target_rtu_id=target_rtu_id,
                polled_telemetry=polled_telemetry,
                telemetry_history=telemetry_history,
                residual_history=list(old_history),
            )
        finally:
            feature_engineering.measurement_matches_rtu = original_match
        old_features.append(legacy)
        return current

    generator.extract_features = dual_extract
    try:
        current = await generator.generate_dataset(
            seed=args.seed,
            total_ticks=args.ticks,
            out_csv=str(output_dir / "corrected_features.csv"),
            mode="scenario_mix",
            port_base=args.port_base,
            run_id=args.run_id,
        )
    finally:
        generator.extract_features = original_extract
        feature_engineering.measurement_matches_rtu = original_match

    old = pd.DataFrame(old_features)
    old["tick"] = current["tick"].to_numpy()
    old["rtu_id"] = current["rtu_id"].to_numpy()
    old["top_level_label"] = current["top_level_label"].to_numpy()
    old["subtype_label"] = current["subtype_label"].to_numpy()
    old_path = output_dir / "legacy_features.csv"
    old.to_csv(old_path, index=False)

    bundle_path = Path(args.model)
    bundle = joblib.load(bundle_path)
    schema = list(bundle["feature_schema"])
    threshold = float(bundle["decision_threshold"])
    current_prob = bundle["top_level_model"].predict_proba(current[schema])
    old_prob = bundle["top_level_model"].predict_proba(old[schema])
    classes = list(bundle.get("classes", bundle["top_level_model"].classes_))
    cyber_index = classes.index("Cyber Intrusion")
    current_predictions = current_prob[:, cyber_index] >= threshold
    old_predictions = old_prob[:, cyber_index] >= threshold
    changes = {}
    for name in FEATURE_SCHEMA:
        delta = (current[name].astype(float) - old[name].astype(float)).abs()
        changes[name] = {"rows_changed": int((delta != 0).sum()), "max_absolute_difference": float(delta.max())}
    result = {
        "task_id": "P1",
        "diagnostic_only": True,
        "seed": args.seed,
        "ticks": args.ticks,
        "rows": len(current),
        "model": {"path": str(bundle_path), "sha256": sha256(bundle_path), "threshold": threshold, "schema": schema},
        "same_stream": True,
        "feature_changes": changes,
        "per_subtype_recall": {
            "legacy_mapping": subtype_recall(current, old_predictions),
            "corrected_mapping": subtype_recall(current, current_predictions),
        },
        "overall_attack_recall": {
            "legacy_mapping": attack_recall(current, old_predictions),
            "corrected_mapping": attack_recall(current, current_predictions),
        },
        "limitations": [
            "The same pre-existing candidate bundle is scored; no model is trained here.",
            "This is a regenerated diagnostic stream and is not a held-out final evaluation.",
            "Legacy mapping is reconstructed explicitly for comparison and is not used by application code.",
        ],
    }
    result_path = output_dir / "diagnostic_results.json"
    result_path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    manifest = {
        "task_id": "P1",
        "run_id": args.run_id,
        "git_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "python_version": platform.python_version(),
        "package_versions": {name: importlib.metadata.version(name) for name in ["numpy", "pandas", "joblib", "scikit-learn", "xgboost"]},
        "cpu_model": platform.processor() or platform.machine(),
        "cli_arguments": vars(args),
        "seeds": {"python_random": args.seed, "numpy": args.seed},
        "started_at_utc": started_at.isoformat(),
        "ended_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "input_datasets": {str(bundle_path): sha256(bundle_path)},
        "output_datasets": {str(path): sha256(path) for path in [output_dir / "corrected_features.csv", old_path, result_path]},
    }
    (output_dir / "run_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--ticks", type=int, default=30)
    parser.add_argument("--port-base", type=int, default=21021)
    parser.add_argument("--run-id", default="p1-attribution-diagnostic")
    parser.add_argument("--model", default="models/experiments/selected_candidate_bundle.joblib")
    parser.add_argument("--out-dir", default="experiments/P1/attribution_diagnostic")
    args = parser.parse_args()
    result = asyncio.run(run(args))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
