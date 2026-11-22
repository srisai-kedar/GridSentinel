import asyncio
from pathlib import Path
import sys
from unittest.mock import AsyncMock, patch

import pandapower as pp

sys.path.insert(0, str(Path(__file__).parents[1]))

from app.core.feeder import build_feeder
from app.ot.scenario_injector import scenario_injector
from app.ot.scenario_registry import (
    SCENARIO_REGISTRY,
    apply_authorized_control_write,
    apply_communication_stall,
    apply_drift,
    apply_fdi,
    apply_load_step,
    apply_replay,
    apply_sustained_setpoint,
    get_scenario,
    load_scenario_weights,
)
from app.ot.scada_master import scada_master
from app.ot.simulation_loop import sim_loop
from app.ot.traffic_logger import traffic_logger


def teardown_function():
    scenario_injector.clear_all_scenarios()
    scada_master.communication_stalls.clear()
    sim_loop.clear_load_step()
    traffic_logger.clear()


def test_registry_and_weights_are_complete():
    assert get_scenario("fdi").label == "Cyber Intrusion"
    assert set(load_scenario_weights("clean")) == {"load_step", "authorized_control_write", "communication_stall", "normal"}
    assert abs(sum(load_scenario_weights("operational").values()) - 1.0) < 1e-12
    assert set(SCENARIO_REGISTRY) >= {"fdi", "breaker_open", "sustained_setpoint", "drift"}


def test_fdi_and_drift_store_parameterized_effects():
    fdi = apply_fdi(rtu_id=2, target="P", sigma_multiple=5, duration_ticks=4)
    assert fdi["scenario_params"] == {"target": "P", "sigma_multiple": 5}
    assert scenario_injector.silent_overrides[2]["overrides"]["p_mw"] > 0.2
    drift = apply_drift(rtu_id=3, mode="ramp", target="Q", duration_ticks=6, magnitude=0.1)
    assert drift["mode"] == "ramp"
    assert scenario_injector.sensor_drifts[3]["target"] == "Q"


def test_natural_line_trip_changes_network_without_a_write():
    net = build_feeder()
    before = traffic_logger.get_total_count()
    result = scenario_injector.trigger_line_trip(net, 0)
    assert not bool(net.line.at[0, "in_service"])
    assert result["type"] == "LINE_TRIP"
    assert traffic_logger.get_total_count() == before


def test_authorized_control_write_is_allow_listed_and_not_unexpected():
    result = apply_authorized_control_write(1, 3, 2)
    event = result["event"]
    assert event["source"] == "AUTHORIZED_CONTROL"
    assert event["is_unexpected_write"] is False
    assert result["label"] == "Normal-Operational"


def test_communication_stall_fails_poll_but_replay_does_not_configure_stall():
    async def run():
        apply_communication_stall(1, 1)
        failed = await scada_master.poll_rtu({"rtu_id": 1, "port": 1, "name": "RTU-1"})
        assert failed is None
        event = traffic_logger.get_recent_events(limit=1)[0]
        assert event["success"] is False
        apply_replay(rtu_id=1, duration_ticks=3)
        assert scada_master.communication_stalls == {}

    asyncio.run(run())


def test_breaker_open_changes_physical_state_and_uses_write_path():
    net = build_feeder()
    with patch.object(scenario_injector, "inject_command_write", new=AsyncMock(return_value={"status": "success"})) as write:
        result = asyncio.run(scenario_injector.inject_breaker_open(net, 1, 0))
    assert result["physical"]["type"] == "LINE_TRIP"
    assert not bool(net.line.at[0, "in_service"])
    write.assert_awaited_once()


def test_sustained_setpoint_records_duration_and_write_path():
    async def run():
        with patch.object(scenario_injector, "inject_command_write", new=AsyncMock(return_value={"status": "success"})) as write:
            result = await apply_sustained_setpoint(
                rtu_id=1, register_address=1, value=250, duration_ticks=5
            )
        assert result["type"] == "SUSTAINED_SETPOINT_WRITE"
        assert scenario_injector.sustained_setpoints[1]["value"] == 250
        write.assert_awaited_once()

    asyncio.run(run())


def test_load_step_has_bounded_duration():
    apply_load_step(0.1, 3)
    from app.ot.simulation_loop import sim_loop
    assert sim_loop._manual_load_step == 0.1
    assert sim_loop._manual_load_step_remaining == 3
