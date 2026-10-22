"""Pre-registered acceptance gate for the schema-3 ML candidate.

Model selection and threshold tuning happen only on validation data. The held-out
test set is evaluated once and is never used to tune or retrain the candidate.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Dict

HISTORICAL_RECALL = 139 / 264
HISTORICAL_FPR = 0.0043
MIN_RECALL_IMPROVEMENT = 0.03
MAX_FPR_INCREASE = 0.002
MAX_INFERENCE_MS = 50.0
REQUIRED_SCHEMA = "3.0.0"


def evaluate_promotion(metrics: Dict[str, Any]) -> Dict[str, Any]:
    recall = metrics.get("cyber_intrusion_recall")
    fpr = metrics.get("cyber_intrusion_fpr")
    latency = metrics.get("latency_ms_per_verdict")
    smoke = (metrics.get("leakage_smoke_test") or {}).get("leakage_test_passed") is True
    schema = str(metrics.get("feature_schema_version", ""))
    min_recall = HISTORICAL_RECALL + MIN_RECALL_IMPROVEMENT
    max_fpr = HISTORICAL_FPR + MAX_FPR_INCREASE
    checks = {
        "feature_schema_is_current": schema == REQUIRED_SCHEMA,
        "cyber_recall_improves_by_at_least_3pp": isinstance(recall, (int, float)) and recall >= min_recall,
        "cyber_fpr_increases_by_at_most_0_2pp": isinstance(fpr, (int, float)) and 0.0 <= fpr <= max_fpr,
        "inference_latency_below_50ms": isinstance(latency, (int, float)) and 0.0 < latency < MAX_INFERENCE_MS,
        "shuffled_label_smoke_test_passed": smoke,
    }
    return {
        "eligible": all(checks.values()),
        "checks": checks,
        "observed": {
            "feature_schema_version": schema,
            "cyber_intrusion_recall": recall,
            "cyber_intrusion_fpr": fpr,
            "latency_ms_per_verdict": latency,
        },
        "criteria": {
            "historical_cyber_recall": HISTORICAL_RECALL,
            "minimum_cyber_recall": min_recall,
            "historical_cyber_fpr": HISTORICAL_FPR,
            "maximum_cyber_fpr": max_fpr,
            "maximum_inference_latency_ms_exclusive": MAX_INFERENCE_MS,
            "required_schema": REQUIRED_SCHEMA,
        },
        "note": "Synthetic held-out test metrics; passing this gate is not field validation.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Check whether a clean-data model candidate may be proposed for promotion.")
    parser.add_argument("--metrics", required=True, help="Path to train_classifier metrics.json")
    parser.add_argument("--json-out", help="Optional path for a promotion_gate.json report")
    args = parser.parse_args()
    metrics_path = Path(args.metrics)
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    result = evaluate_promotion(metrics)
    output_path = Path(args.json_out) if args.json_out else metrics_path.with_name("promotion_gate.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

    eligible = str(result["eligible"]).lower()
    gh_output = os.environ.get("GITHUB_OUTPUT")
    if gh_output:
        with open(gh_output, "a", encoding="utf-8") as stream:
            stream.write(f"eligible={eligible}\n")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    lines = [
        "## GridSentinel ML candidate promotion gate", "",
        f"**Eligible for proposal:** {eligible.upper()}", "",
        "| Check | Result |", "|---|---|",
    ]
    lines += [f"| {name.replace('_', ' ')} | {'PASS' if passed else 'FAIL'} |" for name, passed in result["checks"].items()]
    lines += ["", "This gate evaluates one held-out synthetic test set after tuning on validation data. It is not field validation."]
    if summary:
        with open(summary, "a", encoding="utf-8") as stream:
            stream.write("\n".join(lines) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
