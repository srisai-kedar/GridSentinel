#!/usr/bin/env python3
"""
scripts/promote_candidate.py
----------------------------
Safe promotion utility for GridSentinel Change 5 candidate models.

MANDATORY SAFETY RULES:
  1. Requires explicit `--confirm` flag to execute promotion.
  2. Refuses promotion unless reports/dpn_ablation/decision_report.json explicitly
     declares decision == "PROMOTE".
  3. Archives the currently deployed artifact under models/archive/ with its
     full SHA256 checksum recorded.
  4. Prints exact rollback command for immediate recovery.
  5. Never executes automatically.
"""

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path


def compute_sha256(file_path: Path) -> str:
    """Compute hex SHA256 of a file."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def promote(confirm: bool = False, report_path: Path = None, candidate_path: Path = None, backend_dir: Path = None) -> int:
    backend_dir = backend_dir or Path(__file__).resolve().parent.parent / "gridsentinel" / "backend"
    if not backend_dir.exists():
        # Fallback to current working directory backend
        backend_dir = Path(".").resolve()
        if (backend_dir / "backend").exists():
            backend_dir = backend_dir / "backend"

    report_path = report_path or (backend_dir / "reports" / "dpn_ablation" / "decision_report.json")
    models_dir = backend_dir / "models"
    deployed_path = models_dir / "fusion_classifier.joblib"
    archive_dir = models_dir / "archive"

    print("=" * 70)
    print("GRIDSENTINEL CANDIDATE PROMOTION SCRIPT")
    print("=" * 70)

    # 1. Verification of report existence and decision
    if not report_path.exists():
        print(f"[ERROR] Decision report not found at {report_path}.")
        print("Ablation harness must be run before promotion can be considered.")
        return 1

    with open(report_path, "r", encoding="utf-8") as f:
        report_data = json.load(f)

    decision = report_data.get("decision", "NO-PROMOTE")
    candidate_file = report_data.get("candidate_artifact")

    if decision != "PROMOTE":
        print(f"[REFUSED] Decision in report is '{decision}'.")
        print("Pre-registered decision protocol permits promotion ONLY when decision == 'PROMOTE'.")
        print("No changes made to deployed model artifact.")
        return 1

    if not candidate_file:
        print("[ERROR] Decision is PROMOTE, but no candidate_artifact is listed in report.")
        return 1

    candidate_full_path = candidate_path or (backend_dir / candidate_file)
    if not candidate_full_path.exists():
        print(f"[ERROR] Candidate artifact file not found at: {candidate_full_path}")
        return 1

    # 2. Check for explicit --confirm flag
    if not confirm:
        print("[REFUSED] Missing --confirm flag.")
        print(f"Candidate available: {candidate_full_path.name}")
        print("To proceed with promotion, re-run with explicit --confirm flag:")
        print(f"  python scripts/promote_candidate.py --confirm")
        return 1

    # 3. Archive currently deployed artifact
    archive_dir.mkdir(parents=True, exist_ok=True)
    if deployed_path.exists():
        curr_sha = compute_sha256(deployed_path)
        archive_name = f"fusion_classifier_backup_{curr_sha[:8]}.joblib"
        archive_target = archive_dir / archive_name
        shutil.copy2(deployed_path, archive_target)
        print(f"[ARCHIVED] Current model archived to: {archive_target}")
        print(f"           SHA256: {curr_sha}")
    else:
        curr_sha = "NONE"
        archive_target = None
        print("[NOTICE] No deployed model found at target path. Proceeding with fresh install.")

    # 4. Promote candidate artifact
    cand_sha = compute_sha256(candidate_full_path)
    shutil.copy2(candidate_full_path, deployed_path)
    print(f"[PROMOTED] Installed candidate to: {deployed_path}")
    print(f"           New SHA256: {cand_sha}")

    # 5. Output exact rollback instructions
    print("\n" + "-" * 70)
    print("ROLLBACK COMMAND (in case of post-deployment anomaly):")
    if archive_target and archive_target.exists():
        print(f"  copy \"{archive_target}\" \"{deployed_path}\"")
    else:
        print("  git checkout models/fusion_classifier.joblib")
    print("-" * 70)
    print("[SUCCESS] Promotion completed successfully.")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Promote GridSentinel Candidate ML Model")
    parser.add_argument("--confirm", action="store_true", help="Explicit confirmation required to promote")
    parser.add_argument("--report", type=str, default=None, help="Path to decision_report.json")
    parser.add_argument("--candidate", type=str, default=None, help="Path to candidate joblib file")
    args = parser.parse_args()

    report_path = Path(args.report) if args.report else None
    cand_path = Path(args.candidate) if args.candidate else None
    code = promote(confirm=args.confirm, report_path=report_path, candidate_path=cand_path)
    sys.exit(code)


if __name__ == "__main__":
    main()
