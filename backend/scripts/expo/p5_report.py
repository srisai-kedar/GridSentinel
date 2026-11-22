"""Render P5 findings from committed protocol and test artifacts."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import platform
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_summary(path: Path) -> dict[str, int | str]:
    text = path.read_text(encoding="utf-8", errors="replace")
    match = re.search(r"(?:(\d+) failed, )?(?:(\d+) passed)(?:, (\d+) warnings)?", text)
    if not match:
        raise ValueError(f"pytest summary not found in {path}")
    failed, passed, warnings = match.groups()
    return {"failed": int(failed or 0), "passed": int(passed), "warnings": int(warnings or 0), "raw_summary": match.group(0)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--pytest-output", type=Path, required=True)
    parser.add_argument("--focused-output", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    full = parse_summary(args.pytest_output)
    focused = parse_summary(args.focused_output)
    protocol_hash = sha256(args.protocol)
    lines = [
        "# P5 Findings", "", "## Supported", "",
        f"- Pre-registration protocol was committed before evaluation code execution; SHA-256: `{protocol_hash}`.",
        "- `eval/metrics.py` reports reading, evidence-visible, system-tick, episode, per-type recall, delay, alert-event, and clean-run false-alarm metrics from one in-memory call.",
        "- `eval/bootstrap.py` implements two-level run/episode resampling and Holm adjustment.",
        f"- Focused synthetic suite: `{focused['raw_summary']}`.",
        "", "## Not supported", "",
        "- No production model, candidate model, threshold, or test dataset was evaluated in this task.",
        "- Synthetic coverage tests validate implementation behavior only; they are not detector-performance evidence.",
        "- No final evaluation result is reported because no authorized P5 final-evaluation dataset was supplied or read.",
        "", "## Unresolved", "",
        "- Final evaluation still requires labelled validation/test runs with run duration, clean-run identity, scenario episode metadata, and model scores.",
        "- The existing repository citation-lint baseline remains separate from P5 and is not modified.",
        "", "## Test result", "",
        f"- Full backend suite: `{full['raw_summary']}`.",
    ]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    manifest = {
        "task_id": "P5",
        "git_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "python_version": platform.python_version(),
        "cpu_model": platform.processor() or platform.machine(),
        "cli_arguments": list(__import__("sys").argv),
        "seeds": {"synthetic_tests": 91},
        "started_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "ended_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "input_datasets": {str(path): sha256(path) for path in [args.protocol, args.pytest_output, args.focused_output]},
        "output_datasets": {str(args.out): sha256(args.out)},
    }
    (args.out.parent / "run_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({"full": full, "focused": focused, "protocol_sha256": protocol_hash}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
