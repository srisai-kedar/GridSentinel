"""Scenario-library v2 registry used by experiments and the dataset scheduler."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict

from app.ot.scenario_injector import scenario_injector
from app.ot.scada_master import scada_master


@dataclass(frozen=True)
class ScenarioDefinition:
    name: str
    family: str
    label: str
    evidence: str


SCENARIO_REGISTRY = {
    "fdi": ScenarioDefinition("fdi", "cyber", "Cyber Intrusion", "telemetry_override"),
    "replay": ScenarioDefinition("replay", "cyber", "Cyber Intrusion", "repeated_telemetry"),
    "command_injection": ScenarioDefinition("command_injection", "cyber", "Cyber Intrusion", "observer_write"),
    "breaker_open": ScenarioDefinition("breaker_open", "cyber", "Cyber Intrusion", "observer_write_and_line_state"),
    "sustained_setpoint": ScenarioDefinition("sustained_setpoint", "cyber", "Cyber Intrusion", "observer_write_and_setpoint"),
    "natural_line_trip": ScenarioDefinition("natural_line_trip", "natural_fault", "Natural Fault", "physical_state"),
    "short_circuit": ScenarioDefinition("short_circuit", "natural_fault", "Natural Fault", "physical_state"),
    "drift": ScenarioDefinition("drift", "sensor_malfunction", "Sensor Malfunction", "telemetry_bias"),
    "load_step": ScenarioDefinition("load_step", "normal_operational", "Normal", "physical_state"),
    "authorized_control_write": ScenarioDefinition("authorized_control_write", "normal_operational", "Normal", "allow_listed_write"),
    "communication_stall": ScenarioDefinition("communication_stall", "normal_operational", "Normal", "failed_polls"),
}


def load_scenario_weights(regime: str) -> Dict[str, float]:
    path = Path(__file__).with_name("scenario_weights.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    if regime not in data:
        raise ValueError(f"No scenario weights configured for regime: {regime}")
    weights = {str(key): float(value) for key, value in data[regime].items()}
    if any(value < 0 for value in weights.values()) or sum(weights.values()) <= 0:
        raise ValueError(f"Invalid scenario weights for regime: {regime}")
    total = sum(weights.values())
    return {key: value / total for key, value in weights.items()}


def get_scenario(name: str) -> ScenarioDefinition:
    try:
        return SCENARIO_REGISTRY[name]
    except KeyError as exc:
        raise ValueError(f"Unknown scenario: {name}") from exc


def apply_fdi(**kwargs: Any) -> Dict[str, Any]:
    return scenario_injector.inject_fdi(**kwargs)


def apply_replay(**kwargs: Any) -> Dict[str, Any]:
    return scenario_injector.inject_replay(**kwargs)


async def apply_command_injection(**kwargs: Any) -> Dict[str, Any]:
    return await scenario_injector.inject_command_write(**kwargs)


async def apply_breaker_open(**kwargs: Any) -> Dict[str, Any]:
    return await scenario_injector.inject_breaker_open(**kwargs)


async def apply_sustained_setpoint(**kwargs: Any) -> Dict[str, Any]:
    return await scenario_injector.inject_sustained_setpoint_write(**kwargs)


def apply_natural_line_trip(**kwargs: Any) -> Dict[str, Any]:
    return scenario_injector.trigger_line_trip(**kwargs)


def apply_short_circuit(**kwargs: Any) -> Dict[str, Any]:
    return scenario_injector.trigger_short_circuit_stub(**kwargs)


def apply_drift(**kwargs: Any) -> Dict[str, Any]:
    return scenario_injector.inject_drift(**kwargs)


def apply_authorized_control_write(
    rtu_id: int, register_address: int, value: int, source: str = "AUTHORIZED_CONTROL"
) -> Dict[str, Any]:
    return scenario_injector.inject_authorized_control_write(rtu_id, register_address, value, source)


def apply_communication_stall(rtu_id: int, duration_ticks: int) -> Dict[str, Any]:
    scada_master.inject_communication_stall(rtu_id, duration_ticks)
    return {"type": "COMMUNICATION_STALL", "rtu_id": rtu_id, "duration_ticks": duration_ticks, "label": "Normal-Operational"}


def apply_load_step(magnitude: float, duration_ticks: int) -> Dict[str, Any]:
    from app.ot.simulation_loop import sim_loop

    sim_loop.apply_load_step(magnitude, duration_ticks)
    return {"type": "LOAD_STEP", "magnitude": magnitude, "duration_ticks": duration_ticks, "label": "Normal-Operational"}
