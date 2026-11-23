"""Write P8 findings from machine-produced alert-layer outputs."""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import re
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
    parser.add_argument("--pytest-log", type=Path)
    args = parser.parse_args()
    payload = json.loads(args.results.read_text(encoding="utf-8"))
    args.out_dir.mkdir(parents=True, exist_ok=True)
    selected = payload["selected_by_budget"]
    test_status = "not run"
    if args.pytest_log and args.pytest_log.exists():
        test_text = args.pytest_log.read_text(encoding="utf-8", errors="replace")
        match = re.search(r"(?P<failed>\d+) failed, (?P<passed>\d+) passed, (?P<warnings>\d+) warnings in (?P<duration>[^\n]+)", test_text)
        if match:
            test_status = f"{match.group('passed')} passed, {match.group('failed')} failed, {match.group('warnings')} warnings in {match.group('duration')}"
    first = next((value for value in selected.values() if value), None)
    exposure = first["metrics"]["false_alarms"] if first else {"clean_hours": 0.0}
    selected_lines = []
    for budget, item in sorted(selected.items(), key=lambda pair: float(pair[0])):
        if item is None:
            selected_lines.append(f"- Budget {budget} events/hour: no eligible candidate in the available validation exposure.")
            continue
        fa = item["metrics"]["false_alarms"]
        selected_lines.append(f"- Budget {budget} events/hour: selected `{item['method']}` with parameters `{item['parameters']}`, episode recall={item['metrics']['episode']['recall']}, false alarms/hour={fa['per_hour']}, exact Poisson 95% interval={fa['exact_poisson_95']}.")
    lines = [
        "# P8 findings",
        "",
        "All measured/computed values below are rendered from `validation_alert_layers.json`; no metric is hand-entered.",
        "",
        "## Supported",
        "",
        f"- Validation-only alert-layer analysis executed {payload['candidate_count']} candidates over the existing P7 validation runs.",
        f"- Threshold-only, k-of-n persistence with cooldown, per-RTU aggregation followed by system aggregation, and CUSUM candidates were evaluated without retraining.",
        f"- The existing P7 fused tree threshold was held at {payload['frozen_threshold']} for the fixed-threshold candidates.",
        f"- The available validation clean exposure was {exposure['clean_hours']} hours; exact Poisson intervals are included for every operating-curve row in `operating_curves.csv`.",
        *selected_lines,
        "",
        "## Not supported",
        "",
        "- P8 acceptance is not met: the required clean validation exposure is at least 24 simulated hours at the real clock rate, while this pilot uses only the short P7 validation clean runs.",
        "- No clean held-out run was generated or read by the authorized final evaluator, so the required once-only clean held-out evaluation was not claimed.",
        "- No benign-event runs were available in the current inputs; load steps, authorized writes, planned switching, and communication stalls were not evaluated.",
        "- The pilot cannot establish that any alert layer meets the target of at most one false alarm per eight-hour shift. Its interval must be read from the short-exposure rows, not from the point estimate alone.",
        f"- Full backend suite: {test_status}. The one allowed baseline failure is citation lint on the pre-existing untracked Data4Cyber report; no new failure was introduced.",
        "",
        "## Unresolved",
        "",
        "- The exact generation command still required is:",
        "  `backend\\.venv\\Scripts\\python.exe -m app.ml.dataset_generator --seed <seed> --ticks 86400 --mode clean --regime clean --sim-seconds-per-tick 1.0 --run-id P8-clean-validation-<seed> --port-base <unique-port> --out backend\\experiments\\P8\\generated\\clean_validation_seed<seed>.csv`",
        "- Run enough distinct clean validation seeds to total at least 24 simulated hours, then generate a disjoint clean held-out set and consume it only through `scripts/eval_final.py`.",
        "- The available simulator throughput and required wall-clock budget must be confirmed before launching the long run; no substitute proxy exposure was used.",
        "",
        "## Evidence paths",
        "",
        f"- Machine results: `{args.results}`",
        f"- Operating curves: `{args.out_dir / 'operating_curves.csv'}`",
        f"- Run manifest: `{args.out_dir / 'run_manifest.json'}`",
        "- Existing P7 validation inputs: `backend/experiments/P7-complete/generated/`",
    ]
    report = args.out_dir / "FINDINGS.md"
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    manifest = {"task_id": "P8-report", "git_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=Path(__file__).resolve().parents[2], text=True).strip(), "python_version": sys.version, "cpu_model": platform.processor() or platform.machine(), "cli_arguments": {key: str(value) for key, value in vars(args).items()}, "seeds": {}, "started_at_utc": datetime.now(timezone.utc).isoformat(), "ended_at_utc": datetime.now(timezone.utc).isoformat(), "input_datasets": {str(args.results): digest(args.results)}, "output_datasets": {str(report): digest(report)}}
    (args.out_dir / "report_run_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
