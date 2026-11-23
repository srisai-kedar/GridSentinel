"""Finalize P0 evidence from the isolated run outputs; never reads held-out data."""
from __future__ import annotations

import argparse, hashlib, json, platform, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--clean", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    started = datetime.now(timezone.utc)
    args.out.mkdir(parents=True, exist_ok=True)
    frame = pd.read_csv(args.clean)
    attack_labels = {"Cyber Intrusion", "Attack", "Malicious"}
    counts = frame.get("top_level_label", pd.Series(dtype=str)).value_counts().to_dict()
    evidence = {
        "task_id": "P0",
        "clean_run": {"path": str(args.clean), "ticks": int(frame["tick"].nunique()) if "tick" in frame else None, "rows": int(len(frame)), "class_counts": {str(k): int(v) for k, v in counts.items()}, "contains_attack_labels": bool(set(counts) & attack_labels)},
        "prior_reproducibility": json.loads((ROOT / "backend/reports/research/P0/repro_check.json").read_text(encoding="utf-8")),
        "prior_concurrency": json.loads((ROOT / "backend/reports/research/P0/concurrency_smoke.json").read_text(encoding="utf-8")),
        "limitations": ["The clean run is a normal/fault reference, not evidence of attack detection.", "The generator uses real sockets, so timing columns are not expected to be bitwise stable."],
    }
    result = args.out / "p0_evidence.json"
    result.write_text(json.dumps(evidence, indent=2, sort_keys=True), encoding="utf-8")
    findings = args.out / "FINDINGS.md"
    findings.write_text("# P0 Findings\n\n## Supported\n\n" +
        f"- The completion script observed `{len(frame)}` generated rows and `{frame['tick'].nunique() if 'tick' in frame else 'unknown'}` ticks in the required clean output.\n" +
        "- Prior same-seed, concurrency, and manifest evidence is preserved in the machine-readable evidence.\n\n" +
        "## Not supported\n\n- No claim is made about bitwise equality of timing-dependent network columns.\n\n## Unresolved\n\n- Docker image pinning remains unavailable if the Docker daemon is not running.\n", encoding="utf-8")
    manifest = {"task_id": "P0", "git_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(), "python_version": sys.version, "cpu_model": platform.processor() or platform.machine(), "cli_arguments": sys.argv, "seeds": {"clean": 5050}, "started_at_utc": started.isoformat(), "ended_at_utc": datetime.now(timezone.utc).isoformat(), "input_datasets": {str(args.clean): sha256(args.clean)}, "output_datasets": {str(result): sha256(result), str(findings): sha256(findings)}}
    (args.out / "run_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
