"""Single source of truth for GridSentinel RTU measurement ownership."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class MeasurementBinding:
    element_type: str
    element: int
    measurement_types: tuple[str, ...]
    source: str


RTU_IDS = (1, 2, 3, 4, 5)

# These are the measurements written by the five attackable RTU servers.
RTU_MEASUREMENT_MAP: dict[int, tuple[MeasurementBinding, ...]] = {
    1: (
        MeasurementBinding("bus", 1, ("v",), "rtu_reported"),
        MeasurementBinding("trafo", 0, ("p", "q"), "rtu_reported"),
    ),
    2: (
        MeasurementBinding("bus", 2, ("v",), "rtu_reported"),
        MeasurementBinding("line", 0, ("p", "q"), "rtu_reported"),
    ),
    3: (
        MeasurementBinding("bus", 3, ("v",), "rtu_reported"),
        MeasurementBinding("line", 1, ("p", "q"), "rtu_reported"),
    ),
    4: (
        MeasurementBinding("bus", 4, ("v",), "rtu_reported"),
        MeasurementBinding("line", 2, ("p", "q"), "rtu_reported"),
    ),
    5: (
        MeasurementBinding("bus", 5, ("v",), "rtu_reported"),
        MeasurementBinding("line", 3, ("p", "q"), "rtu_reported"),
    ),
}

# These measurements are generated from the solved network and are not exposed
# through an attackable RTU telemetry path.
TRUSTED_PSEUDO_SENSORS = (
    MeasurementBinding("bus", 6, ("v",), "trusted_pseudo_sensor"),
    MeasurementBinding("line", 4, ("p", "q"), "trusted_pseudo_sensor"),
)


def bindings_for_rtu(rtu_id: int) -> tuple[MeasurementBinding, ...]:
    return RTU_MEASUREMENT_MAP.get(int(rtu_id), ())


def bus_index_for_rtu(rtu_id: int) -> Optional[int]:
    for binding in bindings_for_rtu(rtu_id):
        if binding.element_type == "bus":
            return binding.element
    return None


def measurement_matches_rtu(element_type: str, element: int, rtu_id: int) -> bool:
    normalized_type = str(element_type).lower()
    return any(
        binding.element_type == normalized_type and binding.element == int(element)
        for binding in bindings_for_rtu(rtu_id)
    )


def rtu_for_measurement(element_type: str, element: int) -> Optional[int]:
    normalized_type = str(element_type).lower()
    for rtu_id, bindings in RTU_MEASUREMENT_MAP.items():
        if any(binding.element_type == normalized_type and binding.element == int(element) for binding in bindings):
            return rtu_id
    return None


def is_trusted_pseudo_sensor(element_type: str, element: int) -> bool:
    normalized_type = str(element_type).lower()
    return any(binding.element_type == normalized_type and binding.element == int(element) for binding in TRUSTED_PSEUDO_SENSORS)
