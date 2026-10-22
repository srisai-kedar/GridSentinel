from app.ml.promotion_gate import evaluate_promotion, HISTORICAL_RECALL, HISTORICAL_FPR


def valid_metrics():
    return {
        "feature_schema_version": "3.0.0",
        "cyber_intrusion_recall": HISTORICAL_RECALL + 0.04,
        "cyber_intrusion_fpr": HISTORICAL_FPR + 0.001,
        "latency_ms_per_verdict": 3.5,
        "leakage_smoke_test": {"leakage_test_passed": True},
    }


def test_gate_accepts_candidate_when_all_pre_registered_checks_pass():
    result = evaluate_promotion(valid_metrics())
    assert result["eligible"] is True
    assert all(result["checks"].values())


def test_gate_rejects_candidate_without_three_point_recall_improvement():
    metrics = valid_metrics()
    metrics["cyber_intrusion_recall"] = HISTORICAL_RECALL + 0.02
    result = evaluate_promotion(metrics)
    assert result["eligible"] is False
    assert result["checks"]["cyber_recall_improves_by_at_least_3pp"] is False


def test_gate_rejects_candidate_with_large_fpr_increase():
    metrics = valid_metrics()
    metrics["cyber_intrusion_fpr"] = HISTORICAL_FPR + 0.003
    result = evaluate_promotion(metrics)
    assert result["eligible"] is False
    assert result["checks"]["cyber_fpr_increases_by_at_most_0_2pp"] is False
