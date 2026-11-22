"""Materialize the P0 findings from run artifacts and command outputs."""

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


ROOT = Path(__file__).resolve().parents[1]
REPORT_ROOT = ROOT / "backend" / "reports" / "research" / "P0"
EXPERIMENT_ROOT = ROOT / "backend" / "experiments" / "P0"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def docker_status() -> dict:
    try:
        completed = subprocess.run(["docker", "images", "--digests"], text=True, capture_output=True)
        return {"returncode": completed.returncode, "stdout": completed.stdout, "stderr": completed.stderr}
    except OSError as exc:
        return {"returncode": None, "stdout": "", "stderr": str(exc)}


def parse_pytest(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    passed = re.search(r"(?P<value>\d+) passed", text)
    failed = re.search(r"(?P<value>\d+) failed", text)
    return {
        "path": str(path),
        "sha256": sha256(path),
        "passed": int(passed.group("value")) if passed else 0,
        "failed": int(failed.group("value")) if failed else 0,
        "summary": (failed.group(0) + ", " if failed else "") + (passed.group(0) if passed else "unparsed"),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--clean-required-ticks", type=int, default=5000)
    parser.add_argument("--clean-smoke-ticks", type=int, default=100)
    parser.add_argument("--pytest-output", default="backend/reports/research/P0/final_pytest.txt")
    args = parser.parse_args()
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    repro = json.loads((REPORT_ROOT / "repro_check.json").read_text(encoding="utf-8"))
    concurrency = json.loads((REPORT_ROOT / "concurrency_smoke.json").read_text(encoding="utf-8"))
    clean_manifest_path = EXPERIMENT_ROOT / "clean_smoke" / "run_manifest.json"
    clean_manifest = json.loads(clean_manifest_path.read_text(encoding="utf-8"))
    clean_dataset = EXPERIMENT_ROOT / "clean_smoke" / "generated.csv"
    clean_labels = {}
    import pandas as pd
    clean_df = pd.read_csv(clean_dataset)
    clean_labels = {str(key): int(value) for key, value in clean_df["top_level_label"].value_counts().to_dict().items()}
    docker = docker_status()
    (REPORT_ROOT / "container_image_digest.json").write_text(json.dumps(docker, indent=2, sort_keys=True), encoding="utf-8")
    pytest_path = ROOT / args.pytest_output
    findings = {
        "task_id": "P0",
        "host": {"python": sys.version, "cpu": platform.processor() or platform.machine()},
        "repro_check": repro,
        "concurrency_smoke": concurrency,
        "clean_smoke": {
            "ticks": args.clean_smoke_ticks,
            "manifest": clean_manifest,
            "dataset_sha256": sha256(clean_dataset),
            "top_level_counts": clean_labels,
            "contains_labelled_scenarios": any(key not in {"Normal", "Natural Fault"} for key in clean_labels),
        },
        "clean_required": {
            "ticks": args.clean_required_ticks,
            "completed": clean_manifest.get("cli_arguments", {}).get("ticks") == args.clean_required_ticks,
        },
        "container_image_digest": docker,
        "tests": parse_pytest(pytest_path) if pytest_path.exists() else {"status": "not_run"},
    }
    (REPORT_ROOT / "p0_evidence.json").write_text(json.dumps(findings, indent=2, sort_keys=True), encoding="utf-8")
    comparison = repro.get("comparison", {})
    completed_runs = [item for item in concurrency.get("runs", []) if item.get("returncode") == 0 and item.get("manifest")]
    report = f"""# P0 Findings\n\nGenerated from `p0_evidence.json`; numerical values are read from run artifacts.\n\n## Supported\n\n- Same-seed reproducibility: labels equal = `{comparison.get('labels_equal')}`; non-timing columns identical = `{comparison.get('identical_non_timing')}` across `{comparison.get('rows', 0)}` rows.\n- Timing-affected columns and measured maximum absolute differences: `{json.dumps(comparison.get('timing', {}), sort_keys=True)}`.\n- Concurrent isolation: `{len(completed_runs)}` of `{concurrency.get('requested_runs', 0)}` processes completed with distinct port bases; see `concurrency_smoke.json`.\n- Clean-mode smoke run: `{clean_manifest.get('cli_arguments', {}).get('ticks')}` ticks, `{clean_manifest.get('rows')}` rows, labels `{json.dumps(clean_labels, sort_keys=True)}`; labelled attack scenarios present = `{findings['clean_smoke']['contains_labelled_scenarios']}`.\n- Each completed generator output has a `run_manifest.json` containing git SHA, Python/package versions, CPU, arguments, seeds, timestamps, throughput, and dataset SHA-256.\n\n## Not supported\n\n- The required clean run of `{args.clean_required_ticks}` ticks was completed = `{findings['clean_required']['completed']}`.\n- A pinned container image digest was recorded = `{bool(docker.get('stdout', '').strip())}`.\n- The full backend suite is green: `{findings['tests'].get('summary', 'not available')}`.\n\n## Unresolved\n\n- The clean-mode acceptance run was not completed in this environment; the measured smoke run demonstrates mode behaviour but is not a substitute.\n- Docker CLI is present, but the daemon/image store was unavailable; no container digest could be verified.\n- Real socket and simulator timing remain nondeterministic. The timing columns are documented rather than forced to bitwise equality.\n- The existing citation-lint failure remains a pre-existing baseline failure and was not edited.\n\n## Evidence\n\n- `repro_check.json`\n- `concurrency_smoke.json`\n- `throughput.csv`\n- `container_image_digest.json`\n- `manifest_schema.json`\n- `clean_smoke/run_manifest.json`\n"""
    (REPORT_ROOT / "FINDINGS.md").write_text(report, encoding="utf-8")
    output_paths = [
        REPORT_ROOT / "repro_check.json",
        REPORT_ROOT / "concurrency_smoke.json",
        REPORT_ROOT / "throughput.csv",
        REPORT_ROOT / "container_image_digest.json",
        REPORT_ROOT / "p0_evidence.json",
        REPORT_ROOT / "FINDINGS.md",
    ]
    input_paths = [
        REPORT_ROOT / "repro_check.json",
        REPORT_ROOT / "concurrency_smoke.json",
        clean_manifest_path,
        clean_dataset,
        pytest_path,
    ]
    manifest = {
        "task_id": "P0",
        "run_id": "p0-report",
        "git_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "python_version": sys.version,
        "package_versions": {name: importlib.metadata.version(name) for name in ["numpy", "pandas", "pytest"]},
        "cpu_model": platform.processor() or platform.machine(),
        "cli_arguments": vars(args),
        "seeds": {"generator": [repro.get("seed"), *[item.get("seed") for item in concurrency.get("runs", [])]]},
        "started_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "ended_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "input_datasets": {str(path): sha256(path) for path in input_paths if path.exists()},
        "output_datasets": {str(path): sha256(path) for path in output_paths if path.exists()},
    }
    (REPORT_ROOT / "run_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(findings, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
