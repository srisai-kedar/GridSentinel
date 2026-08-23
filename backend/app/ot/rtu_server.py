"""
rtu_server.py
-------------
Simulates 5 Modbus TCP RTUs deployed across the Indian 11kV distribution feeder:
  - RTU 1 (Port 5021): Substation-11kV (Bus 1) & Feeder Head / Trafo LV
  - RTU 2 (Port 5022): Bus-1-FeederA (Bus 2)
  - RTU 3 (Port 5023): Bus-2-FeederB (Bus 3)
  - RTU 4 (Port 5024): Bus-3-FeederC (Bus 4)
  - RTU 5 (Port 5025): Bus-4-FeederA2 (Bus 5)

Each RTU holds a 16-bit holding register map:
  Register 0: Voltage magnitude (pu x 10000)
  Register 1: Active power (kW x 1, signed 16-bit)
  Register 2: Reactive power (kVAR x 1, signed 16-bit)
  Register 3: Status / Quality flag (1=OK, 2=WARNING, 3=FAULT/TRIP)
"""

from __future__ import annotations

import asyncio
import logging
import math
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from pymodbus.datastore import (
    ModbusDeviceContext,
    ModbusSequentialDataBlock,
    ModbusServerContext,
)
from pymodbus.server import ModbusTcpServer

logger = logging.getLogger("GridSentinel.RTU")


# ---------------------------------------------------------------------------
# Register Map and Scaling Constants
# ---------------------------------------------------------------------------
REGISTER_MAP = {
    "VOLTAGE_PU": {
        "address": 0,
        "description": "Bus voltage magnitude in per-unit (x10000)",
        "scale": 10000.0,
        "signed": False,
        "unit": "pu",
    },
    "ACTIVE_POWER_KW": {
        "address": 1,
        "description": "Active power in kW (x1)",
        "scale": 1000.0,  # 1 MW = 1000 kW
        "signed": True,
        "unit": "kW",
    },
    "REACTIVE_POWER_KVAR": {
        "address": 2,
        "description": "Reactive power in kVAR (x1)",
        "scale": 1000.0,  # 1 MVAR = 1000 kVAR
        "signed": True,
        "unit": "kVAR",
    },
    "STATUS_FLAG": {
        "address": 3,
        "description": "Status code: 1=OK, 2=WARNING, 3=FAULT/TRIP, 0=OFFLINE",
        "scale": 1.0,
        "signed": False,
        "unit": "code",
    },
}

# RTU Configuration metadata
RTU_CONFIGS = [
    {
        "rtu_id": 1,
        "name": "RTU-1-Substation",
        "port": 5021,
        "monitored_bus": 1,
        "monitored_bus_name": "Substation-11kV",
        "monitored_line": 0,
        "monitored_trafo": 0,
        "description": "Monitors 11kV Substation bus and feeder head injection",
    },
    {
        "rtu_id": 2,
        "name": "RTU-2-FeederA",
        "port": 5022,
        "monitored_bus": 2,
        "monitored_bus_name": "Bus-1-FeederA",
        "monitored_line": 0,
        "description": "Monitors Feeder A (Industrial Load) bus and line flow",
    },
    {
        "rtu_id": 3,
        "name": "RTU-3-FeederB",
        "port": 5023,
        "monitored_bus": 3,
        "monitored_bus_name": "Bus-2-FeederB",
        "monitored_line": 1,
        "description": "Monitors Feeder B (Residential Load) bus and line flow",
    },
    {
        "rtu_id": 4,
        "name": "RTU-4-FeederC",
        "port": 5024,
        "monitored_bus": 4,
        "monitored_bus_name": "Bus-3-FeederC",
        "monitored_line": 2,
        "description": "Monitors Feeder C (Agriculture Load) bus and line flow",
    },
    {
        "rtu_id": 5,
        "name": "RTU-5-FeederA2",
        "port": 5025,
        "monitored_bus": 5,
        "monitored_bus_name": "Bus-4-FeederA2",
        "monitored_line": 3,
        "description": "Monitors Feeder A2 branch endpoint",
    },
]


# ---------------------------------------------------------------------------
# Conversion Utilities
# ---------------------------------------------------------------------------
def to_uint16(val: int) -> int:
    """Clamp and convert signed int to 16-bit unsigned representation."""
    return int(val) & 0xFFFF


def from_uint16(val: int) -> int:
    """Convert unsigned 16-bit register value back to signed int."""
    val = int(val) & 0xFFFF
    return val - 65536 if val >= 32768 else val


def encode_telemetry(
    voltage_pu: float,
    p_mw: float,
    q_mvar: float,
    status: int = 1,
) -> List[int]:
    """
    Encode physical telemetry values into 4 x 16-bit holding registers.
    Safely handles NaN/None (e.g. for physically islanded or tripped buses).
    """
    if voltage_pu is None or np.isnan(voltage_pu):
        voltage_pu = 0.0
        status = 3  # Tripped / De-energized

    if p_mw is None or np.isnan(p_mw):
        p_mw = 0.0

    if q_mvar is None or np.isnan(q_mvar):
        q_mvar = 0.0

    v_reg = int(round(voltage_pu * REGISTER_MAP["VOLTAGE_PU"]["scale"]))
    v_reg = max(0, min(65535, v_reg))

    p_kw = int(round(p_mw * REGISTER_MAP["ACTIVE_POWER_KW"]["scale"]))
    p_reg = to_uint16(p_kw)

    q_kvar = int(round(q_mvar * REGISTER_MAP["REACTIVE_POWER_KVAR"]["scale"]))
    q_reg = to_uint16(q_kvar)

    status_reg = max(0, min(65535, int(status)))

    return [v_reg, p_reg, q_reg, status_reg]


