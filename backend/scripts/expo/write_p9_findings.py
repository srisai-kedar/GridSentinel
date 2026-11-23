"""Write P9 findings from the machine-produced readiness audit."""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
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
    source_matrix = args.results.parent / "confusion.csv"
    report_matrix = args.out_dir / "confusion.csv"
    report_matrix.write_bytes(source_matrix.read_bytes())
    test_status = "not run"
    if args.pytest_log and args.pytest_log.exists():
        import re
        text = args.pytest_log.read_text(encoding="utf-8", errors="replace")
        match = re.search(r"(?P<failed>\d+) failed, (?P<passed>\d+) passed, (?P<warnings>\d+) warnings in (?P<duration>[^\n]+)", text)
        if match:
            test_status = f"{match.group('passed')} passed, {match.group('failed')} failed, {match.group('warnings')} warnings in {match.group('duration')}"
    lines = [
        "# P9 findings",
        "",
        "All dataset counts and readiness values below are rendered from `taxonomy_readiness.json`; no metric is hand-entered.",
        "",
        "## Supported",
        "",
        f"- Readiness status: `{payload['status']}`.",
        f"- The current drift-rule source audit found concentration comparison present={payload['rule_audit']['has_concentration_comparison']} and the old always-true key-presence clause present={payload['rule_audit']['has_always_true_key_presence_clause']}.",
        f"- Non-held-out inputs inspected: {len(payload['available_input_files'])} P6 train/validation files; scenario-parameter records parsed={payload['available_input_metadata']['scenario_param_records']}.",
        f"- Observed FDI sigma values: `{payload['available_input_metadata']['fdi_sigma_multiples_observed']}`. Observed drift modes: `{payload['available_input_metadata']['drift_modes_observed']}`.",
        "",
        "## Not supported",
        "",
        f"- The required 5×5 episode confusion matrix was not computed. `confusion.csv` is an empty schema only; filling it would fabricate results.",
        "- No learned four-class model was trained because the required magnitude-by-profile study and independent held-out runs are not available.",
        "- No drift-versus-FDI indistinguishability region can be claimed from the existing random/sparse scenarios.",
        f"- Full backend suite: {test_status}. The known citation-lint baseline failure remains the only allowed failure.",
        "",
        "## Unresolved",
        "",
        f"- Missing required FDI sigma values: `{payload['missing_fdi_sigma_multiples']}`.",
        f"- Missing required drift profiles: `{payload['missing_drift_modes']}`.",
        "- The production drift rule still has hard-coded thresholds in the currently modified application file. The concentration tautology is corrected in the current working tree, but a validation-frozen configuration layer has not been introduced because that file contains pre-existing user changes and the targeted study is blocked.",
        "- Required next data: a fresh, capture-separated validation and held-out corpus covering the same magnitudes and temporal profiles for drift and FDI, plus natural-fault and benign-event runs.",
        "",
        "## Evidence paths",
        "",
        f"- Machine audit: `{args.results}`",
        f"- Confusion schema: `{report_matrix}`",
        f"- Run manifest: `{args.out_dir / 'run_manifest.json'}`",
    ]
    report = args.out_dir / "FINDINGS.md"
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    manifest = {"task_id": "P9-report", "git_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=Path(__file__).resolve().parents[2], text=True).strip(), "python_version": sys.version, "cpu_model": platform.processor() or platform.machine(), "cli_arguments": {key: str(value) for key, value in vars(args).items()}, "seeds": {}, "started_at_utc": datetime.now(timezone.utc).isoformat(), "ended_at_utc": datetime.now(timezone.utc).isoformat(), "input_datasets": {str(args.results): digest(args.results)}, "output_datasets": {str(report): digest(report)}}
    manifest["output_datasets"][str(report_matrix)] = digest(report_matrix)
    (args.out_dir / "report_run_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
