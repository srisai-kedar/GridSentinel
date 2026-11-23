"""P8 validation-only alert-layer analysis over saved P7 predictions."""
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
from typing import Any, Callable

import joblib
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
REPO = ROOT.parent
for path in (ROOT, REPO):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from eval.metrics import evaluate, poisson_interval  # noqa: E402
from scripts.baselines import FUSION_FEATURES  # noqa: E402
from scripts.expo.train_v2 import add_staleness_features  # noqa: E402


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_validation(data_dir: Path) -> tuple[pd.DataFrame, list[Path]]:
    paths = sorted(data_dir.glob("validation_seed*.csv")) + sorted(data_dir.glob("clean_validation_seed*.csv"))
    if not paths:
        raise FileNotFoundError(f"validation files not found in {data_dir}")
    frames = [pd.read_csv(path) for path in paths]
    return add_staleness_features(pd.concat(frames, ignore_index=True)), paths


def persistence_alerts(frame: pd.DataFrame, scores: np.ndarray, threshold: float, k: int, n: int, cooldown: int) -> np.ndarray:
    if not 1 <= k <= n:
        raise ValueError("k must be between 1 and n")
    out = np.zeros(len(frame), dtype=bool)
    order = frame.assign(_row=np.arange(len(frame))).sort_values(["run_id", "rtu_id", "tick", "_row"])
    for (_, _), group in order.groupby(["run_id", "rtu_id"], sort=False):
        history: list[bool] = []
        last_alarm = -10**9
        for row_index in group["_row"]:
            index = int(row_index)
            history.append(bool(scores[index] >= threshold))
            window = history[-n:]
            tick = int(frame.iloc[index]["tick"])
            if len(window) == n and sum(window) >= k and tick - last_alarm > cooldown:
                out[index] = True
                last_alarm = tick
    return out


def cusum_alerts(frame: pd.DataFrame, scores: np.ndarray, threshold: float, drift: float, alarm: float, cooldown: int) -> np.ndarray:
    if drift < 0 or alarm <= 0:
        raise ValueError("drift must be non-negative and alarm must be positive")
    out = np.zeros(len(frame), dtype=bool)
    order = frame.assign(_row=np.arange(len(frame))).sort_values(["run_id", "rtu_id", "tick", "_row"])
    for (_, _), group in order.groupby(["run_id", "rtu_id"], sort=False):
        cumulative = 0.0
        last_alarm = -10**9
        for row_index in group["_row"]:
            index = int(row_index)
            cumulative = max(0.0, cumulative + float(scores[index] - threshold - drift))
            tick = int(frame.iloc[index]["tick"])
            if cumulative >= alarm and tick - last_alarm > cooldown:
                out[index] = True
                last_alarm = tick
                cumulative = 0.0
    return out


def metric(frame: pd.DataFrame, alerts: np.ndarray, label: str, parameters: dict[str, Any]) -> dict[str, Any]:
    rows = frame.to_dict(orient="records")
    observed = [dict(row, alert=bool(alert)) for row, alert in zip(rows, alerts)]
    clean_runs = {str(run): float(group["duration_hours"].iloc[0]) for run, group in frame[frame["is_clean_run"].astype(bool)].groupby("run_id")}
    result = evaluate(observed, clean_runs=clean_runs, gap=0, tail=0, grace=0)
    return {"method": label, "parameters": parameters, "metrics": result}


