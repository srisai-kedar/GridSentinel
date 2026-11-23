"""P10 diagnostic: measurement-space ``a = Hc`` detectability frontier.

This script is deliberately a physics-only diagnostic.  It does not train,
tune, select, or read any held-out dataset.  The pandapower estimator's
Jacobian is used at two operating points; attacks are added to copied network
measurements and never written back to the source model or datasets.
"""
from __future__ import annotations

import argparse
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
from app.core.state_estimation import detect_bad_data, add_measurements
from app.core.topology_map import is_trusted_pseudo_sensor, rtu_for_measurement
from app.ml.classifier_service import ClassifierService
from app.ml.feature_engineering import extract_features


MAGNITUDES = (1.0, 2.0, 3.0, 5.0, 10.0)
KNOWLEDGE = ("exact_current_operating_point", "nominal_topology")
GEOMETRIES = ("single_rtu", "two_rtu_coordinated")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_sha(repo: Path) -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=repo, text=True
    ).strip()


def package_versions() -> dict[str, str]:
    names = ("numpy", "pandas", "pandapower", "scipy", "scikit-learn", "xgboost")
    return {name: metadata.version(name) for name in names if _has_package(name)}


def pytest_summary(path: Path | None) -> str:
    if path is None or not path.exists():
        return "not run by this command"
    text = path.read_text(encoding="utf-8", errors="replace")
    passed = re.findall(r"(\d+) passed", text)
    failed = re.findall(r"(\d+) failed", text)
    return f"{passed[-1] if passed else '0'} passed, {failed[-1] if failed else '0'} failed (raw output: {path})"


def _has_package(name: str) -> bool:
    try:
        metadata.version(name)
        return True
    except metadata.PackageNotFoundError:
        return False


def attackable_measurement_indices(net: Any) -> list[int]:
    return [
        int(index)
        for index, row in net.measurement.iterrows()
        if not is_trusted_pseudo_sensor(str(row["element_type"]), int(row["element"]))
    ]


def measurement_metadata(net: Any) -> list[dict[str, Any]]:
    return [
        {
            "index": int(index),
            "type": str(row["measurement_type"]),
            "element_type": str(row["element_type"]),
            "element": int(row["element"]),
            "rtu": rtu_for_measurement(str(row["element_type"]), int(row["element"])),
            "trusted_pseudo_sensor": is_trusted_pseudo_sensor(str(row["element_type"]), int(row["element"])),
        }
        for index, row in net.measurement.iterrows()
    ]


def make_state_vector(direction: str, geometry: str, seed: int) -> np.ndarray:
    """Create a deterministic state direction; no labels or attack metadata."""
    c = np.zeros(13, dtype=float)
    if geometry == "single_rtu":
        rtus = (1,)
    elif geometry == "two_rtu_coordinated":
        rtus = (1, 5)
    else:
        raise ValueError(f"unsupported geometry: {geometry}")
    for rtu in rtus:
        c[rtu - 1] = 1.0
        c[6 + rtu] = 0.65
    # The direction is intentionally deterministic and fixed across magnitudes.
    if direction == "nominal_topology":
        c = c * 1.0
    return c / np.linalg.norm(c)


