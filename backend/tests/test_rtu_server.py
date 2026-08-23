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