def choose_for_budget(candidates: list[dict[str, Any]], budget: float) -> dict[str, Any] | None:
    eligible = [item for item in candidates if item["metrics"]["false_alarms"]["per_hour"] is not None and item["metrics"]["false_alarms"]["per_hour"] <= budget]
    if not eligible:
        return None
    return max(eligible, key=lambda item: (item["metrics"]["episode"]["recall"] or 0.0, -(item["metrics"]["false_alarms"]["per_hour"] or 0.0), float(item["parameters"].get("threshold", 0.0))))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=ROOT / "experiments" / "P7-complete" / "generated")
    parser.add_argument("--bundle", type=Path, default=ROOT / "experiments" / "P7-complete" / "p7_baseline_bundle.joblib")
    parser.add_argument("--out-dir", type=Path, default=ROOT / "experiments" / "P8")
    args = parser.parse_args()
    started = datetime.now(timezone.utc)
    frame, input_paths = load_validation(args.data_dir)
    bundle = joblib.load(args.bundle)
    model = bundle["models"]["tree_depth3"]
    scores = np.asarray(model.predict_proba(frame[FUSION_FEATURES].fillna(0.0)))[:, 1]
    frozen_threshold = float(bundle["thresholds"]["tree_depth3"])
    threshold_values = sorted(set(float(value) for value in scores), reverse=True)
    candidates: list[dict[str, Any]] = []
    for threshold in threshold_values:
        candidates.append(metric(frame, scores >= threshold, "threshold_only", {"threshold": threshold, "aggregation": "system_any"}))
    for k, n in ((1, 1), (2, 3), (2, 4), (3, 5)):
        for cooldown in (0, 1, 4):
            for threshold in (frozen_threshold, *threshold_values):
                alerts = persistence_alerts(frame, scores, threshold, k, n, cooldown)
                candidates.append(metric(frame, alerts, "persistence", {"threshold": threshold, "k": k, "n": n, "cooldown": cooldown, "aggregation": "per_rtu_then_system_any"}))
    for threshold in (frozen_threshold, *threshold_values):
        alerts = cusum_alerts(frame, scores, threshold, drift=0.01, alarm=0.25, cooldown=0)
        candidates.append(metric(frame, alerts, "cusum", {"threshold": threshold, "drift": 0.01, "alarm": 0.25, "cooldown": 0, "aggregation": "per_rtu_then_system_any"}))
    selected = {str(budget): choose_for_budget(candidates, budget) for budget in (1.0, 5.0, 20.0)}
    out = args.out_dir
    out.mkdir(parents=True, exist_ok=True)
    result_path = out / "validation_alert_layers.json"
    payload = {"task_id": "P8", "scope": "validation_only_pilot_on_existing_P7_validation_runs", "frozen_threshold": frozen_threshold, "candidate_count": len(candidates), "selected_by_budget": selected, "operating_curve": candidates, "input_paths": [str(path) for path in input_paths], "started_at_utc": started.isoformat(), "ended_at_utc": datetime.now(timezone.utc).isoformat()}
    result_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    curve_path = out / "operating_curves.csv"
    curve_rows = []
    for item in candidates:
        metrics = item["metrics"]
        curve_rows.append({"method": item["method"], **item["parameters"], "episode_recall": metrics["episode"]["recall"], "false_alarm_events": metrics["false_alarms"]["events"], "false_alarm_per_hour": metrics["false_alarms"]["per_hour"], "clean_hours": metrics["false_alarms"]["clean_hours"], "poisson_low": (metrics["false_alarms"]["exact_poisson_95"] or [None, None])[0], "poisson_high": (metrics["false_alarms"]["exact_poisson_95"] or [None, None])[1]})
    pd.DataFrame(curve_rows).to_csv(curve_path, index=False)
    manifest = {"task_id": "P8", "git_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip(), "python_version": sys.version, "package_versions": {name: importlib.metadata.version(name) for name in ["numpy", "pandas", "scikit-learn", "scipy"]}, "cpu_model": platform.processor() or platform.machine(), "cli_arguments": {key: str(value) for key, value in vars(args).items()}, "seeds": {}, "started_at_utc": started.isoformat(), "ended_at_utc": datetime.now(timezone.utc).isoformat(), "input_datasets": {str(path): sha256(path) for path in input_paths + [args.bundle]}, "output_datasets": {str(result_path): sha256(result_path), str(curve_path): sha256(curve_path)}}
    (out / "run_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({"candidate_count": len(candidates), "selected_by_budget": {key: bool(value) for key, value in selected.items()}, "output": str(result_path)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
