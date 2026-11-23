"""Render P6 findings from machine-produced result files."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--experiment", default="backend/experiments/P6")
    parser.add_argument("--report", default="backend/reports/research/P6/FINDINGS.md")
    parser.add_argument("--pytest-output", default="")
    args = parser.parse_args()
    experiment = Path(args.experiment)
    report = Path(args.report)
    results = pd.read_csv(experiment / "grouped_cv_validation_results.csv")
    config = json.loads((experiment / "selected_config.json").read_text(encoding="utf-8"))
    manifest = json.loads((experiment / "run_manifest.json").read_text(encoding="utf-8"))
    generated = sorted((experiment / "generated").glob("*.csv"))
    train_rows = sum(len(pd.read_csv(path)) for path in generated if path.name.startswith("train_"))
    validation_rows = sum(len(pd.read_csv(path)) for path in generated if path.name.startswith("validation_"))
    best = results.sort_values(["episode_recall", "fpr", "latency_ms"], ascending=[False, True, True]).iloc[0]
    p2 = Path("backend/reports/research/P2/leak_impact.csv")
    p2_note = "P2 leak-impact table unavailable at report time."
    if p2.exists():
        leak = pd.read_csv(p2)
        p2_note = f"P2 leak-impact rows read from `{p2}`: {len(leak)}. Values were not retyped; the source remains the authority."
    pytest_note = "Full-suite result not supplied."
    if args.pytest_output and Path(args.pytest_output).exists():
        text = Path(args.pytest_output).read_text(encoding="utf-8", errors="replace")
        tail = [line for line in text.splitlines() if "passed" in line or "failed" in line or "error" in line][-3:]
        pytest_note = " ".join(tail) if tail else "Pytest output contained no summary line."
    report.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# P6 findings",
        "",
        "All reported values below are read from the machine-generated P6 result files; no metric was hand-entered.",
        "",
        "## Supported",
        "",
        f"- Fresh run inputs: {len(manifest['input_datasets'])} CSV files from train seeds 100–119 and validation seeds 200–204.",
        f"- Generated row counts: train={train_rows}, validation={validation_rows}.",
        f"- Candidate configuration frozen in `{experiment / 'selected_config.json'}`: model `{config['model']}`, policy `{config['policy']}`, arm `{config['feature_arm']}`, threshold `{config['threshold']}`.",
        f"- Validation-selected candidate latency: {config['latency_ms']} ms per verdict; budget: {config['latency_budget_ms']} ms.",
        f"- Validation calibration ECE: {config['validation_calibration']['ece']}.",
        f"- Best validation row from grouped-CV table: feature arm `{best['feature_arm']}`, model `{best['model']}`, policy `{best['policy']}`, episode recall `{best['episode_recall']}`, FPR `{best['fpr']}`.",
        f"- Selected validation precision/recall/F1: {best['validation_precision']}/{best['validation_recall']}/{best['validation_f1']}; ROC-AUC/PR-AUC: {best['validation_roc_auc']}/{best['validation_pr_auc']}.",
        "- The nine disputed features were included only as an isolated experimental arm when `full37` or `full37_staleness` was evaluated. They were not added to the production model or production artefacts.",
        "",
        "## Not supported",
        "",
        "- No final held-out evaluation was performed in P6, so no production improvement or generalization claim is supported.",
        "- Results do not establish that the nine disputed features are safe for production; their provenance and leakage status remain governed by the P2 audit.",
        "- A validation-selected threshold is not an operational approval and is not a production threshold.",
        f"- {p2_note}",
        "",
        "## Unresolved",
        "",
        "- The generated corpus size is determined by the recorded CLI tick count and is intentionally not substituted with historical CSVs.",
        "- The validation calibration result is descriptive because calibration and threshold selection use the same validation split under the preregistered P6 constraint.",
        f"- Full backend suite status: {pytest_note}",
        "- A final evaluation requires the sole authorized final-evaluation reader and the P5 test-access log; it was not run by this task.",
        "",
        "## Evidence paths",
        "",
        f"- Experiment: `{experiment}`",
        f"- Manifest: `{experiment / 'run_manifest.json'}`",
        f"- Selection: `{experiment / 'selected_config.json'}`",
        f"- Grouped CV: `{experiment / 'grouped_cv_validation_results.csv'}`",
    ]
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
