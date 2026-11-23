"""
scenario_injector.py
--------------------
Cyber-attack and physical-fault injection engine for GridSentinel.

Maintains a clear distinction:
1. Cyber Attacks:
   - Silent Data Injection: Overrides served telemetry at an RTU directly (simulating
     firmware malware or compromised sensor payload). Pandapower's true state is untouched,
     and no anomalous network writes occur.
   - Command Injection: An external attacker sends an unauthorized Modbus TCP Write command
     (FC 06/16) to an RTU. This is logged as an anomalous unexpected write in the traffic logger.
   - Replay Attack: Re-serves frozen or historical telemetry packets.
2. Physical Faults:
   - Line Trip: Sets line `in_service = False` in pandapower, altering real power flows.
   - Short Circuit (Stub): Temporarily connects a heavy fault load to create severe voltage sag.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional, Tuple
import pandapower as pp
from pymodbus.client import AsyncModbusTcpClient

from app.ot.rtu_server import RTU_CONFIGS, rtu_pool
from app.ot.traffic_logger import traffic_logger

logger = logging.getLogger("GridSentinel.ScenarioInjector")


class ScenarioInjector:
    """
    Manages active cyber and physical scenarios.
    """

    def __init__(self):
        # Silent data injection overrides: {rtu_id: {"overrides": dict, "remaining_ticks": int}}
        self.silent_overrides: Dict[int, Dict[str, Any]] = {}

        # Replay attack state: {rtu_id: {"buffer": list, "remaining_ticks": int}}
        self.replay_attacks: Dict[int, Dict[str, Any]] = {}

        # Sensor drift / decalibration state: {rtu_id: {"drift_percent": float, "remaining_ticks": int}}
        self.sensor_drifts: Dict[int, Dict[str, Any]] = {}
        self.sustained_setpoints: Dict[int, Dict[str, Any]] = {}

        # Physical fault state
        self.tripped_lines: List[int] = []
        self.short_circuit_loads: List[int] = []  # indices of created temporary loads in pandapower
        self.short_circuit_remaining_ticks: int = 0

        # Description of currently active scenario
        self.active_scenario_summary: str = "NORMAL_OPERATION"

    # -----------------------------------------------------------------------
    # Cyber Attacks
    # -----------------------------------------------------------------------
    def inject_silent_data_injection(
        self,
        rtu_id: int,
        voltage_pu: Optional[float] = None,
        p_mw: Optional[float] = None,
        q_mvar: Optional[float] = None,
        duration_ticks: int = 20,
    ) -> Dict[str, Any]:
        """
        Silently override the telemetry served by RTU `rtu_id`.
        The real pandapower physical state remains untouched, and no anomalous
        network write packets are sent (simulates compromised sensor/firmware).
        """
        overrides = {}
        if voltage_pu is not None:
            overrides["voltage_pu"] = float(voltage_pu)
        if p_mw is not None:
            overrides["p_mw"] = float(p_mw)
        if q_mvar is not None:
            overrides["q_mvar"] = float(q_mvar)

        self.silent_overrides[rtu_id] = {
            "overrides": overrides,
            "remaining_ticks": duration_ticks,
        }
        self.active_scenario_summary = (
            f"ATTACK: Silent Data Injection on RTU-{rtu_id} ({overrides}) for {duration_ticks} ticks"
        )
        logger.info(self.active_scenario_summary)
        return {
            "status": "injected",
            "type": "SILENT_DATA_INJECTION",
            "rtu_id": rtu_id,
            "overrides": overrides,
            "duration_ticks": duration_ticks,
        }

    def inject_fdi(
        self,
        rtu_id: int,
        target: str,
        sigma_multiple: float,
        duration_ticks: int,
        baseline: Optional[Dict[str, float]] = None,
    ) -> Dict[str, Any]:
        """Apply a parameterized FDI override using an explicit sigma magnitude."""
        if sigma_multiple not in {1, 2, 3, 5, 10, 25}:
            raise ValueError("sigma_multiple must be one of 1, 2, 3, 5, 10, 25")
        base = baseline or {"voltage_pu": 1.0, "p_mw": 0.2, "q_mvar": 0.1}
        if target == "V":
            overrides = {"voltage_pu": float(base["voltage_pu"] + sigma_multiple * 0.01)}
        elif target == "P":
            overrides = {"p_mw": float(base["p_mw"] + sigma_multiple * 0.05)}
        elif target == "Q":
            overrides = {"q_mvar": float(base["q_mvar"] + sigma_multiple * 0.03)}
        elif target == "mixed":
            overrides = {
                "voltage_pu": float(base["voltage_pu"] + sigma_multiple * 0.01),
                "p_mw": float(base["p_mw"] + sigma_multiple * 0.05),
                "q_mvar": float(base["q_mvar"] + sigma_multiple * 0.03),
            }
        else:
            raise ValueError("target must be V, P, Q, or mixed")
        result = self.inject_silent_data_injection(rtu_id=rtu_id, duration_ticks=duration_ticks, **overrides)
        result["scenario_params"] = {"target": target, "sigma_multiple": sigma_multiple}
        return result

    async def inject_command_write(
        self,
        rtu_id: int,
        register_address: int,
        value: int,
        host: str = "127.0.0.1",
    ) -> Dict[str, Any]:
        """
        Simulate an unauthorized cyber attack by sending an actual Modbus TCP
        Write Single Register command (FC 06) from an external attacker client.

        The RTU server's trace_pdu callback (rtu_server._make_write_observer)
        is the SOLE authoritative observer of this event.  When the write PDU
        arrives at the RTU, trace_pdu logs it to traffic_logger with
        ``source="RTU_OBSERVED_WRITE", is_unexpected_write=True``.

        This method intentionally does NOT call traffic_logger.log_transaction().
        Doing so would inject a simulation-only source label
        ("ATTACKER_COMMAND_INJECTION") into the traffic buffer.  That label can
        never appear during real deployment and would cause a
        training-vs-inference distribution mismatch in nbd_distinct_sources_count
        and any future source-derived features.
        """
        # Find target port
        target_cfg = next((cfg for cfg in RTU_CONFIGS if cfg["rtu_id"] == rtu_id), None)
        if not target_cfg:
            raise ValueError(f"RTU ID {rtu_id} not found in configuration")

        port = target_cfg["port"]
        target_name = f"{target_cfg['name']} (Port {port})"

        client = AsyncModbusTcpClient(host, port=port, timeout=2.0)
        start_time = time.perf_counter()

        try:
            connected = await client.connect()
            if not connected:
                # RTU was unreachable: the write never arrived, so the RTU
                # observer never fired.  Do NOT log to traffic_logger here.
                return {"status": "error", "message": "Failed to connect to target RTU"}

            # Send unauthorized Modbus FC 06 (Write Single Register)
            wr = await client.write_register(address=register_address, value=int(value), device_id=1)
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0

            success = not wr.isError()
            # Do NOT call traffic_logger.log_transaction() here.
            # The RTU server's trace_pdu callback already logged this write
            # with source="RTU_OBSERVED_WRITE", is_unexpected_write=True.
            # Adding a second entry with source="ATTACKER_COMMAND_INJECTION"
            # would contaminate nbd_distinct_sources_count with a label that
            # has no real-deployment equivalent.

            self.active_scenario_summary = (
                f"ATTACK: Unauthorized Modbus Command Write on RTU-{rtu_id} Reg {register_address}={value}"
            )

            return {
                "status": "success" if success else "error",
                "type": "COMMAND_INJECTION",
                "rtu_id": rtu_id,
                "register": register_address,
                "value": value,
                "flagged_in_traffic_log": True,
            }
        finally:
            client.close()

    async def inject_breaker_open(
        self,
        net: pp.pandapowerNet,
        rtu_id: int,
        line_index: int,
        host: str = "127.0.0.1",
    ) -> Dict[str, Any]:
        """Send a real write and take a line out of service."""
        write_result = await self.inject_command_write(rtu_id, register_address=4, value=1, host=host)
        physical_result = self.trigger_line_trip(net, line_index)
        return {"type": "BREAKER_OPEN", "write": write_result, "physical": physical_result}

    async def inject_sustained_setpoint_write(
        self,
        rtu_id: int,
        register_address: int,
        value: int,
        duration_ticks: int,
        host: str = "127.0.0.1",
    ) -> Dict[str, Any]:
        """Write once and hold the altered setpoint for the configured duration."""
        write_result = await self.inject_command_write(rtu_id, register_address, value, host)
        self.sustained_setpoints[rtu_id] = {
            "register_address": register_address,
            "value": int(value),
            "remaining_ticks": int(duration_ticks),
        }
        return {"type": "SUSTAINED_SETPOINT_WRITE", "write": write_result, "duration_ticks": duration_ticks}

    def inject_authorized_control_write(
        self,
        rtu_id: int,
        register_address: int,
        value: int,
        source: str = "AUTHORIZED_CONTROL",
    ) -> Dict[str, Any]:
        """Record a benign allow-listed control write without attack labeling."""
        target = next((cfg for cfg in RTU_CONFIGS if cfg["rtu_id"] == rtu_id), None)
        if target is None:
            raise ValueError(f"RTU ID {rtu_id} not found")
        event = traffic_logger.record_authorized_write(
            source=source,
            target_rtu=f"{target['name']} (Port {target['port']})",
            details=f"Authorized register {register_address}={value}",
        )
        return {"type": "AUTHORIZED_CONTROL_WRITE", "event": event, "label": "Normal-Operational"}

    def inject_drift(
        self,
        rtu_id: int,
        mode: str,
        target: str,
        duration_ticks: int,
        magnitude: float,
    ) -> Dict[str, Any]:
        """Configure step/ramp/gain/stuck/noise drift for V or P/Q telemetry."""
        if mode not in {"step", "ramp", "gain_error", "stuck_at", "noise_increase"}:
            raise ValueError("Unsupported drift mode")
        if target not in {"V", "P", "Q", "mixed"}:
            raise ValueError("Unsupported drift target")
        self.sensor_drifts[rtu_id] = {
            "mode": mode,
            "target": target,
            "magnitude": float(magnitude),
            "duration_ticks": int(duration_ticks),
            "remaining_ticks": int(duration_ticks),
            "elapsed_ticks": 0,
        }
        self.active_scenario_summary = f"FAULT: {mode} drift on RTU-{rtu_id} target={target}"
        return {"type": "SENSOR_DRIFT", "rtu_id": rtu_id, "mode": mode, "target": target, "duration_ticks": duration_ticks}

    def inject_replay(
        self,
        rtu_id: int,
        duration_ticks: int = 15,
    ) -> Dict[str, Any]:
        """
        Freeze and re-serve the current RTU telemetry snapshot for `duration_ticks`.
        """
        rtu = rtu_pool.get_rtu(rtu_id)
        frozen_vals = rtu.get_current_values() if rtu else {"voltage_pu": 1.0, "p_mw": 0.2, "q_mvar": 0.1}

        self.replay_attacks[rtu_id] = {
            "frozen_values": frozen_vals,
            "remaining_ticks": duration_ticks,
        }
        self.active_scenario_summary = (
            f"ATTACK: Replay / Frozen Telemetry on RTU-{rtu_id} for {duration_ticks} ticks"
        )
        logger.info(self.active_scenario_summary)
        return {
            "status": "injected",
            "type": "REPLAY_ATTACK",
            "rtu_id": rtu_id,
            "frozen_values": frozen_vals,
            "duration_ticks": duration_ticks,
        }

    # -----------------------------------------------------------------------
    # Physical Faults
    # -----------------------------------------------------------------------
    def trigger_line_trip(
        self,
        net: pp.pandapowerNet,
        line_index: int,
    ) -> Dict[str, Any]:
        """
        Trigger a physical line outage in pandapower.
        Sets `net.line.at[line_index, 'in_service'] = False`.
        """
        if line_index not in net.line.index:
            raise IndexError(f"Line index {line_index} not found in feeder network")

        net.line.at[line_index, "in_service"] = False
        if line_index not in self.tripped_lines:
            self.tripped_lines.append(line_index)

        line_name = str(net.line.at[line_index, "name"])
        self.active_scenario_summary = f"FAULT: Line Trip on Line {line_index} ({line_name})"
        logger.warning(self.active_scenario_summary)

        return {
            "status": "triggered",
            "type": "LINE_TRIP",
            "line_index": line_index,
            "line_name": line_name,
            "in_service": False,
        }

    def trigger_short_circuit_stub(
        self,
        net: pp.pandapowerNet,
        bus_index: int,
        fault_load_mw: float = 6.0,
        fault_load_mvar: float = 4.0,
        duration_ticks: int = 4,
    ) -> Dict[str, Any]:
        """
        Demo stand-in for a short-circuit fault event.
        Attaches a temporary large load at `bus_index` for a few ticks
        to produce realistic voltage depression and current surge across lines.
        """
        if bus_index not in net.bus.index:
            raise IndexError(f"Bus index {bus_index} not found in feeder network")

        # Create temporary fault load
        load_idx = pp.create_load(
            net,
            bus=bus_index,
            p_mw=fault_load_mw,
            q_mvar=fault_load_mvar,
            name=f"TEMP_FAULT_STUB_BUS{bus_index}",
        )
        self.short_circuit_loads.append(load_idx)
        self.short_circuit_remaining_ticks = duration_ticks

        bus_name = str(net.bus.at[bus_index, "name"])
        self.active_scenario_summary = (
            f"FAULT: Short Circuit Stub at Bus {bus_index} ({bus_name}) for {duration_ticks} ticks"
        )
        logger.warning(self.active_scenario_summary)

        return {
            "status": "triggered",
            "type": "SHORT_CIRCUIT_STUB",
            "bus_index": bus_index,
            "bus_name": bus_name,
            "fault_load_mw": fault_load_mw,
            "duration_ticks": duration_ticks,
        }

    def inject_sensor_drift(
        self,
        rtu_id: int,
        drift_percent: float = 0.08,
        duration_ticks: int = 25,
    ) -> Dict[str, Any]:
        """
        Simulate sensor drift / decalibration on RTU `rtu_id`.
        Applies a moderate bias to sensor measurements. OT Modbus network traffic remains clean!
        """
        self.sensor_drifts[rtu_id] = {
            "drift_percent": float(drift_percent),
            "remaining_ticks": int(duration_ticks),
        }
        self.active_scenario_summary = (
            f"FAULT: Sensor Drift / Malfunction on RTU-{rtu_id} ({drift_percent*100:+.1f}%) for {duration_ticks} ticks"
        )
        logger.info(self.active_scenario_summary)
        return {
            "status": "injected",
            "type": "SENSOR_DRIFT",
            "rtu_id": rtu_id,
            "drift_percent": drift_percent,
            "duration_ticks": duration_ticks,
        }

    # -----------------------------------------------------------------------
    # Tick Update & Scenario Maintenance
    # -----------------------------------------------------------------------
    def on_simulation_tick(self, net: pp.pandapowerNet) -> None:
        """
        Called on every simulation tick to decrement attack/fault durations
        and clean up expired temporary faults.
        """
        # Decrement silent overrides
        expired_silent = []
        for rtu_id, item in self.silent_overrides.items():
            item["remaining_ticks"] -= 1
            if item["remaining_ticks"] <= 0:
                expired_silent.append(rtu_id)
        for rtu_id in expired_silent:
            del self.silent_overrides[rtu_id]

        # Decrement replay attacks
        expired_replay = []
        for rtu_id, item in self.replay_attacks.items():
            item["remaining_ticks"] -= 1
            if item["remaining_ticks"] <= 0:
                expired_replay.append(rtu_id)
        for rtu_id in expired_replay:
            del self.replay_attacks[rtu_id]

        # Decrement sensor drifts
        expired_drift = []
        for rtu_id, item in self.sensor_drifts.items():
            item["remaining_ticks"] -= 1
            if item["remaining_ticks"] <= 0:
                expired_drift.append(rtu_id)
        for rtu_id in expired_drift:
            del self.sensor_drifts[rtu_id]

        expired_setpoints = []
        for rtu_id, item in self.sustained_setpoints.items():
            item["remaining_ticks"] -= 1
            if item["remaining_ticks"] <= 0:
                expired_setpoints.append(rtu_id)
        for rtu_id in expired_setpoints:
            del self.sustained_setpoints[rtu_id]

        # Decrement short circuit fault
        if self.short_circuit_remaining_ticks > 0:
            self.short_circuit_remaining_ticks -= 1
            if self.short_circuit_remaining_ticks <= 0:
                # Remove temporary fault loads
                for load_idx in self.short_circuit_loads:
                    if load_idx in net.load.index:
                        net.load.drop(load_idx, inplace=True)
                self.short_circuit_loads.clear()

        # Update active scenario summary
        if not self.silent_overrides and not self.replay_attacks and not self.sensor_drifts and not self.sustained_setpoints and not self.tripped_lines and not self.short_circuit_loads:
            self.active_scenario_summary = "NORMAL_OPERATION"

    def clear_all_scenarios(self, net: Optional[pp.pandapowerNet] = None) -> None:
        """
        Clear all cyber overrides and restore all physical network elements.
        """
        self.silent_overrides.clear()
        self.replay_attacks.clear()
        self.sensor_drifts.clear()
        self.sustained_setpoints.clear()

        if net is not None:
            # Restore all lines
            for l_idx in net.line.index:
                net.line.at[l_idx, "in_service"] = True
            # Remove any fault loads
            for load_idx in list(self.short_circuit_loads):
                if load_idx in net.load.index:
                    net.load.drop(load_idx, inplace=True)

        self.tripped_lines.clear()
        self.short_circuit_loads.clear()
        self.short_circuit_remaining_ticks = 0
        self.active_scenario_summary = "NORMAL_OPERATION"
        logger.info("Cleared all active scenarios and restored normal operation.")

    def get_active_scenarios(self) -> Dict[str, Any]:
        """Return structured summary of active attacks and faults."""
        drift_summary = {}
        for rtu_id, item in self.sensor_drifts.items():
            if "drift_percent" in item:
                drift_summary[rtu_id] = item["drift_percent"]
            elif "magnitude" in item:
                drift_summary[rtu_id] = item["magnitude"]
            else:
                raise ValueError(f"Sensor-drift state for RTU {rtu_id} has no magnitude field")
        return {
            "summary": self.active_scenario_summary,
            "silent_overrides": {
                rtu_id: item["overrides"] for rtu_id, item in self.silent_overrides.items()
            },
            "replay_attacks": list(self.replay_attacks.keys()),
            "sensor_drifts": drift_summary,
            "sustained_setpoints": {
                rtu_id: {key: value for key, value in item.items() if key != "remaining_ticks"}
                for rtu_id, item in self.sustained_setpoints.items()
            },
            "tripped_lines": list(self.tripped_lines),
            "short_circuit_active": len(self.short_circuit_loads) > 0,
        }


# Global singleton instance
scenario_injector = ScenarioInjector()
