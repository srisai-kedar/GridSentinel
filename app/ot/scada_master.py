"""
scada_master.py
---------------
Asynchronous SCADA Master client that polls all 5 simulated Modbus TCP RTUs,
logs every transaction to the traffic logger, decodes holding registers,
and provides decoded telemetry to the physics state estimation layer.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

from pymodbus.client import AsyncModbusTcpClient

from app.ot.rtu_server import RTU_CONFIGS, decode_telemetry
from app.ot.traffic_logger import traffic_logger

logger = logging.getLogger("GridSentinel.SCADAMaster")


class SCADAMaster:
    """
    SCADA Master polling client.
    """

    def __init__(self, host: str = "127.0.0.1", timeout: float = 1.5):
        self.host = host
        self.timeout = timeout
        self.last_poll_results: Dict[int, Dict[str, Any]] = {}
        self.last_poll_timestamp: Optional[float] = None
        self.poll_count: int = 0

    async def poll_rtu(self, rtu_cfg: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Poll a single RTU over Modbus TCP (Read Holding Registers: FC 03).
        Logs the transaction to the traffic logger.
        """
        rtu_id = rtu_cfg["rtu_id"]
        port = rtu_cfg["port"]
        target_name = f"{rtu_cfg['name']} (Port {port})"

        client = AsyncModbusTcpClient(self.host, port=port, timeout=self.timeout)
        start_time = time.perf_counter()

        try:
            connected = await client.connect()
            if not connected:
                elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                traffic_logger.log_transaction(
                    source="SCADA_MASTER",
                    target_rtu=target_name,
                    function_code=3,
                    response_time_ms=elapsed_ms,
                    is_unexpected_write=False,
                    details="Connection failed / timeout",
                    success=False,
                )
                return None

            # Read 4 holding registers starting at address 0
            rr = await client.read_holding_registers(address=0, count=4, device_id=1)
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0

            if rr.isError():
                traffic_logger.log_transaction(
                    source="SCADA_MASTER",
                    target_rtu=target_name,
                    function_code=3,
                    response_time_ms=elapsed_ms,
                    is_unexpected_write=False,
                    details=f"Modbus Error: {rr}",
                    success=False,
                )
                return None

            registers = list(rr.registers)
            telemetry = decode_telemetry(registers)
            telemetry["rtu_id"] = rtu_id
            telemetry["name"] = rtu_cfg["name"]
            telemetry["port"] = port
            telemetry["monitored_bus"] = rtu_cfg["monitored_bus"]
            telemetry["registers_raw"] = registers

            traffic_logger.log_transaction(
                source="SCADA_MASTER",
                target_rtu=target_name,
                function_code=3,
                response_time_ms=elapsed_ms,
                is_unexpected_write=False,
                details=f"Read registers: {registers} -> V={telemetry['voltage_pu']} pu, P={telemetry['p_mw']} MW",
                success=True,
            )

            return telemetry

        except Exception as exc:
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            traffic_logger.log_transaction(
                source="SCADA_MASTER",
                target_rtu=target_name,
                function_code=3,
                response_time_ms=elapsed_ms,
                is_unexpected_write=False,
                details=f"Exception: {str(exc)}",
                success=False,
            )
            return None
        finally:
            client.close()

    async def poll_all_rtus(self) -> Dict[int, Dict[str, Any]]:
        """
        Poll all 5 configured RTUs concurrently and return the telemetry dictionary.
        """
        tasks = [self.poll_rtu(cfg) for cfg in RTU_CONFIGS]
        results = await asyncio.gather(*tasks, return_exceptions=False)

        polled_data: Dict[int, Dict[str, Any]] = {}
        for cfg, res in zip(RTU_CONFIGS, results):
            rtu_id = cfg["rtu_id"]
            if res is not None:
                polled_data[rtu_id] = res

        self.last_poll_results = polled_data
        self.last_poll_timestamp = time.time()
        self.poll_count += 1

        return polled_data

    def get_latest_telemetry(self) -> Dict[int, Dict[str, Any]]:
        """Return the most recently polled telemetry."""
        return dict(self.last_poll_results)


# Global singleton instance
scada_master = SCADAMaster()
