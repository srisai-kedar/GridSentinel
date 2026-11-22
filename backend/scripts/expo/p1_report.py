"""Generate the committed P1 findings report from diagnostic artifacts."""

from __future__ import annotations

import argparse
import datetime
import hashlib
import importlib.metadata
import json
import platform
import re
import subprocess
import sys
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def pytest_counts(path: Path) -> dict[str, int]:
    text = path.read_text(encoding="utf-8")
    passed = re.search(r"(\d+) passed", text)
    failed = re.search(r"(\d+) failed", text)
    return {"passed": int(passed.group(1)) if passed else 0, "failed": int(failed.group(1)) if failed else 0}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--diagnostic", default="experiments/P1/attribution_diagnostic_seed42_120/diagnostic_results.json")
    parser.add_argument("--pytest-output", default="reports/research/P1/final_pytest.txt")
    parser.add_argument("--out-dir", default="reports/research/P1")
    args = parser.parse_args()
    root = Path.cwd()
    diagnostic_path = root / args.diagnostic
    pytest_path = root / args.pytest_output
    out_dir = root / args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    diagnostic = json.loads(diagnostic_path.read_text(encoding="utf-8"))
    counts = pytest_counts(pytest_path)
    changed = {name: value for name, value in diagnostic["feature_changes"].items() if value["rows_changed"]}
    report = [
        "# P1 Findings", "", "All numbers below are generated from `diagnostic_results.json` and the recorded pytest output.", "",
        "## Supported", "",
        f"- The shared topology map covers RTUs `{', '.join(map(str, range(1, 6)))}` and explicitly identifies trusted pseudo-sensors.",
        f"- The same diagnostic stream contained `{diagnostic['rows']}` rows; the same pre-existing model bundle and threshold `{diagnostic['model']['threshold']}` were used for both mappings.",
        f"- Changed features ({len(changed)}):",
        "",
        "| Feature | Rows changed | Maximum absolute difference |",
        "|---|---:|---:|",
    ]
    for name, value in sorted(changed.items()):
        report.append(f"| `{name}` | {value['rows_changed']} | {value['max_absolute_difference']} |" )
    report += [
        "", "| Mapping | Overall cyber recall |", "|---|---:|",
        f"| Legacy diagnostic mapping | {diagnostic['overall_attack_recall']['legacy_mapping']} |",
        f"| Corrected topology mapping | {diagnostic['overall_attack_recall']['corrected_mapping']} |",
        "", "| Mapping | Attack subtype | Support | Recall |", "|---|---|---:|---:|",
    ]
    for mapping, values in diagnostic["per_subtype_recall"].items():
        for subtype, metric in values.items():
            report.append(f"| {mapping} | {subtype} | {metric['support']} | {metric['recall']} |")
    report += [
        "", "## Not supported", "",
        "- This diagnostic does not establish an independent improvement or a production-model promotion decision.",
        f"- The full backend suite is not fully green: `{counts['passed']}` passed and `{counts['failed']}` failed; the failure classification is recorded in the raw output.",
        "- The diagnostic stream is not a held-out final test set and contains no cyber rows if the recorded support table is empty for a subtype.",
        "", "## Unresolved", "",
        "- The WLS estimator can distribute a +10σ P/Q perturbation across measurements; the tests verify exact ownership and corrected element-type matching, not that every global WLS maximum must be the injected P/Q row.",
        "- The selected experimental bundle was serialized under a different scikit-learn patch version; loading emitted an `InconsistentVersionWarning`.",
        "- Timing and socket behavior remain environment-dependent.",
        "", "## Evidence", "",
        f"- Diagnostic JSON: `{diagnostic_path}` (SHA-256 `{sha256(diagnostic_path)}`)",
        f"- Diagnostic run manifest: `{diagnostic_path.parent / 'run_manifest.json'}`",
        f"- Test output: `{pytest_path}` (SHA-256 `{sha256(pytest_path)}`)",
        "- No production model or frozen metrics file was modified.",
    ]
    report_path = out_dir / "FINDINGS.md"
    report_path.write_text("\n".join(report) + "\n", encoding="utf-8")
    manifest = {
        "task_id": "P1",
        "run_id": "p1-report",
        "git_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "python_version": platform.python_version(),
        "package_versions": {name: importlib.metadata.version(name) for name in ["numpy", "pandas", "pytest"]},
        "cpu_model": platform.processor() or platform.machine(),
        "cli_arguments": vars(args),
        "seeds": {"diagnostic": diagnostic.get("seed")},
        "started_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "ended_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "input_datasets": {str(path): sha256(path) for path in [diagnostic_path, pytest_path]},
        "output_datasets": {str(path): sha256(path) for path in [report_path]},
    }
    (out_dir / "run_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    print(report_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
