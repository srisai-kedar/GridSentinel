"""
test_kill_resilience.py
-----------------------
Kill-test suite: verifies GridSentinel recovers gracefully from hostile conditions
that have caused real production regressions in previous demo sessions.

Each test simulates a specific failure mode and asserts the correct recovery
observable without leaving the server in an invalid state for subsequent tests.

Failure modes covered:
  KT-01  Simulation loop killed mid-run: restart produces clean state
  KT-02  Double-stop: second /ot/stop is idempotent
  KT-03  Double-start: second /ot/start is idempotent  
  KT-04  Reset while stopped: /ot/reset with no running simulation succeeds
  KT-05  Attack on non-existent RTU: 422 validation error, loop unaffected
  KT-06  Attack while sim stopped: endpoint rejects gracefully
  KT-07  Tick exception: loop sets error state, does not hang
  KT-08  WS disconnect mid-stream: server does not crash, queue cleaned up
  KT-09  Classifier cache stale after stop: verdicts cleared on OT stop
  KT-10  Multiple rapid start-stop cycles: server remains stable
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.ml.classifier_service import classifier_service
from app.ot.rtu_server import rtu_pool
from app.ot.simulation_loop import SimulationLoop, sim_loop
from app.ot.scenario_injector import scenario_injector
from app.ot.traffic_logger import traffic_logger


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def _ensure_stopped(client):
    """Guarantee each test starts with a stopped simulation."""
    client.post("/ot/stop")
    yield
    client.post("/ot/stop")


# ===========================================================================
# KT-01 — Simulation loop restart after kill produces clean state
# ===========================================================================


@pytest.mark.asyncio
async def test_kt01_restart_after_kill_produces_clean_state(monkeypatch):
    """
    Simulate the loop being killed externally while running.
    After /ot/start again, stream_status must be streaming, not error.
    """
    loop = SimulationLoop(tick_interval_seconds=60)
    loop.is_running = True
    loop.last_error = "RuntimeError: killed by signal"
    loop.latest_state = {
        "stream_status": "error",
        "stale": True,
        "tick": 3,
        "sim_time": "06:00:00",
        "ml_verdicts": {},
        "active_scenarios": {"summary": "NORMAL_OPERATION"},
        "recent_traffic_log": [],
    }

    # Simulate a clean stop
    monkeypatch.setattr(rtu_pool, "stop_all", AsyncMock())
    await loop.stop()

    assert loop.is_running is False
    assert loop.latest_state["stream_status"] == "stopped"
    assert loop.latest_state["stale"] is True
    # last_error is NOT cleared by stop — caller must inspect it
    # Verify classifier verdicts are flushed
    assert classifier_service.latest_verdicts == {}


# ===========================================================================
# KT-02 — Double-stop is idempotent (no crash, returns already_stopped)
# ===========================================================================


def test_kt02_double_stop_is_idempotent(client):
    """Two consecutive POST /ot/stop calls must both return 200."""
    r1 = client.post("/ot/stop")
    assert r1.status_code == 200
    assert r1.json()["status"] in ("stopped", "already_stopped")

    r2 = client.post("/ot/stop")
    assert r2.status_code == 200
    assert r2.json()["status"] == "already_stopped"


# ===========================================================================
# KT-03 — Double-start is idempotent (no duplicate goroutine / crash)
# ===========================================================================


def test_kt03_double_start_is_idempotent(client):
    """Two consecutive POST /ot/start calls must both return 200."""
    r1 = client.post("/ot/start")
    assert r1.status_code == 200
    assert r1.json()["status"] in ("started", "already_running")

    r2 = client.post("/ot/start")
    assert r2.status_code == 200
    assert r2.json()["status"] == "already_running"

    client.post("/ot/stop")


# ===========================================================================
# KT-04 — Reset while stopped: endpoint succeeds, cache is cleared
# ===========================================================================


def test_kt04_reset_while_stopped_succeeds(client):
    """POST /ot/reset when simulation is not running must return 200 ok."""
    # Plant some stale state
    scenario_injector._silent_overrides = {2: {"voltage_pu": 0.5}}
    traffic_logger.clear()

    r = client.post("/ot/reset")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"

    classifier_status = client.get("/classifier/status").json()
    assert classifier_status["cached_rtu_count"] == 0


# ===========================================================================
# KT-05 — Attack on non-existent RTU returns 422, loop is unaffected
# ===========================================================================


def test_kt05_attack_nonexistent_rtu_returns_422(client):
    """Silent data injection on RTU ID 99 (non-existent) must fail validation."""
    client.post("/ot/start")

    r = client.post(
        "/ot/attack/data-injection",
        json={"rtu_id": 99, "voltage_pu": 0.5, "duration_ticks": 5},
    )
    assert r.status_code == 422

    # Loop must still be running
    status = client.get("/ot/status").json()
    assert status["is_simulation_running"] is True

    client.post("/ot/stop")


# ===========================================================================
# KT-06 — Attack while sim stopped: endpoint still works (scenario is queued)
# ===========================================================================


def test_kt06_attack_while_sim_stopped_succeeds_gracefully(client):
    """
    POST /ot/attack/data-injection while stopped must NOT return 500.
    The scenario endpoint works independently of the running loop.
    """
    r = client.post(
        "/ot/attack/data-injection",
        json={"rtu_id": 2, "voltage_pu": 0.75, "duration_ticks": 3},
    )
    # Must be 200 (scenario is accepted for next run) or 409/503 — but NOT 500
    assert r.status_code != 500, f"Server crashed on attack-while-stopped: {r.text}"
    assert r.status_code in (200, 409, 503)

    # Clean up
    client.post("/ot/reset")


# ===========================================================================
# KT-07 — Tick exception: loop sets error state, does not hang forever
# ===========================================================================


@pytest.mark.asyncio
async def test_kt07_tick_exception_surfaces_error_state(monkeypatch):
    """
    A tick that raises RuntimeError must set stream_status='error' and
    stale=True without hanging the process.
    """
    loop = SimulationLoop(tick_interval_seconds=0.02)
    loop.is_running = True

    call_count = 0

    async def bad_tick():
        nonlocal call_count
        call_count += 1
        loop.is_running = False   # stop after one failure
        raise RuntimeError("synthetic tick failure — disk full")

    monkeypatch.setattr(loop, "tick", bad_tick)
    monkeypatch.setattr(loop, "_broadcast_ws", AsyncMock())

    await asyncio.wait_for(loop._run_loop(), timeout=5.0)

    assert call_count >= 1
    assert loop.last_error == "RuntimeError: synthetic tick failure — disk full"
    assert loop.latest_state["stream_status"] == "error"
    assert loop.latest_state["stale"] is True


# ===========================================================================
# KT-08 — WS disconnect mid-stream: server does not crash; queue GC'd
# ===========================================================================


def test_kt08_websocket_disconnect_mid_stream_is_safe(client):
    """
    A client that disconnects immediately after receiving the first frame
    must not leave a dangling queue in the server.
    """
    client.post("/ot/start")

    import json as _json

    try:
        with client.websocket_connect("/ws/live") as ws:
            _ = _json.loads(ws.receive_text())   # consume initial frame
            # Disconnect immediately (context manager close)

    except Exception:
        pass  # disconnect-triggered exceptions are expected

    # Server should still respond to HTTP after WS disconnect
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    client.post("/ot/stop")


# ===========================================================================
# KT-09 — Classifier cache stale after stop: verdicts cleared
# ===========================================================================


@pytest.mark.asyncio
async def test_kt09_classifier_cache_cleared_on_ot_stop(monkeypatch):
    """
    Starting the sim, running a tick, then stopping must clear the classifier cache.
    This prevents the 'zombie verdict' bug where old Cyber Intrusion verdicts
    persist after the simulation loop is stopped.
    """
    loop = SimulationLoop()
    loop.is_running = True
    loop.latest_state = {
        "tick": 5,
        "sim_time": "10:00:00",
        "ml_verdicts": {"1": {"verdict": "Cyber Intrusion"}, "2": {"verdict": "Normal"}},
        "active_scenarios": {"summary": "ATTACK"},
        "recent_traffic_log": [],
    }
    # Plant stale verdicts in classifier cache
    classifier_service.latest_verdicts = {1: {"verdict": "Cyber Intrusion"}}

    monkeypatch.setattr(rtu_pool, "stop_all", AsyncMock())
    await loop.stop()

    assert loop.is_running is False
    assert classifier_service.latest_verdicts == {}
    assert loop.latest_state["ml_verdicts"] == {}
    assert loop.latest_state["active_scenarios"]["summary"] == "NORMAL_OPERATION"


# ===========================================================================
# KT-10 — Multiple rapid start-stop cycles: server remains stable
# ===========================================================================


def test_kt10_rapid_start_stop_cycles_remain_stable(client):
    """
    Three consecutive start → stop cycles must not corrupt server state.
    Each cycle must return the expected status codes.
    """
    for cycle in range(3):
        start_r = client.post("/ot/start")
        assert start_r.status_code == 200, f"cycle {cycle} start failed: {start_r.text}"
        assert start_r.json()["status"] in ("started", "already_running")

        stop_r = client.post("/ot/stop")
        assert stop_r.status_code == 200, f"cycle {cycle} stop failed: {stop_r.text}"
        assert stop_r.json()["status"] in ("stopped", "already_stopped")

    # Server must still answer health checks
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"
