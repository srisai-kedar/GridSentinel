"""
Regression tests for NBD data-leakage prevention.

Validates that:
  1. Untagged events (missing sources, flags, or function codes) never contribute
     to nbd_unexpected_write_count.
  2. Caller-supplied flags (from attacker clients, scenario injectors, or test stubs)
     are strictly ignored in both traffic_logger and feature extraction.
  3. Source-label manipulation (fake/spoofed sources, FC mismatch, or RTU observer tags)
     cannot inflate nbd_unexpected_write_count or pollute nbd_distinct_sources_count.
  4. Only explicitly identified RTU-server-observed Modbus write requests
     (source == 'RTU_OBSERVED_WRITE' and FC in {5, 6, 15, 16}) contribute.
  5. The frozen FEATURE_SCHEMA and model compatibility remain strictly intact.
"""

import pytest
from typing import Any, Dict, List

from app.ml.feature_engineering import (
    FEATURE_SCHEMA,
    RTU_OBSERVED_WRITE_SOURCE,
    extract_features,
    features_to_vector,
)
from app.ot.traffic_logger import ModbusTrafficLogger


def _dummy_se_result() -> Dict[str, Any]:
    return {
        "success": True,
        "chi2_test_passed": True,
        "chi2_statistic": 3.5,
        "chi2_threshold": 15.0,
        "flagged_measurements": [],
        "bad_data_detected": False,
        "status_code": 1,
    }


