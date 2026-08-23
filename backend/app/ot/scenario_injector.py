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

    async def inject_command_write(
        self,
        rtu_id: int,
        register_address: int,
        value: int,
        host: str = "127.0.0.1",
    ) -> Dict[str, Any]:
        """
        Simulate an unauthorized cyber attack by sending an actual Modbus TCP
        Write Single Register command (FC 06) from an external attacker IP.
        This MUST be flagged as an unexpected write in the traffic logger.
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
                elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                traffic_logger.log_transaction(
                    source="ATTACKER_COMMAND_INJECTION",
                    target_rtu=target_name,
                    function_code=6,
                    response_time_ms=elapsed_ms,
                    is_unexpected_write=True,
                    details=f"Connection failed when attempting unauthorized write to reg {register_address}",
                    success=False,
                )
                return {"status": "error", "message": "Failed to connect to target RTU"}

            # Send unauthorized Modbus FC 06 (Write Single Register)
            wr = await client.write_register(address=register_address, value=int(value), device_id=1)
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0

            success = not wr.isError()
            traffic_logger.log_transaction(
                source="ATTACKER_COMMAND_INJECTION",
                target_rtu=target_name,
                function_code=6,
                response_time_ms=elapsed_ms,
                is_unexpected_write=True,
                details=f"UNAUTHORIZED WRITE: Register {register_address} = {value} (Hex: 0x{value:04X})",
                success=success,
            )

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
        if not self.silent_overrides and not self.replay_attacks and not self.tripped_lines and not self.short_circuit_loads:
            self.active_scenario_summary = "NORMAL_OPERATION"

    def clear_all_scenarios(self, net: Optional[pp.pandapowerNet] = None) -> None:
        """
        Clear all cyber overrides and restore all physical network elements.
        """
        self.silent_overrides.clear()
        self.replay_attacks.clear()

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
        return {
            "summary": self.active_scenario_summary,
            "silent_overrides": {
                rtu_id: item["overrides"] for rtu_id, item in self.silent_overrides.items()
            },
            "replay_attacks": list(self.replay_attacks.keys()),
            "tripped_lines": list(self.tripped_lines),
            "short_circuit_active": len(self.short_circuit_loads) > 0,
        }


# Global singleton instance
scenario_injector = ScenarioInjector()
