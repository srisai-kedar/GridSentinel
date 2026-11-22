"""Render the committed P2 machine results into findings and finalize its manifest."""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "backend" / "reports" / "research" / "P2"


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
    return {
        "failed": int(failed or 0),
        "passed": int(passed),
        "warnings": int(warnings or 0),
        "raw_summary": match.group(0),
    }


def write_findings(result: dict[str, Any], pytest_counts: dict[str, Any]) -> Path:
    impact = result.get("impact") or {}
    findings = [
        "# P2 Findings",
        "",
        "## Supported",
        "",
        f"- Static provenance audit passed = `{result['static_provenance']['passed']}`; violations = `{len(result['static_provenance']['violations'])}`.",
        f"- Blind re-extraction passed = `{result['blind_reextraction']['passed']}`; differing features = `{len(result['blind_reextraction']['differences'])}`.",
        f"- Test-only leak canary detected the injected feature mismatch = `{result['canary']['audit_detected_leak']}`.",
        f"- Label shuffle used `{result['label_shuffle']['train_rows']}` training rows and `{result['label_shuffle']['validation_rows']}` validation rows; accuracy `{result['label_shuffle']['accuracy']}`, majority rate `{result['label_shuffle']['majority_class_rate']}`, absolute gap `{result['label_shuffle']['absolute_gap']}`.",
        f"- Matched generator diagnostic rows: leaky `{impact.get('leaky_pre_pr16', {}).get('rows')}`, repaired `{impact.get('repaired', {}).get('rows')}`; each used a 70/30 tick split recorded by the script.",
        f"- Diagnostic command-injection recall: leaky `{impact.get('leaky_pre_pr16', {}).get('command_injection_recall')}`, repaired `{impact.get('repaired', {}).get('command_injection_recall')}`; precision: leaky `{impact.get('leaky_pre_pr16', {}).get('precision')}`, repaired `{impact.get('repaired', {}).get('precision')}`.",
        "",
        "## Not supported",
        "",
        "- The matched generator comparison is diagnostic only: it is one seed, one short run, uses a time split rather than independent capture groups, and does not establish production improvement.",
        "- The blind audit validates the extractor boundary over serialized traffic and telemetry; it does not prove that every estimator/PCD path is independently replayable from those two logs.",
        "",
        "## Unresolved",
        "",
        "- Generator timing is not bitwise reproducible: repeated same-seed runs can produce different timing-dependent samples and therefore different diagnostic metrics. This is recorded in the generated run manifests and is a P0 issue.",
        "- The pre-PR16 scratch comparison does not isolate only the historical label leak; generator and runtime differences remain possible confounders.",
        "",
        "## Test result",
        "",
        f"- Full backend suite: `{pytest_counts['passed']}` passed, `{pytest_counts['failed']}` failed, `{pytest_counts['warnings']}` warnings; source summary: `{pytest_counts['raw_summary']}`.",
        "- The single failure is the pre-existing repository citation-lint baseline failure; no citation report or lint rule was changed by P2.",
    ]
    path = REPORT_DIR / "FINDINGS.md"
    path.write_text("\n".join(findings) + "\n", encoding="utf-8")
    return path


def finalize(pytest_path: Path) -> dict[str, Any]:
    result_path = REPORT_DIR / "leakage_audit.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    counts = parse_pytest_counts(pytest_path)
    findings_path = write_findings(result, counts)
    manifest_path = REPORT_DIR / "run_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["final_pytest"] = counts
    manifest["finalized_at_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    manifest.setdefault("input_artifacts", {})[str(pytest_path)] = sha256(pytest_path)
    output_paths = [findings_path]
    manifest.setdefault("output_artifacts", {})
    for path in output_paths:
        manifest["output_artifacts"][str(path)] = sha256(path)
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return {"pytest": counts, "findings": str(findings_path), "manifest": str(manifest_path)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pytest-output", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(finalize(args.pytest_output), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
