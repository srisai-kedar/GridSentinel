"""
test_rtu_server.py
------------------
Unit tests for Modbus RTU servers, holding register maps, and encoding/decoding.
"""

import asyncio
import pytest
from app.ot.rtu_server import (
    REGISTER_MAP,
    RTU_CONFIGS,
    SimulatedRTU,
    decode_telemetry,
    encode_telemetry,
    from_uint16,
    to_uint16,
)


class TestRTUEncoding:
    def test_uint16_conversions(self):
        """Test signed to unsigned 16-bit integer conversions."""
        # Positive values
        assert to_uint16(500) == 500
        assert from_uint16(500) == 500

        # Zero
        assert to_uint16(0) == 0
        assert from_uint16(0) == 0

        # Negative values (two's complement 16-bit)
        assert to_uint16(-1) == 65535
        assert from_uint16(65535) == -1

        assert to_uint16(-1000) == 64536
        assert from_uint16(64536) == -1000

    def test_encode_decode_roundtrip(self):
        """Verify that encoding and decoding telemetry preserves physical values."""
        v_in = 0.9735
        p_in = 0.280  # 280 kW
        q_in = 0.175  # 175 kVAR
        status_in = 1

        regs = encode_telemetry(v_in, p_in, q_in, status_in)
        assert len(regs) == 4
        assert regs[0] == 9735  # 0.9735 * 10000
        assert regs[1] == 280   # 0.280 * 1000
        assert regs[2] == 175   # 0.175 * 1000
        assert regs[3] == 1

        decoded = decode_telemetry(regs)
        assert abs(decoded["voltage_pu"] - v_in) < 1e-4
        assert abs(decoded["p_mw"] - p_in) < 1e-4
        assert abs(decoded["q_mvar"] - q_in) < 1e-4
        assert decoded["status_flag"] == status_in

    def test_encode_decode_negative_power_roundtrip(self):
        """Verify negative power flow (e.g. transformer feed -1.184 MW) roundtrips correctly."""
        v_in = 0.9850
        p_in = -1.184  # -1184 kW
        q_in = -0.738  # -738 kVAR
        status_in = 1

        regs = encode_telemetry(v_in, p_in, q_in, status_in)
        decoded = decode_telemetry(regs)

        assert abs(decoded["voltage_pu"] - v_in) < 1e-4
        assert abs(decoded["p_mw"] - p_in) < 1e-3
        assert abs(decoded["q_mvar"] - q_in) < 1e-3

    def test_register_map_completeness(self):
        """Ensure all 4 registers are defined with descriptions and scale factors."""
        assert "VOLTAGE_PU" in REGISTER_MAP
        assert "ACTIVE_POWER_KW" in REGISTER_MAP
        assert "REACTIVE_POWER_KVAR" in REGISTER_MAP
        assert "STATUS_FLAG" in REGISTER_MAP

        assert REGISTER_MAP["VOLTAGE_PU"]["scale"] == 10000.0
        assert REGISTER_MAP["ACTIVE_POWER_KW"]["scale"] == 1000.0