def decode_telemetry(registers: List[int]) -> Dict[str, Any]:
    """
    Decode 4 x 16-bit holding registers into physical floating point values.
    """
    if len(registers) < 4:
        raise ValueError(f"Expected at least 4 registers, got {len(registers)}")

    v_raw = registers[0]
    p_raw = from_uint16(registers[1])
    q_raw = from_uint16(registers[2])
    status_raw = registers[3]

    return {
        "voltage_pu": round(v_raw / REGISTER_MAP["VOLTAGE_PU"]["scale"], 5),
        "p_mw": round(p_raw / REGISTER_MAP["ACTIVE_POWER_KW"]["scale"], 5),
        "q_mvar": round(q_raw / REGISTER_MAP["REACTIVE_POWER_KVAR"]["scale"], 5),
        "p_kw": float(p_raw),
        "q_kvar": float(q_raw),
        "status_flag": int(status_raw),
    }


# ---------------------------------------------------------------------------
# Simulated RTU Class
# ---------------------------------------------------------------------------
class SimulatedRTU:
    """
    Asynchronous Modbus TCP RTU Server.
    """

    def __init__(self, config: Dict[str, Any], host: str = "127.0.0.1"):
        self.config = config
        self.rtu_id: int = config["rtu_id"]
        self.name: str = config["name"]
        self.port: int = config["port"]
        self.host: str = host
        self.monitored_bus: int = config["monitored_bus"]

        # Default initial values: V=1.0 pu, P=0 kW, Q=0 kVAR, Status=1 (OK)
        self.initial_registers = encode_telemetry(voltage_pu=1.0, p_mw=0.0, q_mvar=0.0, status=1)

        self._block = ModbusSequentialDataBlock(1, self.initial_registers)
        self._dev_ctx = ModbusDeviceContext(hr=self._block)
        self._context = ModbusServerContext(devices=self._dev_ctx, single=True)

        self._server: Optional[ModbusTcpServer] = None
        self._server_task: Optional[asyncio.Task] = None
        self.is_running: bool = False

        # In-memory mirror of last written engineering values
        self._current_values = {
            "voltage_pu": 1.0,
            "p_mw": 0.0,
            "q_mvar": 0.0,
            "status_flag": 1,
        }

    async def start(self) -> None:
        """Start the Modbus TCP server in the background."""
        if self.is_running:
            return

        try:
            self._server = ModbusTcpServer(context=self._context, address=(self.host, self.port))
            self._server_task = asyncio.create_task(self._server.serve_forever())
            self.is_running = True
            logger.info(f"[{self.name}] Started Modbus TCP server on {self.host}:{self.port}")
        except Exception as exc:
            logger.error(f"[{self.name}] Failed to start on port {self.port}: {exc}")
            raise

    async def stop(self) -> None:
        """Stop the Modbus TCP server."""
        if not self.is_running:
            return

        self.is_running = False
        if self._server:
            try:
                await self._server.shutdown()
            except Exception:
                pass
            self._server = None

        if self._server_task:
            self._server_task.cancel()
            try:
                await self._server_task
            except (asyncio.CancelledError, Exception):
                pass
            self._server_task = None

        logger.info(f"[{self.name}] Stopped Modbus TCP server on port {self.port}")

    async def write_values(
        self,
        voltage_pu: float,
        p_mw: float,
        q_mvar: float,
        status: int = 1,
    ) -> None:
        """
        Push new physical measurements into the RTU holding registers.
        """
        registers = encode_telemetry(voltage_pu, p_mw, q_mvar, status)
        self._current_values = {
            "voltage_pu": voltage_pu,
            "p_mw": p_mw,
            "q_mvar": q_mvar,
            "status_flag": status,
        }
        # In pymodbus 3.x, update server context registers directly
        if self._server and hasattr(self._server, "context") and self._server.context:
            await self._server.context.async_setValues(1, 16, 0, registers)
        elif self._context:
            try:
                await self._context.async_setValues(1, 16, 0, registers)
            except Exception:
                pass

    def get_current_values(self) -> Dict[str, Any]:
        """Return the current in-memory engineering values."""
        return dict(self._current_values)


# ---------------------------------------------------------------------------
# RTU Pool Manager
# ---------------------------------------------------------------------------
class RTUPool:
    """
    Manages the lifecycle of all 5 simulated RTUs.
    """

    def __init__(self, host: str = "127.0.0.1"):
        self.host = host
        self.rtus: Dict[int, SimulatedRTU] = {
            cfg["rtu_id"]: SimulatedRTU(cfg, host=host) for cfg in RTU_CONFIGS
        }

    async def start_all(self) -> None:
        """Start all 5 RTU servers concurrently."""
        await asyncio.gather(*(rtu.start() for rtu in self.rtus.values()))

    async def stop_all(self) -> None:
        """Stop all 5 RTU servers."""
        await asyncio.gather(*(rtu.stop() for rtu in self.rtus.values()))

    def get_rtu(self, rtu_id: int) -> Optional[SimulatedRTU]:
        return self.rtus.get(rtu_id)

    def get_all_status(self) -> List[Dict[str, Any]]:
        """Return status information for all 5 RTUs."""
        result = []
        for rtu_id, rtu in sorted(self.rtus.items()):
            vals = rtu.get_current_values()
            result.append(
                {
                    "rtu_id": rtu_id,
                    "name": rtu.name,
                    "port": rtu.port,
                    "host": rtu.host,
                    "is_running": rtu.is_running,
                    "monitored_bus": rtu.monitored_bus,
                    "telemetry": vals,
                }
            )
        return result


# Global singleton instance for the application
rtu_pool = RTUPool()
