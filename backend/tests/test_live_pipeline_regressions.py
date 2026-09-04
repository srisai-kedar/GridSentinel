"""Regression tests for the production live telemetry/classifier lifecycle."""

from unittest.mock import AsyncMock

import pytest

from app.core.feeder import build_feeder
from app.ml.classifier_service import classifier_service
from app.ot.scenario_injector import scenario_injector
from app.ot.simulation_loop import SimulationLoop
from app.ot.rtu_server import rtu_pool
from app.ot.scada_master import scada_master
from app.ot.traffic_logger import traffic_logger


@pytest.mark.asyncio
async def test_simulation_tick_evaluates_classifier_from_polled_telemetry(monkeypatch):
    """A live tick must feed the same polled frame into automatic inference."""
    loop = SimulationLoop(tick_interval_seconds=60)
    loop.net = build_feeder()
    loop._base_load_p = {idx: float(row["p_mw"]) for idx, row in loop.net.load.iterrows()}
    loop._base_load_q = {idx: float(row["q_mvar"]) for idx, row in loop.net.load.iterrows()}

    polled = {
        rtu_id: {"voltage_pu": 0.98, "p_mw": 0.2, "q_mvar": 0.05, "status_flag": 1}
        for rtu_id in range(1, 6)
    }
    observed = {}

    async def poll_all_rtus():
        return polled

    def evaluate_all_rtus(**kwargs):
        observed.update(kwargs)
        return {
            rtu_id: {
                "verdict": "Normal",
                "subtype": "normal",
                "confidence": 0.96,
                "probabilities": {"Normal": 0.96},
            }
            for rtu_id in range(1, 6)
        }

    monkeypatch.setattr(scada_master, "poll_all_rtus", poll_all_rtus)
    monkeypatch.setattr(rtu_pool, "get_rtu", lambda _rtu_id: None)
    monkeypatch.setattr(classifier_service, "evaluate_all_rtus", evaluate_all_rtus)
    scenario_injector.clear_all_scenarios(net=loop.net)
    traffic_logger.clear()

    snapshot = await loop.tick()

    assert observed["polled_telemetry"] == polled
    assert observed["traffic_events"] == []
    assert len(snapshot["ml_verdicts"]) == 5
    assert snapshot["stream_status"] == "streaming"
    assert snapshot["simulation_running"] is True


@pytest.mark.asyncio
async def test_stop_clears_classifier_cache_and_broadcasts_stopped(monkeypatch):
    """Stopping the OT lifecycle must not leave old verdicts visible to clients."""
    loop = SimulationLoop()
    loop.latest_state = {
        "tick": 7,
        "sim_time": "09:45:00",
        "ml_verdicts": {"2": {"verdict": "Cyber Intrusion"}},
        "active_scenarios": {"summary": "ATTACK"},
        "recent_traffic_log": [{"event_id": 1}],
    }
    loop.is_running = True
    classifier_service.latest_verdicts = {2: {"verdict": "Cyber Intrusion"}}
    monkeypatch.setattr(rtu_pool, "stop_all", AsyncMock())

    await loop.stop()

    assert classifier_service.latest_verdicts == {}
    assert loop.latest_state["simulation_running"] is False
    assert loop.latest_state["stream_status"] == "stopped"
    assert loop.latest_state["stale"] is True
    assert loop.latest_state["ml_verdicts"] == {}
    assert loop.latest_state["active_scenarios"]["summary"] == "NORMAL_OPERATION"


@pytest.mark.asyncio
async def test_tick_failure_surfaces_explicit_error_state(monkeypatch):
    """A tick exception is observable instead of silently killing the loop."""
    loop = SimulationLoop(tick_interval_seconds=0.05)
    loop.is_running = True

    async def failed_tick():
        loop.is_running = False
        raise RuntimeError("synthetic tick failure")

    monkeypatch.setattr(loop, "tick", failed_tick)
    monkeypatch.setattr(loop, "_broadcast_ws", AsyncMock())

    await loop._run_loop()

    assert loop.last_error == "RuntimeError: synthetic tick failure"
    assert loop.latest_state["stream_status"] == "error"
    assert loop.latest_state["stale"] is True
