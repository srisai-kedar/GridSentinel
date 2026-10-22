"""
traffic_logger.py
-----------------
Logs every Modbus TCP transaction in GridSentinel.
Captures communication metadata (source, target, function code, response time,
and expected/unexpected flags) into a rolling in-memory buffer (last 500 events).

This provides clean structured logs for Phase 3's network-behavioral anomaly classifier.
"""

from __future__ import annotations

import collections
import datetime
import threading
import uuid
from typing import Any, Dict, List, Optional


class RTUObserverToken:
    """
    Opaque capability token issued exclusively to SimulatedRTU server instances.
    Ordinary callers cannot instantiate or forge a valid token.
    """
    def __init__(self, rtu_id: int, port: int, secret: str):
        self._rtu_id = rtu_id
        self._port = port
        self._secret = secret

    @property
    def rtu_id(self) -> int:
        return self._rtu_id

    @property
    def port(self) -> int:
        return self._port


class ModbusTrafficLogger:
    """
    Thread-safe rolling log buffer for Modbus TCP transactions.
    """
    _instance: Optional[ModbusTrafficLogger] = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(ModbusTrafficLogger, cls).__new__(cls)
                    cls._instance._init_logger()
        return cls._instance

    def _init_logger(self, maxlen: int = 500):
        self._buffer: collections.deque[Dict[str, Any]] = collections.deque(maxlen=maxlen)
        self._counter: int = 0
        self._buf_lock = threading.Lock()
        self._trusted_tokens: set[str] = set()

    def register_rtu_server(self, rtu_id: int, port: int) -> RTUObserverToken:
        """
        Issue a unique, unforgeable capability token for a SimulatedRTU server instance.
        Only holders of this token can log through the dedicated trusted observer path.
        """
        secret = uuid.uuid4().hex
        token = RTUObserverToken(rtu_id, port, secret)
        with self._buf_lock:
            self._trusted_tokens.add(secret)
        return token

    def unregister_rtu_server(self, token: Optional[RTUObserverToken]) -> None:
        """Revoke an RTU server observer token."""
        if isinstance(token, RTUObserverToken):
            with self._buf_lock:
                self._trusted_tokens.discard(token._secret)

    def record_rtu_observed_write(
        self,
        token: RTUObserverToken,
        target_rtu: str,
        function_code: int,
        details: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Dedicated trusted observer path for RTU-observed Modbus writes.
        Can ONLY be invoked with a valid active RTUObserverToken issued to a SimulatedRTU.
        Attempts to call this without a valid token will be rejected with PermissionError.
        """
        if (
            not isinstance(token, RTUObserverToken)
            or getattr(token, "_secret", None) not in self._trusted_tokens
        ):
            raise PermissionError(
                "Observer authenticity check failed: invalid or unauthorized RTUObserverToken. "
                "Only genuine RTU server trace_pdu callbacks can record observed writes."
            )

        fc = int(function_code)
        if fc not in (5, 6, 15, 16):
            raise ValueError(
                f"Function code {fc} is not a valid Modbus write function code"
            )

        fc_names = {
            5: "WRITE_SINGLE_COIL",
            6: "WRITE_SINGLE_REGISTER",
            15: "WRITE_MULTIPLE_COILS",
            16: "WRITE_MULTIPLE_REGISTERS",
        }
        function_name = fc_names.get(fc, f"FC_{fc}")

        with self._buf_lock:
            self._counter += 1
            event = {
                "event_id": self._counter,
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "source": "RTU_OBSERVED_WRITE",
                "target_rtu": target_rtu,
                "function_code": fc,
                "function_name": function_name,
                "response_time_ms": 0.0,
                "is_unexpected_write": True,
                "observer_verified": True,
                "success": True,
                "details": details or "",
            }
            self._buffer.append(event)
            return event

    def log_transaction(
        self,
        source: str,
        target_rtu: str,
        function_code: int,
        response_time_ms: float,
        is_unexpected_write: bool = False,
        details: Optional[str] = None,
        success: bool = True,
    ) -> Dict[str, Any]:
        """
        Record a standard Modbus transaction (e.g. from SCADA_MASTER polling).

        Ordinary callers using this method CANNOT create trusted RTU-observed write events.
        Any attempt to spoof source='RTU_OBSERVED_WRITE' or pass is_unexpected_write=True
        is sanitized and recorded with is_unexpected_write=False, observer_verified=False.
        """
        fc_names = {
            1: "READ_COILS",
            2: "READ_DISCRETE_INPUTS",
            3: "READ_HOLDING_REGISTERS",
            4: "READ_INPUT_REGISTERS",
            5: "WRITE_SINGLE_COIL",
            6: "WRITE_SINGLE_REGISTER",
            15: "WRITE_MULTIPLE_COILS",
            16: "WRITE_MULTIPLE_REGISTERS",
        }
        function_name = fc_names.get(function_code, f"FC_{function_code}")

        # Ordinary callers cannot create trusted RTU-observed write events.
        is_spoofed_attempt = (
            source == "RTU_OBSERVED_WRITE" or bool(is_unexpected_write)
        )
        safe_source = (
            "UNTRUSTED_SPOOFED_RTU_WRITE" if source == "RTU_OBSERVED_WRITE" else source
        )

        with self._buf_lock:
            self._counter += 1
            event = {
                "event_id": self._counter,
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "source": safe_source,
                "target_rtu": target_rtu,
                "function_code": function_code,
                "function_name": function_name,
                "response_time_ms": round(response_time_ms, 2),
                "is_unexpected_write": False,  # General callers CANNOT set True
                "observer_verified": False,
                "success": bool(success),
                "details": (
                    f"SPOOF_ATTEMPT_REJECTED: {details}" if is_spoofed_attempt else (details or "")
                ),
            }
            self._buffer.append(event)
            return event

    def get_recent_events(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Retrieve the latest N events in reverse chronological order (newest first).
        """
        with self._buf_lock:
            events = list(self._buffer)
            events.reverse()
            return events[:limit]

    def clear(self) -> None:
        """Clear all logged events."""
        with self._buf_lock:
            self._buffer.clear()
            self._counter = 0

    def get_total_count(self) -> int:
        """Return the lifetime count of logged transactions."""
        with self._buf_lock:
            return self._counter


# Global singleton instance
traffic_logger = ModbusTrafficLogger()