@pytest.mark.asyncio
class TestSimulatedRTUServer:
    async def test_rtu_start_write_and_stop(self):
        """Verify that a single simulated RTU server starts, accepts writes, and shuts down."""
        cfg = {
            "rtu_id": 99,
            "name": "RTU-Test",
            "port": 5099,
            "monitored_bus": 1,
        }
        rtu = SimulatedRTU(cfg)
        assert not rtu.is_running

        await rtu.start()
        assert rtu.is_running

        # Write values
        await rtu.write_values(voltage_pu=0.965, p_mw=0.350, q_mvar=0.210, status=1)
        vals = rtu.get_current_values()
        assert vals["voltage_pu"] == 0.965
        assert vals["p_mw"] == 0.350

        await rtu.stop()
        assert not rtu.is_running

    async def test_startup_race_no_sleep(self):
        """
        Regression test for RTU startup-readiness race (Task 6).

        Before the fix, SimulatedRTU.start() created a serve_forever() task but
        marked is_running=True immediately.  The TCP socket had NOT yet been bound,
        so a client connecting immediately after 'await rtu.start()' (with zero
        sleep) would get a ConnectionRefusedError.

        After the fix, server.listen() is awaited synchronously inside start(),
        so the socket IS bound by the time start() returns.  This test verifies
        that an AsyncModbusTcpClient can connect and transact with NO sleep
        between start() and connect().
        """
        from pymodbus.client import AsyncModbusTcpClient

        cfg = {
            "rtu_id": 98,
            "name": "RTU-RaceTest",
            "port": 5098,
            "monitored_bus": 1,
        }
        rtu = SimulatedRTU(cfg)
        await rtu.start()
        assert rtu.is_running

        # Immediately connect — no sleep. Any ConnectionRefusedError here means
        # the startup race is still present.
        client = AsyncModbusTcpClient("127.0.0.1", port=5098, timeout=3.0)
        try:
            connected = await client.connect()
            assert connected, (
                "Client could not connect immediately after rtu.start() returned. "
                "This indicates the startup-readiness race condition is still present."
            )
            # Simple FC3 read to confirm the server is serving
            result = await client.read_holding_registers(address=0, count=4, device_id=1)
            assert not result.isError(), f"FC3 read failed: {result}"
            assert len(result.registers) == 4
        finally:
            client.close()
            await rtu.stop()

    async def test_rtu_observer_logs_unexpected_write(self):
        """
        Regression test for RTU-side write observer (Task 2/3 — NBD leakage fix).

        The RTU's trace_pdu callback must independently detect incoming FC6
        (Write Single Register) requests and log them to traffic_logger with
        is_unexpected_write=True and source='RTU_OBSERVED_WRITE'.

        Critically, the 'unexpected' classification must be derived from the
        observed Modbus function code at the server, NOT from a flag set by the
        attacker client (scenario_injector).
        """
        from pymodbus.client import AsyncModbusTcpClient
        from app.ot.traffic_logger import traffic_logger

        traffic_logger.clear()
        cfg = {
            "rtu_id": 97,
            "name": "RTU-ObserverTest",
            "port": 5097,
            "monitored_bus": 1,
        }
        rtu = SimulatedRTU(cfg)
        await rtu.start()

        client = AsyncModbusTcpClient("127.0.0.1", port=5097, timeout=3.0)
        try:
            connected = await client.connect()
            assert connected, "Test client failed to connect to RTU observer test server"

            # Send FC6 (Write Single Register) — this is the attacker's action
            wr = await client.write_register(address=0, value=9500, device_id=1)
            assert not wr.isError(), f"FC6 write failed unexpectedly: {wr}"

            # Give asyncio a moment to dispatch the trace_pdu callback
            await asyncio.sleep(0.05)

        finally:
            client.close()
            await rtu.stop()

        # Verify the RTU-side observer logged the write
        events = traffic_logger.get_recent_events(limit=10)
        observed_writes = [e for e in events if e["is_unexpected_write"]]

        assert len(observed_writes) >= 1, (
            "RTU-side trace_pdu observer must log at least one is_unexpected_write=True entry "
            "when an FC6 write is received, but none were found in the traffic log. "
            "Check that _make_write_observer() is wired into ModbusTcpServer(trace_pdu=...)."
        )
        obs = observed_writes[0]
        assert obs["source"] == "RTU_OBSERVED_WRITE", (
            f"Expected source='RTU_OBSERVED_WRITE', got '{obs['source']}'. "
            "The write flag must come from the RTU observer, not from the client."
        )
        assert obs["function_code"] == 6, (
            f"Expected FC6 (Write Single Register), got FC{obs['function_code']}"
        )
        assert obs["is_unexpected_write"] is True
        assert "RTU-ObserverTest" in obs["target_rtu"]
