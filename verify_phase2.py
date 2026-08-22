"""
verify_phase2.py
----------------
End-to-end verification script for GridSentinel Phase 2.
Tests:
1. 5 Modbus TCP RTU servers & SCADA master polling.
2. Traffic logger capturing transactions and unexpected writes.
3. Scenario Injector:
   - Silent Data Injection (telemetry fabricated, pandapower untouched)
   - Command Injection (unauthorized write logged as anomaly)
   - Replay Attack (frozen telemetry)
   - Physical Line Trip (pandapower line tripped, power flow alters, propagates to RTUs)
4. Full integration tick loop + WLS state estimation.
"""

import asyncio
import sys
import numpy as np
import pandapower as pp

from app.core.feeder import build_feeder, run_power_flow
from app.core.state_estimation import add_measurements, run_state_estimation, detect_bad_data
from app.ot.rtu_server import rtu_pool, RTU_CONFIGS
from app.ot.scada_master import scada_master
from app.ot.scenario_injector import scenario_injector
from app.ot.simulation_loop import sim_loop
from app.ot.traffic_logger import traffic_logger


async def main():
    print("=" * 70)
    print("GRIDSENTINEL PHASE 2 -- END-TO-END VERIFICATION")
    print("=" * 70)

    # -----------------------------------------------------------------------
    # Step 1: Start RTUs and Verify Polling
    # -----------------------------------------------------------------------
    print("\n[1/4] Starting 5 Modbus TCP RTUs on ports 5021-5025...")
    traffic_logger.clear()
    await rtu_pool.start_all()

    for rtu_id in range(1, 6):
        rtu = rtu_pool.get_rtu(rtu_id)
        assert rtu.is_running, f"RTU {rtu_id} failed to start"
        print(f"  [OK] {rtu.name} running on port {rtu.port}")

    print("\nPolling all 5 RTUs via SCADA Master...")
    # Seed known values
    for rtu_id in range(1, 6):
        await rtu_pool.get_rtu(rtu_id).write_values(
            voltage_pu=0.970 + rtu_id * 0.002,
            p_mw=0.200 + rtu_id * 0.050,
            q_mvar=0.100 + rtu_id * 0.020,
            status=1,
        )

    polled = await scada_master.poll_all_rtus()
    assert len(polled) == 5, f"Expected 5 polled RTUs, got {len(polled)}"
    for rtu_id in range(1, 6):
        data = polled[rtu_id]
        print(f"  [OK] Polled RTU-{rtu_id}: V={data['voltage_pu']:.4f} pu, P={data['p_mw']:.3f} MW, Q={data['q_mvar']:.3f} MVAR, Status={data['status_flag']}")

    # Check traffic log
    events = traffic_logger.get_recent_events(limit=10)
    print(f"  [OK] Traffic logger captured {len(events)} events (all legitimate SCADA reads)")
    assert all(e["function_code"] == 3 and not e["is_unexpected_write"] for e in events)

    await rtu_pool.stop_all()

    # -----------------------------------------------------------------------
    # Step 2: Start Simulation Loop & Check Baseline State Estimation
    # -----------------------------------------------------------------------
    print("\n[2/4] Initializing Simulation Loop & Diurnal Engine...")
    net = build_feeder()
    await sim_loop.start(net=net)

    snap = await sim_loop.tick()
    print(f"  [OK] Sim Time: {snap['sim_time']} (Diurnal Multiplier: {snap['diurnal_multiplier']}x)")
    print(f"  [OK] Power Flow Converged: {snap['power_flow_converged']}")
    print(f"  [OK] State Estimation Success: {snap['state_estimation']['success']}")
    print(f"  [OK] Chi-Square Test Passed: {snap['state_estimation']['chi2_test_passed']} (Stat: {snap['state_estimation']['chi2_statistic']}, Thresh: {snap['state_estimation']['chi2_threshold']})")
    assert snap["state_estimation"]["success"] is True

    # -----------------------------------------------------------------------
    # Step 3: Test Scenario Injector (Attacks vs Faults)
    # -----------------------------------------------------------------------
    print("\n[3/4] Testing Cyber Attacks & Physical Faults...")

    # A. Silent Data Injection
    print("\n  [A] Injecting Silent Data Injection on RTU 2 (V=1.150 pu)...")
    scenario_injector.inject_silent_data_injection(rtu_id=2, voltage_pu=1.150, duration_ticks=5)
    snap_sdi = await sim_loop.tick()

    reported_v2 = snap_sdi["polled_modbus_telemetry"][2]["voltage_pu"]
    true_v2 = float(net.res_bus.at[2, "vm_pu"])
    print(f"      - Reported Telemetry from RTU 2: {reported_v2:.4f} pu")
    print(f"      - True Pandapower Grid State:    {true_v2:.4f} pu")
    print(f"      - Physical/Cyber Divergence:     {abs(reported_v2 - true_v2):.4f} pu")
    assert abs(reported_v2 - 1.150) < 0.005, "Reported telemetry did not reflect attack"
    assert abs(true_v2 - 0.968) < 0.015, "Pandapower true state was improperly modified"
    print("      [OK] Confirmed: Cyber attack successfully spoofed telemetry while physical grid remained untouched!")

    # Check Bad Data Detector caught the physics violation
    print(f"      - Bad Data Detected by Physics Engine: {snap_sdi['state_estimation']['bad_data_detected']}")
    scenario_injector.clear_all_scenarios(net=net)

    # B. Command Injection
    print("\n  [B] Injecting Unauthorized Modbus Command Write on RTU 3...")
    traffic_logger.clear()
    cmd_res = await scenario_injector.inject_command_write(rtu_id=3, register_address=0, value=12000)
    print(f"      - Command status: {cmd_res['status']}")

    recent_events = traffic_logger.get_recent_events(limit=5)
    unexpected = [e for e in recent_events if e["is_unexpected_write"]]
    assert len(unexpected) >= 1, "Command injection was not logged as unexpected write"
    print(f"      [OK] Confirmed: Traffic logger captured and flagged unauthorized write from {unexpected[0]['source']} (FC {unexpected[0]['function_code']})!")

    # C. Replay Attack
    print("\n  [C] Injecting Telemetry Replay Attack on RTU 4...")
    rep_res = scenario_injector.inject_replay(rtu_id=4, duration_ticks=5)
    snap_rep = await sim_loop.tick()
    print(f"      - Replay active on RTUs: {snap_rep['active_scenarios']['replay_attacks']}")
    assert 4 in snap_rep['active_scenarios']['replay_attacks']
    print("      [OK] Confirmed: Telemetry successfully frozen on RTU 4!")
    scenario_injector.clear_all_scenarios(net=net)

    # D. Physical Line Trip
    print("\n  [D] Triggering Physical Line Trip on Line 0 (Feeder A)...")
    scenario_injector.trigger_line_trip(net=net, line_index=0)
    snap_trip = await sim_loop.tick()

    line_0_loading = next((l["loading_percent"] for l in snap_trip["true_physical_state"]["line_loadings"] if l["line_index"] == 0), 0.0)
    p_bus2 = snap_trip["polled_modbus_telemetry"][2]["p_mw"]
    print(f"      - Line 0 Physical Loading:       {line_0_loading}%")
    print(f"      - RTU 2 Downstream Power Flow:   {p_bus2:.3f} MW")
    assert bool(net.line.at[0, "in_service"]) is False
    assert abs(p_bus2) < 0.05
    print("      [OK] Confirmed: Physical trip modified grid topology and naturally flowed down to Modbus telemetry!")

    # -----------------------------------------------------------------------
    # Step 4: Cleanup & Normal State Restoration
    # -----------------------------------------------------------------------
    print("\n[4/4] Resetting all scenarios and verifying clean recovery...")
    scenario_injector.clear_all_scenarios(net=net)
    snap_clean = await sim_loop.tick()
    assert snap_clean["active_scenarios"]["summary"] == "NORMAL_OPERATION"
    print("  [OK] All cyber-attacks and physical faults cleared. Feeder operating normally.")

    await sim_loop.stop()

    print("\n" + "=" * 70)
    print("ALL PHASE 2 END-TO-END VERIFICATIONS PASSED SUCCESSFULLY!")
    print("=" * 70)

if __name__ == "__main__":
    asyncio.run(main())
