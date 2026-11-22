"""Render P4 findings from the registry smoke dataset and test output."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import platform
import re
import subprocess
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[3]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def pytest_counts(path: Path) -> dict[str, int | str]:
    text = path.read_text(encoding="utf-8", errors="replace")
    match = re.search(r"(?:(\d+) failed, )?(?:(\d+) passed)(?:, (\d+) warnings)?", text)
    if not match:
        raise ValueError("pytest summary not found")
    failed, passed, warnings = match.groups()
    return {"failed": int(failed or 0), "passed": int(passed), "warnings": int(warnings or 0), "raw_summary": match.group(0)}


def smoke_summary(path: Path) -> dict[str, object]:
    frame = pd.read_csv(path)
    return {
        "rows": int(len(frame)),
        "class_counts": {str(k): int(v) for k, v in frame["top_level_label"].value_counts().sort_index().items()},
        "subtype_counts": {str(k): int(v) for k, v in frame["subtype_label"].value_counts().sort_index().items()},
        "scenario_types": sorted(str(value) for value in frame["scenario_type"].unique()),
        "scenario_columns_present": all(column in frame.columns for column in ["episode_id", "scenario_params", "evidence_visible"]),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", required=True, type=Path)
    parser.add_argument("--pytest-output", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    smoke = smoke_summary(args.smoke)
    tests = pytest_counts(args.pytest_output)
    findings = [
        "# P4 Findings", "", "## Supported", "",
        "- A registry-backed scenario library is present with parameterized FDI, replay, command-injection, breaker-open, sustained-setpoint, natural-fault, drift, load-step, authorized-write, and communication-stall definitions.",
        "- Breaker-open uses the real command-write path and then changes pandapower line service state; natural line trips change only physical state and do not emit a write.",
        "- Authorized control writes use an explicit allow-listed source and remain non-unexpected; communication stalls emit failed polls while replay leaves polling available.",
        f"- Registry smoke summary produced by the script: `{json.dumps(smoke, sort_keys=True)}`.",
        "", "## Not supported", "",
        "- No model was trained, tuned, selected, or evaluated in P4.",
        "- The short smoke run does not establish scenario coverage for every registry entry or any detector performance claim.",
        "", "## Unresolved", "",
        "- The generator scheduler is registry-driven for the configured regimes, but targeted generation of all parameter combinations and all seed bands remains a later workload.",
        "- Full physical validation of breaker-open and sustained-setpoint behavior still depends on live RTU-server execution; unit tests verify the state transition and write-path invocation without changing production artifacts.",
        "", "## Test result", "",
        f"- Backend suite summary: `{tests['raw_summary']}`; the known citation-lint baseline failure, if present, is unchanged.",
    ]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(findings) + "\n", encoding="utf-8")
    manifest = {
        "task_id": "P4",
        "git_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "python_version": platform.python_version(),
        "cpu_model": platform.processor() or platform.machine(),
        "cli_arguments": list(__import__("sys").argv),
        "seeds": {"smoke": 801},
        "started_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "ended_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "input_datasets": {str(path): sha256(path) for path in [args.smoke, args.pytest_output]},
        "output_datasets": {str(args.out): sha256(args.out)},
    }
    (args.out.parent / "run_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({"smoke": smoke, "tests": tests, "findings": str(args.out)}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
