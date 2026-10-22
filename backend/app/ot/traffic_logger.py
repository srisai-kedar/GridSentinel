"""
traffic_logger.py
-----------------
Logs Modbus TCP observations in GridSentinel into a rolling in-memory buffer.

Two kinds of observers feed this log:

* ``scada_master`` - the master's own poll measurements (latency, success).
* ``rtu_tap``      - what each RTU server *actually received on the wire*
  (function code, address, TCP connects), recorded by the passive tap in
  ``rtu_server.py``.

ANTI-LEAKAGE CONTRACT
---------------------
``is_unexpected_write`` is NOT an input. It is computed here, from the observed
function code, by :mod:`app.ot.nbd_policy`. No caller (master, attacker script,
test, scenario injector) can declare its own traffic unexpected.

Every event is stamped with a simulation tick so NBD feature windows are defined
in ticks (``NBD_WINDOW_TICKS``) identically for dataset generation, live
inference, and the REST API.
"""

from __future__ import annotations

import collections
import datetime
import threading
from typing import Any, Dict, List, Optional

from app.ot import nbd_policy


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

    def _init_logger(self, maxlen: int = 1500):
        self._buffer: collections.deque[Dict[str, Any]] = collections.deque(maxlen=maxlen)
        self._counter: int = 0
        self._buf_lock = threading.Lock()
        # Simulation-clock bookkeeping (a clock, never a label).
        self._tick: int = 0
        self._in_tick: bool = False

    # ------------------------------------------------------------------
    # Simulation clock
    # ------------------------------------------------------------------
    def begin_tick(self) -> int:
        """Mark the start of a simulation tick; events logged until
        :meth:`end_tick` belong to this tick."""
        with self._buf_lock:
            self._tick += 1
            self._in_tick = True
            return self._tick

    def end_tick(self) -> None:
        """Mark the end of the current simulation tick."""
        with self._buf_lock:
            self._in_tick = False

    def _stamp_locked(self) -> int:
        # Inside a tick: that tick. Between ticks (e.g. an attacker write sent
        # before the next poll): the upcoming tick.
        return self._tick if self._in_tick else self._tick + 1

    @property
    def current_tick(self) -> int:
        with self._buf_lock:
            return self._tick

    def _append_locked(self, **fields: Any) -> Dict[str, Any]:
        self._counter += 1
        event = {
            "event_id": self._counter,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "tick": self._stamp_locked(),
            **fields,
        }
        self._buffer.append(event)
        return event

    def log_transaction(
        self,
        source: str,
        target_rtu: str,
        function_code: int,
        response_time_ms: float,
        details: Optional[str] = None,
        success: bool = True,
        observer: str = "scada_master",
        rtu_id: Optional[int] = None,
        address: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Record one Modbus transaction as seen by ``observer``.

        NOTE: there is intentionally no ``is_unexpected_write`` parameter. The
        flag is derived from ``function_code``/``address`` by the NBD policy.
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
            22: "MASK_WRITE_REGISTER",
            23: "READ_WRITE_MULTIPLE_REGISTERS",
        }
        fc = int(function_code)
        with self._buf_lock:
            return self._append_locked(
                source=source,
                target_rtu=target_rtu,
                function_code=fc,
                function_name=fc_names.get(fc, f"FC_{fc}"),
                response_time_ms=round(float(response_time_ms), 2),
                is_unexpected_write=nbd_policy.is_unexpected_write(fc, address),
                success=bool(success),
                details=details or "",
                observer=observer,
                rtu_id=rtu_id,
                address=address,
            )

    def log_tap_pdu(
        self,
        rtu_id: int,
        rtu_name: str,
        port: int,
        function_code: int,
        address: Optional[int] = None,
        details: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Record one request PDU observed by an RTU's passive tap."""
        return self.log_transaction(
            source="RTU_TAP",  # observation point, not a client identity
            target_rtu=f"{rtu_name} (Port {port})",
            function_code=function_code,
            response_time_ms=0.0,
            details=details,
            success=True,
            observer="rtu_tap",
            rtu_id=rtu_id,
            address=address,
        )

    def log_tap_connection(self, rtu_id: int, rtu_name: str, port: int) -> Dict[str, Any]:
        """Record one TCP connection accepted by an RTU server (observed)."""
        with self._buf_lock:
            return self._append_locked(
                source="RTU_TAP",
                target_rtu=f"{rtu_name} (Port {port})",
                function_code=0,
                function_name="TCP_CONNECT",
                response_time_ms=0.0,
                is_unexpected_write=False,
                success=True,
                details="TCP connection accepted",
                observer="rtu_tap_conn",
                rtu_id=rtu_id,
                address=None,
            )

    def get_recent_events(self, limit: int = 50, include_connections: bool = False) -> List[Dict[str, Any]]:
        """
        Retrieve the latest N events in reverse chronological order (newest first).
        TCP-connection observations are internal feature inputs and are hidden
        from this view unless ``include_connections`` is True.
        """
        with self._buf_lock:
            events = [
                e for e in self._buffer
                if include_connections or e.get("observer") != "rtu_tap_conn"
            ]
            events.reverse()
            return events[:limit]

    def get_window_events(self, window_ticks: int) -> List[Dict[str, Any]]:
        """
        Events belonging to the last ``window_ticks`` simulation ticks
        (newest first), including TCP-connection observations.

        This is the ONE accessor used by dataset generation, the live
        simulation loop and the REST API, so NBD features see identical
        windows everywhere (train/serve parity).

        Window anchoring: lo = (last begun tick) - window_ticks + 1.
        Inside a tick, hi is that tick. Between ticks, events already logged for
        the upcoming tick (e.g. an attacker write) are also included.
        """
        if window_ticks < 1:
            raise ValueError("window_ticks must be >= 1")
        with self._buf_lock:
            lo = self._tick - window_ticks + 1
            hi = self._tick if self._in_tick else self._tick + 1
            events = [e for e in self._buffer if lo <= e.get("tick", 0) <= hi]
            events.reverse()
            return events

    def clear(self) -> None:
        """Clear all logged events."""
        with self._buf_lock:
            self._buffer.clear()
            self._counter = 0
            self._tick = 0
            self._in_tick = False

    def get_total_count(self) -> int:
        """Return the lifetime count of logged transactions."""
        with self._buf_lock:
            return self._counter


# Global singleton instance
traffic_logger = ModbusTrafficLogger()
