"""
test_validation_metrics.py
--------------------------
Unit and integration tests for validation_report.py.
Verifies Wilson intervals, cyber breakdown formulas, episode aggregation,
provenance hashes, and end-to-end report generation.
"""

import json
from pathlib import Path
import pytest

from app.ml.validation_report import (
    wilson_score_interval,
    compute_cyber_breakdown,
    compute_episode_metrics,
    compute_sha256,
)


def test_wilson_score_interval_properties():
    """Test 1: Wilson interval correctness against verified analytical bounds."""
    # 3 successes of 10 gives approx (0.108, 0.603) at 95% CI (tolerance 0.002)
    ci_3_10 = wilson_score_interval(3, 10, confidence=0.95)
    assert abs(ci_3_10[0] - 0.108) <= 0.002, f"Expected lower ~0.108, got {ci_3_10[0]}"
    assert abs(ci_3_10[1] - 0.603) <= 0.002, f"Expected upper ~0.603, got {ci_3_10[1]}"

    # 0 successes of 50 gives lower bound 0 and upper approx 0.0713 (tolerance 0.002)
    ci_0_50 = wilson_score_interval(0, 50, confidence=0.95)
    assert abs(ci_0_50[0] - 0.0) <= 0.002, f"Expected lower 0.0, got {ci_0_50[0]}"
    assert abs(ci_0_50[1] - 0.0713) <= 0.002, f"Expected upper ~0.0713, got {ci_0_50[1]}"


def test_cyber_breakdown_identity():
    """Test 2: Cyber breakdown on hand-built confusion matrix row."""
    # Cyber row: 7 predicted Cyber, 2 predicted Normal, 1 predicted Fault
    predictions = ["Cyber Intrusion"] * 7 + ["Normal"] * 2 + ["Natural Fault"] * 1
    cyber_indices = list(range(10))

    breakdown = compute_cyber_breakdown(cyber_indices, predictions)

    assert breakdown["n"] == 10
    assert breakdown["tp"] == 7
    assert breakdown["fn"] == 3
    assert abs(breakdown["fnr_strict"] - 0.30) < 1e-6
    assert abs(breakdown["miss_to_normal_rate"] - 0.20) < 1e-6
    assert abs(breakdown["miss_to_fault_rate"] - 0.10) < 1e-6

    # Strict sum identity check
    assert abs(breakdown["fnr_strict"] - (breakdown["miss_to_normal_rate"] + breakdown["miss_to_fault_rate"])) < 1e-9


def test_episode_logic():
    """Test 3: Episode aggregation logic and false-alarm detection."""
    # true = [N,A,A,N,A,A,A,N,A,A]
    # pred = [N,N,N,N,C,N,N,C,N,N]
    true_seq = ["N", "A", "A", "N", "A", "A", "A", "N", "A", "A"]
    pred_seq = ["N", "N", "N", "N", "C", "N", "N", "C", "N", "N"]

    ep = compute_episode_metrics(
        true_labels=true_seq,
        pred_labels=pred_seq,
        cyber_label="A",
        pred_cyber_label="C",
        fault_label="F",
        tick_duration_seconds=1.0,
    )

    # Expect 3 episodes: [1..2], [4..6], [8..9]
    assert ep["total_episodes"] == 3

    # Episode starting at index 4 is detected (pred is C at index 4), delay is 0
    assert ep["detected_episodes"] == 1
    assert abs(ep["episode_detection_rate"] - (1.0 / 3.0)) < 1e-6
    assert ep["detection_delays"] == [0]
    assert ep["median_delay_ticks"] == 0.0

    # Exactly 1 false-alarm episode at index 7 (pred C on true N)
    assert ep["false_alarm_episodes"] == 1


def test_provenance_and_hashes():
    """Test 4: Provenance hash verification."""
    backend_dir = Path(__file__).resolve().parent.parent
    model_path = backend_dir / "models" / "fusion_classifier.joblib"
    test_path = backend_dir / "data" / "generated" / "test_dataset_seed1337.csv"

    model_hash = compute_sha256(model_path)
    test_hash = compute_sha256(test_path)

    assert model_hash == "ee5211510e41eddac32ed1eed405af982a0a550bd0b75e8867253135b812ccae"
    assert test_hash == "a8ca03f3dd18f2454f132bd8e41a4f95e35bd0d1426e2a5e9085c5b1c6e22f2c"


def test_integration_validation_report_cli():
    """Test 5: Integration test running report generator and verifying JSON & MD outputs."""
    backend_dir = Path(__file__).resolve().parent.parent
    repo_root = backend_dir.parent

    # Execute validation report generator module
    from app.ml.validation_report import main
    import sys

    # Invoke main with explicit empty arguments
    main([])

    json_path = backend_dir / "reports" / "validation_report.json"
    md_reports_path = backend_dir / "reports" / "VALIDATION_REPORT.md"
    docs_output = repo_root / "docs" / "VALIDATION_REPORT.md"

    assert json_path.exists(), f"Missing {json_path}"
    assert md_reports_path.exists(), f"Missing {md_reports_path}"
    assert docs_output.exists(), f"Missing {docs_output}"

    # Verify JSON structure
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert "provenance" in data
    assert "headline_metrics" in data
    assert "test_metrics" in data
    assert data["provenance"]["model_sha256"] == "ee5211510e41eddac32ed1eed405af982a0a550bd0b75e8867253135b812ccae"
    assert data["provenance"]["test_dataset_sha256"] == "a8ca03f3dd18f2454f132bd8e41a4f95e35bd0d1426e2a5e9085c5b1c6e22f2c"
    assert data["reproducibility"]["accuracy_status"] == "MATCH (Reproduced)"
    assert data["reproducibility"]["fpr_status"] == "MATCH (Reproduced)"
