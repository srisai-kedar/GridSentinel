"""Create P3 findings from the descriptor and test output artifacts."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import platform
import re
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_pytest_counts(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="replace")
    match = re.search(r"(?:(\d+) failed, )?(?:(\d+) passed)(?:, (\d+) warnings)?", text)
    if not match:
        raise ValueError(f"pytest summary not found in {path}")
    failed, passed, warnings = match.groups()
    return {"failed": int(failed or 0), "passed": int(passed), "warnings": int(warnings or 0), "raw_summary": match.group(0)}


def write_findings(description_path: Path, pytest_path: Path, output: Path) -> dict[str, Any]:
    description = json.loads(description_path.read_text(encoding="utf-8"))
    pytest_counts = parse_pytest_counts(pytest_path)
    lines = [
        "# P3 Findings",
        "",
        "## Supported",
        "",
        "- Dataset rows now carry `episode_id`, `scenario_type`, JSON `scenario_params`, `onset_tick`, `end_tick`, `attack_active`, `evidence_visible`, and JSON `affected_rtus`; legacy labels remain present.",
        "- The generator supports `stress`, `operational`, and `clean` prevalence regimes; `--compressed-stress` explicitly selects the legacy 900-second simulated tick, while the default simulated tick is one second.",
        "- Load variation is reproducibly seeded and includes per-bus phase/shape offsets, OU variability, day scaling, and occasional persistent load steps. `ood` selects a distinct profile family and noise scale.",
        f"- Descriptor smoke output: `{json.dumps(description, sort_keys=True)}`.",
        "",
        "## Not supported",
        "",
        "- No candidate model was trained, tuned, selected, or evaluated in P3.",
        "- The smoke run is not evidence of prevalence or generalization; it is only an end-to-end schema and runtime check.",
        "- The current simulation has no separate benign-event injector, so the operational regime represents the documented 5% benign-event intent through the existing Normal class rather than claiming a distinct benign-event label.",
        "",
        "## Unresolved",
        "",
        "- Full seed-band generation has not been run in this task; the bands are recorded in generator manifests for later controlled generation.",
        "- Command-injection evidence visibility is tied to the observer-verified write appearing in the rolling traffic window; physical consequence evidence is not synthesized.",
        "",
        "## Test result",
        "",
        f"- Backend suite summary: `{pytest_counts['raw_summary']}`; the known citation-lint baseline failure, if present, is not changed by P3.",
    ]
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"description": description, "pytest": pytest_counts, "findings": str(output)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--description", required=True, type=Path)
    parser.add_argument("--pytest-output", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    result = write_findings(args.description, args.pytest_output, args.out)
    manifest = {
        "task_id": "P3",
        "git_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "python_version": platform.python_version(),
        "cpu_model": platform.processor() or platform.machine(),
        "cli_arguments": list(__import__("sys").argv),
        "seeds": {"smoke": 701},
        "started_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "ended_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "input_datasets": {str(path): sha256(path) for path in [args.description, args.pytest_output]},
        "output_datasets": {str(args.out): sha256(args.out)},
    }
    manifest_path = args.out.parent / "run_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
