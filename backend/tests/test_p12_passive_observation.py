from __future__ import annotations

from scripts.expo.p12_passive_observation import compare_event_sequences, function_name, normalize_capture_event


def test_passive_event_mapping_does_not_invent_observer_authority():
    event = normalize_capture_event({"function_code": 6, "source_ip": "127.0.0.1", "response_matched": True, "success": True, "transaction_id": 4, "unit_id": 1})
    assert event["function_name"] == "WRITE_SINGLE_REGISTER"
    assert event["is_unexpected_write"] is False
    assert event["observer_verified"] is False


def test_event_comparison_reports_common_field_agreement_and_timing():
    tap = [{"function_code": 3, "response_matched": True, "success": True, "transaction_id": 1, "unit_id": 1, "response_time_ms": 10.0}]
    capture = [{"function_code": 3, "response_matched": True, "success": True, "transaction_id": 1, "unit_id": 1, "response_time_ms": 11.0}]
    result = compare_event_sequences(tap, capture, timing_tolerance_ms=2.0)
    assert result["feature_agreement"]["function_code"]["fraction"] == 1.0
    assert result["timing_bias_ms"] == 1.0
    assert result["timing_within_tolerance"] == 1.0


def test_unknown_function_is_not_given_a_fake_name():
    assert function_name(99) is None
