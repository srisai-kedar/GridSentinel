"""Out-of-band capture of already-computed classifier features for forensic replay."""

from __future__ import annotations

from collections import defaultdict, deque
from copy import deepcopy
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Deque, Dict, List, Mapping, Optional

from app.ml.feature_engineering import FEATURE_SCHEMA


REPLAY_RADIUS = 5
REPLAY_BUFFER_LENGTH = 31


class ReplayCaptureStore:
    """Keep a small copy of live feature vectors outside the detection path.

    The store receives feature dictionaries after the classifier has already
    extracted them. It never computes or changes a feature and is not used by
    inference or the WebSocket broadcaster.
    """

    def __init__(self) -> None:
        self._history: Dict[int, Deque[Dict[str, Any]]] = defaultdict(
            lambda: deque(maxlen=REPLAY_BUFFER_LENGTH)
        )
        self._lock = Lock()

    def clear(self) -> None:
        with self._lock:
            self._history.clear()

    def record_tick(
        self,
        *,
        tick: int,
        sim_time: Optional[str],
        features_by_rtu: Mapping[int, Mapping[str, float]],
        verdicts_by_rtu: Mapping[int, Mapping[str, Any]],
        telemetry_by_rtu: Optional[Mapping[int, Mapping[str, Any]]] = None,
        timestamp: Optional[str] = None,
    ) -> None:
        """Copy one completed classifier tick into the bounded replay buffers."""
        captured_at = timestamp or datetime.now(timezone.utc).isoformat()
        with self._lock:
            for raw_rtu_id, features in features_by_rtu.items():
                rtu_id = int(raw_rtu_id)
                # FEATURE_SCHEMA is the exact vector that was sent to the
                # classifier. Keep only those already-computed scalar values.
                copied_features = {
                    name: float(features[name])
                    for name in FEATURE_SCHEMA
                    if name in features
                }
                verdict = verdicts_by_rtu.get(rtu_id, {})
                telemetry = (telemetry_by_rtu or {}).get(rtu_id, {})
                self._history[rtu_id].append(
                    {
                        "tick": int(tick),
                        "sim_time": sim_time,
                        "timestamp": captured_at,
                        "features": copied_features,
                        "telemetry": {
                            key: float(telemetry[key])
                            for key in ("voltage_pu", "p_mw", "q_mvar")
                            if key in telemetry
                        },
                        "verdict": verdict.get("verdict"),
                        "subtype": verdict.get("subtype"),
                        "confidence": verdict.get("confidence"),
                    }
                )

    def get_window(self, rtu_id: Optional[int], trigger_tick: Optional[int]) -> List[Dict[str, Any]]:
        """Return the available ordered +/- radius window around a trigger tick."""
        if rtu_id is None or trigger_tick is None:
            return []

        with self._lock:
            history = list(self._history.get(int(rtu_id), ()))

        window: List[Dict[str, Any]] = []
        lower = int(trigger_tick) - REPLAY_RADIUS
        upper = int(trigger_tick) + REPLAY_RADIUS
        for sample in history:
            sample_tick = int(sample["tick"])
            if lower <= sample_tick <= upper:
                features = sample["features"]
                window.append(
                    {
                        "tick": sample_tick,
                        "tick_offset": sample_tick - int(trigger_tick),
                        "sim_time": sample.get("sim_time"),
                        "timestamp": sample.get("timestamp"),
                        "voltage_pu": features.get("pcd_voltage_pu_reported"),
                        "p_mw": features.get("pcd_p_mw_reported"),
                        "q_mvar": sample.get("telemetry", {}).get("q_mvar"),
                        "nbd": {
                            key: value
                            for key, value in features.items()
                            if key.startswith("nbd_")
                        },
                        "pcd": {
                            key: value
                            for key, value in features.items()
                            if key.startswith("pcd_")
                        },
                        "verdict": sample.get("verdict"),
                        "subtype": sample.get("subtype"),
                        "confidence": sample.get("confidence"),
                    }
                )

        window.sort(key=lambda point: point["tick"])
        return deepcopy(window)


replay_capture_store = ReplayCaptureStore()