class TestNbdLeakageRegressions:
    """Regression suite enforcing zero data leakage in NBD feature computation."""

    def test_untagged_events_do_not_contribute_to_unexpected_writes(self):
        """Untagged, malformed, or empty traffic events must never increment unexpected_writes."""
        untagged_events = [
            {},  # completely empty event
            {"target_rtu": "RTU_1 (Port 5021)"},  # missing source, FC, flag
            {"target_rtu": "RTU_1 (Port 5021)", "function_code": 6},  # missing source and flag
            {"target_rtu": "RTU_1 (Port 5021)", "source": None, "function_code": 6, "is_unexpected_write": True},
            {"target_rtu": "RTU_1 (Port 5021)", "source": "", "function_code": 6, "is_unexpected_write": True},
            {"target_rtu": "RTU_1 (Port 5021)", "source": "UNKNOWN", "function_code": 0, "is_unexpected_write": False},
        ]
        feats = extract_features(
            traffic_events=untagged_events,
            state_estimation_result=_dummy_se_result(),
            target_rtu_id=1,
        )
        assert feats["nbd_unexpected_write_count"] == 0.0, (
            "Untagged events must NOT contribute to nbd_unexpected_write_count."
        )

    def test_caller_supplied_flags_are_ignored(self):
        """
        Caller-supplied is_unexpected_write=True flags from non-RTU observer sources
        (e.g., ATTACKER, SCADA_MASTER, or test clients) must be strictly ignored.
        """
        caller_flagged_events = [
            # External attacker client setting flag
            {
                "target_rtu": "RTU_1 (Port 5021)",
                "source": "ATTACKER",
                "function_code": 6,
                "is_unexpected_write": True,
                "response_time_ms": 10.0,
                "success": True,
            },
            # Simulation scenario injector setting flag
            {
                "target_rtu": "RTU_1 (Port 5021)",
                "source": "ATTACKER_COMMAND_INJECTION",
                "function_code": 6,
                "is_unexpected_write": True,
                "response_time_ms": 5.0,
                "success": True,
            },
            # SCADA master incorrectly having flag set
            {
                "target_rtu": "RTU_1 (Port 5021)",
                "source": "SCADA_MASTER",
                "function_code": 3,
                "is_unexpected_write": True,
                "response_time_ms": 12.0,
                "success": True,
            },
        ]
        feats = extract_features(
            traffic_events=caller_flagged_events,
            state_estimation_result=_dummy_se_result(),
            target_rtu_id=1,
        )
        assert feats["nbd_unexpected_write_count"] == 0.0, (
            "Caller-supplied is_unexpected_write=True flags on non-RTU sources must be ignored."
        )

    def test_ordinary_caller_cannot_spoof_rtu_observed_write(self):
        """
        Ordinary callers invoking log_transaction(source='RTU_OBSERVED_WRITE', ...)
        MUST NOT be able to forge trusted RTU-observed write events.
        The logger must sanitize the source and force is_unexpected_write=False.
        """
        logger = ModbusTrafficLogger()
        logger.clear()

        # Attacker tries to spoof RTU_OBSERVED_WRITE directly via log_transaction
        ev_spoof = logger.log_transaction(
            source="RTU_OBSERVED_WRITE",
            target_rtu="RTU_1 (Port 5021)",
            function_code=6,
            response_time_ms=0.0,
            is_unexpected_write=True,
            details="attacker attempting to spoof RTU observer",
        )
        assert ev_spoof["is_unexpected_write"] is False, (
            "Ordinary log_transaction must NEVER produce is_unexpected_write=True."
        )
        assert ev_spoof["source"] == "UNTRUSTED_SPOOFED_RTU_WRITE", (
            "Attempted RTU_OBSERVED_WRITE via log_transaction must be sanitized."
        )
        assert ev_spoof.get("observer_verified") is False, (
            "Spoofed entry must have observer_verified=False."
        )

        # Confirm feature extraction ignores the spoofed transaction
        feats = extract_features(
            traffic_events=[ev_spoof],
            state_estimation_result=_dummy_se_result(),
            target_rtu_id=1,
        )
        assert feats["nbd_unexpected_write_count"] == 0.0, (
            "Spoofed log_transaction entries must yield 0.0 unexpected writes in feature extraction."
        )

    def test_dedicated_trusted_observer_path_requires_valid_token(self):
        """
        record_rtu_observed_write is a dedicated trusted observer path that strictly
        requires an active RTUObserverToken issued during RTU server initialization.
        """
        logger = ModbusTrafficLogger()
        logger.clear()

        # Attempt 1: Call without token -> PermissionError
        with pytest.raises(PermissionError, match="Observer authenticity check failed"):
            logger.record_rtu_observed_write(
                token=None,  # type: ignore
                target_rtu="RTU_1 (Port 5021)",
                function_code=6,
            )

        # Attempt 2: Call with counterfeit / forged token -> PermissionError
        from app.ot.traffic_logger import RTUObserverToken
        forged_token = RTUObserverToken(1, 5021, "counterfeit-secret-key")
        with pytest.raises(PermissionError, match="Observer authenticity check failed"):
            logger.record_rtu_observed_write(
                token=forged_token,
                target_rtu="RTU_1 (Port 5021)",
                function_code=6,
            )

        # Attempt 3: Genuine token issued to an RTU server instance -> Success
        genuine_token = logger.register_rtu_server(rtu_id=1, port=5021)
        ev_trusted = logger.record_rtu_observed_write(
            token=genuine_token,
            target_rtu="RTU_1 (Port 5021)",
            function_code=6,
            details="genuine RTU trace_pdu callback event",
        )
        assert ev_trusted["source"] == "RTU_OBSERVED_WRITE"
        assert ev_trusted["is_unexpected_write"] is True
        assert ev_trusted["observer_verified"] is True

        # Confirm feature extraction accepts genuine trusted event
        feats = extract_features(
            traffic_events=[ev_trusted],
            state_estimation_result=_dummy_se_result(),
            target_rtu_id=1,
        )
        assert feats["nbd_unexpected_write_count"] == 1.0

        # Attempt 4: Once unregistered/revoked, the token is rejected
        logger.unregister_rtu_server(genuine_token)
        with pytest.raises(PermissionError, match="Observer authenticity check failed"):
            logger.record_rtu_observed_write(
                token=genuine_token,
                target_rtu="RTU_1 (Port 5021)",
                function_code=6,
            )

    def test_source_label_manipulation_cannot_inflate_write_count(self):
        """
        Manipulating the source label to RTU_OBSERVED_WRITE on non-write operations
        or without is_unexpected_write=True must not increment the write feature.
        """
        manipulated_events = [
            # Tagged RTU_OBSERVED_WRITE but function code is Read Holding Registers (FC 3)
            {
                "target_rtu": "RTU_1 (Port 5021)",
                "source": RTU_OBSERVED_WRITE_SOURCE,
                "function_code": 3,
                "is_unexpected_write": True,
            },
            # Tagged RTU_OBSERVED_WRITE with FC 6, but is_unexpected_write is False
            {
                "target_rtu": "RTU_1 (Port 5021)",
                "source": RTU_OBSERVED_WRITE_SOURCE,
                "function_code": 6,
                "is_unexpected_write": False,
            },
            # Tagged RTU_OBSERVED_WRITE with non-standard FC
            {
                "target_rtu": "RTU_1 (Port 5021)",
                "source": RTU_OBSERVED_WRITE_SOURCE,
                "function_code": 99,
                "is_unexpected_write": True,
            },
        ]
        feats = extract_features(
            traffic_events=manipulated_events,
            state_estimation_result=_dummy_se_result(),
            target_rtu_id=1,
        )
        assert feats["nbd_unexpected_write_count"] == 0.0, (
            "Manipulated source labels must NOT increment nbd_unexpected_write_count "
            "unless they match valid Modbus write function codes and is_unexpected_write is True."
        )

    def test_rtu_observed_write_does_not_pollute_distinct_sources(self):
        """
        RTU_OBSERVED_WRITE is an internal observer log entry, NOT an external network
        client. It must not be counted as a separate communication source in nbd_distinct_sources_count.
        """
        events = [
            # Legitimate SCADA polling event
            {
                "target_rtu": "RTU_1 (Port 5021)",
                "source": "SCADA_MASTER",
                "function_code": 3,
                "response_time_ms": 11.5,
                "is_unexpected_write": False,
                "success": True,
            },
            # RTU-side observer entry for incoming write
            {
                "target_rtu": "RTU_1 (Port 5021)",
                "source": RTU_OBSERVED_WRITE_SOURCE,
                "function_code": 6,
                "response_time_ms": 0.0,
                "is_unexpected_write": True,
                "observer_verified": True,
                "success": True,
            },
        ]
        feats = extract_features(
            traffic_events=events,
            state_estimation_result=_dummy_se_result(),
            target_rtu_id=1,
        )
        assert feats["nbd_unexpected_write_count"] == 1.0
        # distinct_sources must remain 1.0 (from SCADA_MASTER), NOT inflated to 2.0
        assert feats["nbd_distinct_sources_count"] == 1.0, (
            f"Expected distinct_sources == 1.0, got {feats['nbd_distinct_sources_count']}. "
            "RTU_OBSERVED_WRITE must not be treated as a distinct network host."
        )

    def test_missing_or_false_observer_verified_rejected(self):
        """
        An event with source='RTU_OBSERVED_WRITE', FC in {5,6,15,16}, and is_unexpected_write=True
        MUST be rejected (cannot increment nbd_unexpected_write_count) if observer_verified
        is missing, None, or False.
        """
        # Case 1: observer_verified omitted entirely
        ev_missing = {
            "target_rtu": "RTU_1 (Port 5021)",
            "source": RTU_OBSERVED_WRITE_SOURCE,
            "function_code": 6,
            "is_unexpected_write": True,
            "response_time_ms": 0.0,
            "success": True,
        }
        feats_missing = extract_features([ev_missing], _dummy_se_result(), target_rtu_id=1)
        assert feats_missing["nbd_unexpected_write_count"] == 0.0, (
            "Event with missing observer_verified field must NOT increment nbd_unexpected_write_count."
        )

        # Case 2: observer_verified is None
        ev_none = {
            "target_rtu": "RTU_1 (Port 5021)",
            "source": RTU_OBSERVED_WRITE_SOURCE,
            "function_code": 6,
            "is_unexpected_write": True,
            "observer_verified": None,
            "response_time_ms": 0.0,
            "success": True,
        }
        feats_none = extract_features([ev_none], _dummy_se_result(), target_rtu_id=1)
        assert feats_none["nbd_unexpected_write_count"] == 0.0, (
            "Event with observer_verified=None must NOT increment nbd_unexpected_write_count."
        )

        # Case 3: observer_verified is False
        ev_false = {
            "target_rtu": "RTU_1 (Port 5021)",
            "source": RTU_OBSERVED_WRITE_SOURCE,
            "function_code": 6,
            "is_unexpected_write": True,
            "observer_verified": False,
            "response_time_ms": 0.0,
            "success": True,
        }
        feats_false = extract_features([ev_false], _dummy_se_result(), target_rtu_id=1)
        assert feats_false["nbd_unexpected_write_count"] == 0.0, (
            "Event with observer_verified=False must NOT increment nbd_unexpected_write_count."
        )

    def test_genuine_rtu_observed_write_contributes(self):
        """Genuinely observed Modbus write requests (FC 5, 6, 15, 16) must increment unexpected_writes."""
        events = [
            {
                "target_rtu": "RTU_1 (Port 5021)",
                "source": RTU_OBSERVED_WRITE_SOURCE,
                "function_code": 6,
                "is_unexpected_write": True,
                "observer_verified": True,
                "response_time_ms": 0.0,
                "success": True,
            },
            {
                "target_rtu": "RTU_1 (Port 5021)",
                "source": RTU_OBSERVED_WRITE_SOURCE,
                "function_code": 16,
                "is_unexpected_write": True,
                "observer_verified": True,
                "response_time_ms": 0.0,
                "success": True,
            },
        ]
        feats = extract_features(
            traffic_events=events,
            state_estimation_result=_dummy_se_result(),
            target_rtu_id=1,
        )
        assert feats["nbd_unexpected_write_count"] == 2.0

    def test_feature_schema_preserved_and_model_compatible(self):
        """The frozen FEATURE_SCHEMA must be fully populated and compatible with ClassifierService."""
        from app.ml.classifier_service import ClassifierService

        cs = ClassifierService()
        assert cs.load_model() is True, "ClassifierService must load model without schema rejection."

        events = [
            {
                "target_rtu": "RTU_1 (Port 5021)",
                "source": "SCADA_MASTER",
                "function_code": 3,
                "response_time_ms": 12.0,
                "is_unexpected_write": False,
                "success": True,
            },
            {
                "target_rtu": "RTU_1 (Port 5021)",
                "source": RTU_OBSERVED_WRITE_SOURCE,
                "function_code": 6,
                "response_time_ms": 0.0,
                "is_unexpected_write": True,
                "observer_verified": True,
                "success": True,
            },
        ]
        feats = extract_features(
            traffic_events=events,
            state_estimation_result=_dummy_se_result(),
            target_rtu_id=1,
        )
        for key in FEATURE_SCHEMA:
            assert key in feats, f"Missing schema key: {key}"
            assert isinstance(feats[key], (int, float)), f"Key {key} must be numeric"

        vec = features_to_vector(feats)
        assert len(vec) == len(FEATURE_SCHEMA)

        verdict = cs.predict(feats)
        assert "verdict" in verdict
        assert verdict["verdict"] in ("Normal", "Natural Fault", "Cyber Intrusion", "Sensor Malfunction")
