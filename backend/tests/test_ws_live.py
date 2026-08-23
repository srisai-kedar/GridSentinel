"""
test_ws_live.py
---------------
Integration tests for Phase 2 OT SCADA endpoints and the /ws/live WebSocket stream.
"""

import json
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.ot.simulation_loop import sim_loop


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


class TestOTApiEndpoints:
    def test_ot_start_and_status(self, client):
        """POST /ot/start starts simulation, GET /ot/status returns status."""
        resp = client.post("/ot/start")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] in ("started", "already_running")

        status_resp = client.get("/ot/status")
        assert status_resp.status_code == 200
        st = status_resp.json()
        assert st["is_simulation_running"] is True
        assert "sim_time" in st
        assert "active_scenarios" in st

    def test_ot_rtus_endpoint(self, client):
        """GET /ot/rtus returns 5 configured RTUs."""
        resp = client.get("/ot/rtus")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_rtus"] == 5
        assert len(data["rtus"]) == 5

        ports = [r["port"] for r in data["rtus"]]
        assert ports == [5021, 5022, 5023, 5024, 5025]

    def test_ot_traffic_endpoint(self, client):
        """GET /ot/traffic returns recent transactions."""
        resp = client.get("/ot/traffic?limit=10")
        assert resp.status_code == 200
        data = resp.json()
        assert "events" in data
        assert isinstance(data["events"], list)

    def test_ot_silent_data_injection_endpoint(self, client):
        """POST /ot/attack/data-injection accepts valid injection request."""
        resp = client.post(
            "/ot/attack/data-injection",
            json={
                "rtu_id": 2,
                "voltage_pu": 1.120,
                "duration_ticks": 10,
            },
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "injected"

    def test_ot_command_injection_endpoint(self, client):
        """POST /ot/attack/command-injection triggers unauthorized write and logs anomaly."""
        resp = client.post(
            "/ot/attack/command-injection",
            json={
                "rtu_id": 4,
                "register_address": 1,
                "value": 5000,
            },
        )
        assert resp.status_code == 200
        assert resp.json()["details"]["flagged_in_traffic_log"] is True

    def test_ot_fault_line_trip_endpoint(self, client):
        """POST /ot/fault/line-trip trips target line."""
        resp = client.post(
            "/ot/fault/line-trip",
            json={"line_index": 1},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "triggered"

    def test_ot_reset_endpoint(self, client):
        """POST /ot/reset clears all active attacks and restores grid."""
        resp = client.post("/ot/reset")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_ot_stop_endpoint(self, client):
        """POST /ot/stop cleanly stops the background simulation."""
        resp = client.post("/ot/stop")
        assert resp.status_code == 200
        assert resp.json()["status"] == "stopped"


class TestWebSocketLiveFeed:
    def test_websocket_live_stream_delivers_payload(self, client):
        """
        Verify that connecting to /ws/live receives valid simulation broadcast snapshots.
        """
        # Ensure a simulation tick has run so latest_state is populated
        client.post("/ot/start")

        try:
            with client.websocket_connect("/ws/live") as ws:
                data_str = ws.receive_text()
                payload = json.loads(data_str)

                assert "sim_time" in payload
                assert "true_physical_state" in payload
                assert "polled_modbus_telemetry" in payload
                assert "state_estimation" in payload
                assert "active_scenarios" in payload
        finally:
            client.post("/ot/stop")
