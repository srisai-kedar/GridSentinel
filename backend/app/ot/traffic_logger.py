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
from typing import Any, Dict, List, Optional


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

    def log_transaction(
        self,
        source: str,
        target_rtu: str,
        function_code: int,
        response_time_ms: float,
        is_unexpected_write: bool,
        details: Optional[str] = None,
        success: bool = True,
    ) -> Dict[str, Any]:
        """
        Record a single Modbus transaction event.

        Parameters
        ----------
        source : str
            Identifier of source, e.g. "SCADA_MASTER", "127.0.0.1", or "ATTACKER"
        target_rtu : str
            Identifier of target RTU, e.g. "RTU_1 (Port 5021)"
        function_code : int
            Modbus function code (3=Read HR, 6=Write Single, 16=Write Multiple, etc.)
        response_time_ms : float
            Roundtrip execution time in milliseconds
        is_unexpected_write : bool
            Flag set to True if this is an unauthorized/unexpected command write
        details : str, optional
            Human-readable description or register payload
        success : bool
            Whether the Modbus transaction succeeded
        """
        # Map function codes to friendly names
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

        with self._buf_lock:
            self._counter += 1
            event = {
                "event_id": self._counter,
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "source": source,
                "target_rtu": target_rtu,
                "function_code": function_code,
                "function_name": function_name,
                "response_time_ms": round(response_time_ms, 2),
                "is_unexpected_write": bool(is_unexpected_write),
                "success": bool(success),
                "details": details or "",
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
