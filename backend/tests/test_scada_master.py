"""
test_scada_master.py
--------------------
Tests for SCADA Master polling client, Modbus traffic logging, and feeding state estimation.
"""

import asyncio
import pytest
from app.core.feeder import build_feeder, run_power_flow
from app.core.state_estimation import add_measurements, run_state_estimation
from app.ot.rtu_server import rtu_pool
from app.ot.scada_master import scada_master
from app.ot.traffic_logger import traffic_logger


@pytest.mark.asyncio
class TestSCADAMasterPolling:
    async def test_scada_master_polls_all_rtus(self):
        """Verify that SCADA Master polls all 5 RTUs over Modbus TCP and decodes values."""
        traffic_logger.clear()
        await rtu_pool.start_all()

        try:
            # Seed test values into all 5 RTUs
            for rtu_id in range(1, 6):
                rtu = rtu_pool.get_rtu(rtu_id)
                await rtu.write_values(
                    voltage_pu=0.970 + rtu_id * 0.002,
                    p_mw=0.200 + rtu_id * 0.050,
                    q_mvar=0.100 + rtu_id * 0.020,
                    status=1,
                )

            # Poll all 5 RTUs via SCADA Master
            telemetry = await scada_master.poll_all_rtus()

            assert len(telemetry) == 5, f"Expected 5 polled RTUs, got {len(telemetry)}"

            for rtu_id in range(1, 6):
                assert rtu_id in telemetry
                t = telemetry[rtu_id]
                expected_v = 0.970 + rtu_id * 0.002
                expected_p = 0.200 + rtu_id * 0.050

                assert abs(t["voltage_pu"] - expected_v) < 1e-3
                assert abs(t["p_mw"] - expected_p) < 1e-3
                assert t["status_flag"] == 1

            # Verify traffic logger captured all 5 read transactions
            events = traffic_logger.get_recent_events(limit=10)
            assert len(events) >= 5
            for ev in events[:5]:
                assert ev["function_code"] == 3  # Read Holding Registers
                assert ev["source"] == "SCADA_MASTER"
                assert ev["is_unexpected_write"] is False
                assert ev["success"] is True

        finally:
            await rtu_pool.stop_all()

    async def test_polled_telemetry_feeds_state_estimation(self):
        """
        Verify that Modbus polled telemetry integrates into pandapower state estimation
        and yields accurate state estimates close to power-flow truth.
        """
        await rtu_pool.start_all()
        net = build_feeder()
        run_power_flow(net)

        try:
            # Push true power flow results to RTUs
            v1 = float(net.res_bus.at[1, "vm_pu"])
            p1 = float(net.res_trafo.at[0, "p_lv_mw"])
            q1 = float(net.res_trafo.at[0, "q_lv_mvar"])
            await rtu_pool.get_rtu(1).write_values(v1, p1, q1)

            for rtu_id, bus_idx, line_idx in [(2, 2, 0), (3, 3, 1), (4, 4, 2), (5, 5, 3)]:
                v = float(net.res_bus.at[bus_idx, "vm_pu"])
                p = float(net.res_line.at[line_idx, "p_from_mw"])
                q = float(net.res_line.at[line_idx, "q_from_mvar"])
                await rtu_pool.get_rtu(rtu_id).write_values(v, p, q)

            # Poll via SCADA Master
            telemetry = await scada_master.poll_all_rtus()

            # Feed polled telemetry into State Estimation
            add_measurements(net, telemetry=telemetry)
            se_res = run_state_estimation(net)

            assert se_res["success"] is True
            assert se_res["chi2_test_passed"] is True

            # Verify estimated voltages are within 0.01 pu of true power flow
            for ev in se_res["estimated_voltages"]:
                b_idx = ev["bus_index"]
                if net.bus.at[b_idx, "vn_kv"] == 11.0 and ev["vm_pu_est"] is not None:
                    true_v = float(net.res_bus.at[b_idx, "vm_pu"])
                    assert abs(ev["vm_pu_est"] - true_v) < 0.01

        finally:
            await rtu_pool.stop_all()
