"""
test_scenario_injector.py
-------------------------
Tests for all 3 cyber-attack types and 2 physical-fault types, verifying the
fundamental distinction:
  - Cyber attacks fake telemetry without altering pandapower's real physical state.
  - Physical faults alter pandapower's true state, which then naturally propagates into telemetry.
"""

import pytest
from app.core.feeder import build_feeder, run_power_flow
from app.ot.rtu_server import rtu_pool
from app.ot.scada_master import scada_master
from app.ot.scenario_injector import scenario_injector
from app.ot.simulation_loop import sim_loop
from app.ot.traffic_logger import traffic_logger


@pytest.mark.asyncio
class TestScenarioInjector:
    async def test_silent_data_injection_attack(self):
        """
        Verify Silent Data Injection:
          1. Overrides reported telemetry at target RTU.
          2. pandapower's true internal state remains completely UNTOUCHED.
          3. Traffic logger records normal read operations (no anomalous writes).
        """
        traffic_logger.clear()
        net = build_feeder()
        await sim_loop.start(net=net)

        try:
            # Run one clean tick
            snap_clean = await sim_loop.tick()
            true_v2_clean = float(net.res_bus.at[2, "vm_pu"])
            reported_v2_clean = snap_clean["polled_modbus_telemetry"][2]["voltage_pu"]
            # Baseline tolerance: Gaussian noise std=0.002 pu (applied in simulation_loop._safe_float_val)
            # + 16-bit Modbus quantization (max 5e-5 pu). 3-sigma envelope ≈ 0.006 pu; 0.02 is safe.
            assert abs(reported_v2_clean - true_v2_clean) < 0.02

            # Inject Silent Data Injection on RTU 2 (fabricate voltage to 1.150 pu)
            scenario_injector.inject_silent_data_injection(
                rtu_id=2,
                voltage_pu=1.150,
                duration_ticks=5,
            )

            # Run tick under attack
            snap_attack = await sim_loop.tick()

            # 1. Reported Modbus telemetry reflects the fabricated value
            reported_v2_attack = snap_attack["polled_modbus_telemetry"][2]["voltage_pu"]
            assert abs(reported_v2_attack - 1.150) < 0.005

            # 2. pandapower's true physical voltage at Bus 2 is UNTOUCHED (~0.968 pu)
            true_v2_attack = float(net.res_bus.at[2, "vm_pu"])
            assert abs(true_v2_attack - true_v2_clean) < 0.01
            assert abs(reported_v2_attack - true_v2_attack) > 0.15  # Divergence proven!

            # 3. Traffic logger has NO anomalous writes logged (silent in network logs)
            events = traffic_logger.get_recent_events(limit=20)
            unexpected_writes = [e for e in events if e["is_unexpected_write"]]
            assert len(unexpected_writes) == 0

        finally:
            scenario_injector.clear_all_scenarios(net=net)
            await sim_loop.stop()

    async def test_command_injection_attack_logged(self):
        """
        Verify Command Injection:
          1. Sends an unauthorized Modbus TCP write command to target RTU.
          2. MUST be recorded as an anomalous unexpected write in traffic logger.
        """
        traffic_logger.clear()
        await rtu_pool.start_all()

        try:
            # Send unauthorized write to RTU 3, Register 0 (Voltage), Value 12000
            res = await scenario_injector.inject_command_write(
                rtu_id=3,
                register_address=0,
                value=12000,
            )
            assert res["status"] == "success"
            assert res["flagged_in_traffic_log"] is True

            # Verify the traffic logger has flagged this transaction
            events = traffic_logger.get_recent_events(limit=5)
            unexpected = [e for e in events if e["is_unexpected_write"]]

            assert len(unexpected) >= 1
            unauth_event = unexpected[0]
            assert unauth_event["function_code"] == 6  # Write Single Register
            assert unauth_event["source"] == "ATTACKER_COMMAND_INJECTION"
            assert "RTU-3" in unauth_event["target_rtu"]

        finally:
            await rtu_pool.stop_all()

    async def test_line_trip_fault_propagates_physically(self):
        """
        Verify Physical Line Trip:
          1. Line out-of-service in pandapower changes the TRUE physical power flow.
          2. The true physical change naturally propagates into polled telemetry.
        """
        net = build_feeder()
        await sim_loop.start(net=net)

        try:
            # Normal state tick
            snap_pre = await sim_loop.tick()

            # Trigger physical Line Trip on Line 0 (Feeder A main branch)
            scenario_injector.trigger_line_trip(net=net, line_index=0)
            assert bool(net.line.at[0, "in_service"]) is False

            # Run tick under fault
            snap_post = await sim_loop.tick()

            # Line 0 is out of service in pandapower, so line loading should be 0.0
            line_0_loading = next(
                (l["loading_percent"] for l in snap_post["true_physical_state"]["line_loadings"] if l["line_index"] == 0),
                None
            )
            assert line_0_loading == 0.0 or line_0_loading is None

            # Bus 2 (Bus-1-FeederA) is now physically disconnected / zero line flow.
            # pandapower sets res_line[0].p_from_mw = 0.0 for out-of-service lines.
            # The simulation loop adds Gaussian noise std=0.004 MW; 3σ ≈ 0.012 MW.
            # Threshold 0.10 MW is well below the pre-trip ~0.5 MW value.
            p_bus2_polled = snap_post["polled_modbus_telemetry"][2]["p_mw"]
            assert abs(p_bus2_polled) < 0.10, (
                f"Expected near-zero power after line trip but got {p_bus2_polled:.4f} MW"
            )

        finally:
            scenario_injector.clear_all_scenarios(net=net)
            await sim_loop.stop()

    async def test_short_circuit_stub_voltage_sag(self):
        """
        Verify Short Circuit Stub:
          1. Creates heavy load causing voltage sag at target bus.
          2. Restores normal voltage after duration expires.
        """
        net = build_feeder()
        run_power_flow(net)
        base_v4 = float(net.res_bus.at[4, "vm_pu"])

        # Attach fault load at Bus 4 (moderate fault load that produces heavy sag without numerical divergence)
        scenario_injector.trigger_short_circuit_stub(
            net=net,
            bus_index=4,
            fault_load_mw=2.5,
            fault_load_mvar=1.5,
            duration_ticks=2,
        )

        pf_res = run_power_flow(net)
        assert pf_res["converged"] is True
        sag_v4 = float(net.res_bus.at[4, "vm_pu"])
        # Severe voltage sag should be observable (> 0.03 pu sag)
        assert sag_v4 < base_v4 - 0.03

        # Advance 2 ticks to clear fault
        scenario_injector.on_simulation_tick(net)
        scenario_injector.on_simulation_tick(net)

        run_power_flow(net)
        cleared_v4 = float(net.res_bus.at[4, "vm_pu"])
        assert abs(cleared_v4 - base_v4) < 0.005