def estimator_jacobian(net: Any) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return H, the internal-to-net measurement index map, and E at WLS fit."""
    se = estimation.StateEstimation(net, recycle=True)
    result = se.estimate()
    if not result.get("success") or se.solver.H is None:
        raise RuntimeError("pandapower WLS did not expose a successful Jacobian")
    return np.asarray(se.solver.H, dtype=float), np.asarray(se.eppci.pp_meas_indices, dtype=int), np.asarray(se.eppci.E, dtype=float)


def build_operating_point(load_scale: float) -> tuple[Any, np.ndarray, np.ndarray, np.ndarray, list[int]]:
    net = build_feeder()
    net.load.loc[:, "p_mw"] *= load_scale
    net.load.loc[:, "q_mvar"] *= load_scale
    add_measurements(net)
    H, mapping, _ = estimator_jacobian(net)
    sigma = np.asarray([float(net.measurement.at[int(index), "std_dev"]) for index in mapping], dtype=float)
    return net, H, mapping, sigma, attackable_measurement_indices(net)


def scaled_attack(H: np.ndarray, c: np.ndarray, mapping: np.ndarray, sigma: np.ndarray, attackable: list[int], magnitude: float, restrict: bool) -> np.ndarray:
    raw = H @ c
    if restrict:
        allowed_rows = [row for row, measurement_index in enumerate(mapping) if int(measurement_index) in attackable]
        raw = np.where(np.isin(np.arange(len(raw)), allowed_rows), raw, 0.0)
    norm = float(np.linalg.norm(raw / sigma))
    if norm == 0.0:
        raise RuntimeError("Jacobian direction produced a zero attack vector")
    return raw * (float(magnitude) / norm)


def apply_attack(net: Any, mapping: np.ndarray, delta_internal: np.ndarray) -> None:
    for row, measurement_index in enumerate(mapping):
        net.measurement.at[int(measurement_index), "value"] += float(delta_internal[row])


def telemetry_from_measurements(net: Any) -> dict[int, dict[str, float]]:
    telemetry: dict[int, dict[str, float]] = {rtu: {"voltage_pu": 1.0, "p_mw": 0.0, "q_mvar": 0.0, "status_flag": 1.0} for rtu in range(1, 6)}
    for _, row in net.measurement.iterrows():
        rtu = rtu_for_measurement(str(row["element_type"]), int(row["element"]))
        if rtu is None:
            continue
        if row["measurement_type"] == "v":
            telemetry[rtu]["voltage_pu"] = float(row["value"])
        elif row["measurement_type"] == "p":
            telemetry[rtu]["p_mw"] = float(row["value"])
        elif row["measurement_type"] == "q":
            telemetry[rtu]["q_mvar"] = float(row["value"])
    return telemetry


def detector_outputs(net: Any, service: ClassifierService) -> dict[str, Any]:
    pcd = detect_bad_data(net)
    residuals = pcd.get("all_residuals", [])
    max_lnr = max((float(row.get("normalised_residual", 0.0)) for row in residuals), default=0.0)
    telemetry = telemetry_from_measurements(net)
    features = extract_features([], pcd, target_rtu_id=1, polled_telemetry=telemetry)
    fusion = service.predict(features)
    return {
        "chi2_alarm": bool(not pcd.get("chi2_test_passed", True)),
        "lnr_alarm": bool(max_lnr > 3.0),
        "pcd_alarm": bool(pcd.get("bad_data_detected", False)),
        "nbd_alarm": False,
        "fusion_alarm": str(fusion.get("verdict")) == "Cyber Intrusion",
        "fusion_verdict": str(fusion.get("verdict")),
        "max_lnr": max_lnr,
        "chi2_statistic": float(pcd.get("chi2_statistic", 0.0)),
        "residuals": [float(row.get("normalised_residual", 0.0)) for row in residuals],
    }


def run_experiment(seed: int, model_path: Path) -> dict[str, Any]:
    np.random.seed(seed)
    service = ClassifierService(str(model_path))
    base_net, base_H, base_mapping, base_sigma, attackable = build_operating_point(1.0)
    varied_net, varied_H, varied_mapping, varied_sigma, varied_attackable = build_operating_point(1.35)
    if base_mapping.tolist() != varied_mapping.tolist():
        raise RuntimeError("operating points changed measurement ordering")
    c_by_geometry = {geometry: make_state_vector("exact_current_operating_point", geometry, seed) for geometry in GEOMETRIES}

    clean = detector_outputs(varied_net, service)
    clean_residual = np.asarray(clean["residuals"], dtype=float)
    rows: list[dict[str, Any]] = []
    theory: list[dict[str, Any]] = []
    for geometry in GEOMETRIES:
        c = c_by_geometry[geometry]
        for knowledge in KNOWLEDGE:
            for magnitude in MAGNITUDES:
                h_for_attack = varied_H if knowledge == "exact_current_operating_point" else base_H
                delta_full = scaled_attack(h_for_attack, c, varied_mapping, varied_sigma, varied_attackable, magnitude, restrict=False)
                delta_rtu = scaled_attack(h_for_attack, c, varied_mapping, varied_sigma, varied_attackable, magnitude, restrict=True)
                for attack_scope, delta in (("all_measurements_theory", delta_full), ("rtu_reported_only", delta_rtu)):
                    net = varied_net.deepcopy() if hasattr(varied_net, "deepcopy") else None
                    if net is None:
                        import copy
                        net = copy.deepcopy(varied_net)
                    apply_attack(net, varied_mapping, delta)
                    output = detector_outputs(net, service)
                    rows.extend(
                        {
                            "geometry": geometry,
                            "knowledge": knowledge,
                            "attack_scope": attack_scope,
                            "magnitude_whitened_norm": magnitude,
                            "method": method,
                            "episode_detected": int(output[key]),
                            "max_lnr": output["max_lnr"],
                            "chi2_statistic": output["chi2_statistic"],
                        }
                        for method, key in (("chi2", "chi2_alarm"), ("lnr", "lnr_alarm"), ("pcd", "pcd_alarm"), ("nbd", "nbd_alarm"), ("fusion", "fusion_alarm"))
                    )
                    if attack_scope == "all_measurements_theory" and geometry == "single_rtu":
                        attacked_residual = np.asarray(output["residuals"], dtype=float)
                        theory.append({
                            "knowledge": knowledge,
                            "magnitude_whitened_norm": magnitude,
                            "clean_l2": float(np.linalg.norm(clean_residual)),
                            "attacked_l2": float(np.linalg.norm(attacked_residual)),
                            "absolute_l2_difference": float(np.linalg.norm(attacked_residual - clean_residual)),
                            "clean_max": float(np.max(clean_residual, initial=0.0)),
                            "attacked_max": float(np.max(attacked_residual, initial=0.0)),
                        })
    return {
        "topology": {
            "actual_attackable_measurement_count": len(attackable),
            "requested_attackable_measurement_count": 13,
            "measurement_count": len(base_mapping),
            "measurements": measurement_metadata(base_net),
            "discrepancy": "Current topology_map.py exposes 15 RTU-reported measurements; the task premise says 13. Results retain both full-theory and actual-RTU-only scopes.",
        },
        "thresholds": {"lnr": 3.0, "chi2": "production state_estimation chi-square 95% threshold", "fusion": "read-only production bundle decision_threshold"},
        "rows": rows,
        "theory_check": theory,
        "model_status": {"path": str(model_path), "loaded": bool(service.is_loaded), "decision_threshold": service.decision_threshold},
        "limitations": [
            "This is a fixed-feeder diagnostic and not a held-out scenario evaluation.",
            "NBD has no changed traffic event in an a=Hc injection, so its alarm is explicitly false; this is a network-evidence invariance diagnostic, not a trained NBD benchmark.",
            "The current code exposes 15 attackable measurements, not the requested 13; no measurements were silently removed.",
            "Nominal-topology attacks use the base-load Jacobian against a 1.35 load-scaled operating point; this is a controlled topology-knowledge contrast, not an empirical attacker trace.",
        ],
    }


def write_outputs(result: dict[str, Any], repo: Path, out_dir: Path, report_dir: Path, args: argparse.Namespace, start: str, end: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)
    result_path = out_dir / "frontier_results.json"
    frontier_path = report_dir / "frontier.csv"
    result_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    import csv
    with frontier_path.open("w", newline="", encoding="utf-8") as handle:
        fieldnames = ["geometry", "knowledge", "attack_scope", "magnitude_whitened_norm", "method", "episode_detected", "max_lnr", "chi2_statistic"]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(result["rows"])
    figure_path = report_dir / "frontier.png"
    try:
        import matplotlib.pyplot as plt
        grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
        for row in result["rows"]:
            key = (row["geometry"], row["knowledge"], row["attack_scope"])
            grouped.setdefault(key, []).append(row)
        fig, axes = plt.subplots(1, 2, figsize=(12, 5), sharey=True)
        for axis, geometry in zip(axes, GEOMETRIES):
            for method in ("chi2", "lnr", "pcd", "nbd", "fusion"):
                subset = [row for row in result["rows"] if row["geometry"] == geometry and row["method"] == method and row["attack_scope"] == "all_measurements_theory"]
                for knowledge, style in (("exact_current_operating_point", "-"), ("nominal_topology", "--")):
                    points = sorted((row["magnitude_whitened_norm"], row["episode_detected"]) for row in subset if row["knowledge"] == knowledge)
                    axis.plot([p[0] for p in points], [p[1] for p in points], linestyle=style, marker="o", label=f"{method}/{knowledge.split('_')[0]}")
            axis.set_title(geometry)
            axis.set_xlabel("Whitened attack norm")
            axis.set_ylim(-0.05, 1.05)
            axis.grid(True, alpha=0.3)
        axes[0].set_ylabel("Episode detected (0/1)")
        axes[1].legend(fontsize=7, loc="center left", bbox_to_anchor=(1.0, 0.5))
        fig.tight_layout()
        fig.savefig(figure_path, dpi=150)
        plt.close(fig)
    except Exception as exc:
        figure_path = None
        result.setdefault("warnings", []).append(f"frontier figure unavailable: {exc}")
    input_paths = [
        repo / "backend/models/fusion_classifier.joblib",
        repo / "backend/app/core/topology_map.py",
        repo / "backend/app/core/state_estimation.py",
        repo / "backend/app/core/feeder.py",
        repo / "backend/app/ml/feature_engineering.py",
        repo / "backend/app/ml/classifier_service.py",
    ]
    suite_path = Path(args.pytest_output) if args.pytest_output else None
    outputs = [result_path, frontier_path] + ([figure_path] if figure_path is not None else [])
    if suite_path is not None and suite_path.exists():
        outputs.append(suite_path)
    manifest = {
        "task": "P10",
        "git_sha": git_sha(repo),
        "python": sys.version,
        "packages": package_versions(),
        "cpu_model": platform.processor(),
        "cli_arguments": vars(args),
        "seed": args.seed,
        "start_time_utc": start,
        "end_time_utc": end,
        "input_sha256": {str(path): sha256(path) for path in input_paths},
        "output_sha256": {str(path): sha256(path) for path in outputs},
        "test_set_read": False,
        "pytest_summary": pytest_summary(Path(args.pytest_output) if args.pytest_output else None),
    }
    (out_dir / "run_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    rows = result["rows"]
    theory = result["theory_check"]
    aggregate: dict[tuple[str, str, str], list[int]] = {}
    for row in rows:
        aggregate.setdefault((row["geometry"], row["knowledge"], row["attack_scope"], row["method"]), []).append(int(row["episode_detected"]))
    lines = [
        "# P10 findings",
        "",
        "This report is generated from `frontier_results.json` by the committed P10 script. It is a physics diagnostic, not a held-out attack-detection benchmark.",
        "",
        "## Supported",
        "",
        f"- The installed pandapower estimator exposed a Jacobian with {result['topology']['measurement_count']} measurement rows and 13 estimator state variables.",
        f"- The current topology map classifies {result['topology']['actual_attackable_measurement_count']} measurements as RTU-reported and the remainder as trusted pseudo-sensors.",
        f"- The generated frontier contains {len(rows)} measured method/condition rows across the prescribed magnitude sweep and both single-RTU and coordinated two-RTU directions.",
        f"- The exact-theory residual check contains {len(theory)} measured comparisons. Each value is read from the machine-generated JSON; no metric was hand-entered.",
        f"- Full backend suite result: {pytest_summary(Path(args.pytest_output) if args.pytest_output else None)}.",
        "",
        "### Measured frontier values",
        "",
        "| Geometry | Knowledge | Scope | Method | Detected / conditions |",
        "|---|---|---|---|---:|",
    ]
    for key in sorted(aggregate):
        values = aggregate[key]
        lines.append(f"| {key[0]} | {key[1]} | {key[2]} | {key[3]} | {sum(values)} / {len(values)} |")
    lines.extend([
        "",
        "### Measured theory check",
        "",
        "| Knowledge | Magnitude | Clean residual L2 | Attacked residual L2 | Absolute L2 difference |",
        "|---|---:|---:|---:|---:|",
    ])
    for row in theory:
        lines.append(f"| {row['knowledge']} | {row['magnitude_whitened_norm']} | {row['clean_l2']:.8g} | {row['attacked_l2']:.8g} | {row['absolute_l2_difference']:.8g} |")
    lines.extend([
        "",
        "- Full-measurement `a=Hc` is the only condition for which the linear WLS residual-invariance theory applies. The RTU-only restriction is reported separately because trusted pseudo-sensors are not attackable.",
        "",
        "## Not supported",
        "",
        "- These results do not establish production detection performance, generalisation, or a failure rate on real or generated attack episodes.",
        "- No test-set file was read, and no training, tuning, or model selection was performed.",
        "- The requested 13-RTU-measurement premise is not supported by the current source of truth: `topology_map.py` exposes 15. The script did not silently coerce the code to 13.",
        "- NBD alarm rows are intentionally zero because an `a=Hc` measurement attack does not change the supplied traffic event list. This is not evidence that every network detector is blind to every coordinated attack.",
        "",
        "## Unresolved",
        "",
        "- The repository does not define an approved mapping from the requested 13 measurements to the current 15 RTU-reported measurements. P10 cannot claim acceptance for a 13-measurement frontier until that mapping is resolved.",
        "- A production-relevant frontier needs the finalized P4 scenario library, independent runs, and the frozen P5 evaluation protocol; this fixed-feeder diagnostic is insufficient for those claims.",
        "- The exact-versus-nominal distinction here uses the base-load Jacobian as the nominal reference against a 1.35 load-scaled point while keeping topology fixed. A true alternate-topology mismatch experiment requires an approved alternate topology source.",
        "",
        "## Evidence paths",
        "",
        f"- Results: `{result_path}`",
        f"- Frontier CSV: `{frontier_path}`",
        f"- Frontier figure: `{figure_path}`" if figure_path is not None else "- Frontier figure: unavailable; see the warning in `frontier_results.json`.",
        f"- Run manifest: `{out_dir / 'run_manifest.json'}`",
        f"- Source Jacobian implementation: `{repo / 'backend/.venv/Lib/site-packages/pandapower/estimation/algorithm/matrix_base.py'}`",
        "",
        "## Reproduction",
        "",
        f"`backend/.venv/Scripts/python.exe backend/scripts/expo/p10_frontier.py --out-dir {args.out_dir} --report-dir {args.report_dir} --seed {args.seed}`",
    ])
    (report_dir / "FINDINGS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", default="backend/experiments/P10")
    parser.add_argument("--report-dir", default="backend/reports/research/P10")
    parser.add_argument("--seed", type=int, default=1010)
    parser.add_argument("--pytest-output", default="")
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[3]
    start = datetime.now(timezone.utc).isoformat()
    result = run_experiment(args.seed, repo / "backend/models/fusion_classifier.joblib")
    end = datetime.now(timezone.utc).isoformat()
    write_outputs(result, repo, repo / args.out_dir, repo / args.report_dir, args, start, end)


if __name__ == "__main__":
    main()
