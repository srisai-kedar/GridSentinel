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

    def test_ot_replay_attack_endpoint(self, client):
        """POST /ot/attack/replay accepts a target RTU and duration."""
        resp = client.post(
            "/ot/attack/replay",
            json={"rtu_id": 3, "duration_ticks": 10},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "injected"

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
        assert client.get("/classifier/status").json()["cached_rtu_count"] == 0

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
                payload = json.loads(ws.receive_text())
                # A just-started loop can explicitly report waiting before
                # its first fresh tick; consume that transition frame.
                if payload.get("stream_status") != "streaming":
                    payload = json.loads(ws.receive_text())

                assert "sim_time" in payload
                assert "true_physical_state" in payload
                assert "polled_modbus_telemetry" in payload
                assert "state_estimation" in payload
                assert "active_scenarios" in payload
                assert payload["stream_status"] == "streaming"
                assert len(payload["ml_verdicts"]) == 5
        finally:
            client.post("/ot/stop")

    def test_live_injection_is_classified_in_stream_without_manual_verdict_call(self, client):
        """A data injection tick is classified as an anomaly and propagated through the live stream.

        Taxonomy note: A silent data injection overrides RTU registers without generating Modbus
        write traffic. In heuristic fallback mode (no trained model), the 3-class taxonomy
        correctly classifies isolated high physics residuals with clean network as
        ``Sensor Malfunction``. With the trained model loaded, the physics–network disagreement
        pattern is recognised as ``Cyber Intrusion`` (FDI). Both verdicts set
        overall_status = ANOMALY_DETECTED, which is the key safety invariant.
        """
        client.post("/ot/reset")
        client.post("/ot/start")

        try:
            with client.websocket_connect("/ws/live") as ws:
                # Drain the explicit startup transition and wait for a fresh
                # streaming frame before applying the scenario.
                for _ in range(3):
                    payload = json.loads(ws.receive_text())
                    if payload.get("stream_status") == "streaming":
                        break

                response = client.post(
                    "/ot/attack/data-injection",
                    json={
                        "rtu_id": 2,
                        "voltage_pu": 0.70,
                        "p_mw": 0.20,
                        "q_mvar": 0.05,
                        "duration_ticks": 10,
                    },
                )
                assert response.status_code == 200

                # Acceptable verdicts for a silent data injection:
                # - "Cyber Intrusion" when the trained model is loaded (FDI pattern)
                # - "Sensor Malfunction" in heuristic fallback mode (isolated physics residual,
                #    clean Modbus network — correctly disambiguated from active cyber attack)
                ANOMALY_VERDICTS = {"Cyber Intrusion", "Sensor Malfunction"}

                detected = None
                for _ in range(8):
                    candidate = json.loads(ws.receive_text())
                    rtu2_verdict = candidate.get("ml_verdicts", {}).get("2", {})
                    if rtu2_verdict.get("verdict") in ANOMALY_VERDICTS:
                        detected = candidate
                        break

                assert detected is not None, "No anomaly frame received in 8 ticks"
                # The silent override must appear in active_scenarios
                assert detected["active_scenarios"]["silent_overrides"]["2"]["voltage_pu"] == 0.70
                # Overall status must be ANOMALY_DETECTED regardless of which class is triggered
                assert detected["overall_status"] == "ANOMALY_DETECTED"
        finally:
            client.post("/ot/reset")
            client.post("/ot/stop")

    def test_live_line_trip_remains_a_physical_disturbance(self, client):
        """A line trip changes true network state and exposes the model verdict."""
        client.post("/ot/reset")
        client.post("/ot/start")

        try:
            with client.websocket_connect("/ws/live") as ws:
                for _ in range(3):
                    payload = json.loads(ws.receive_text())
                    if payload.get("stream_status") == "streaming":
                        break

                response = client.post("/ot/fault/line-trip", json={"line_index": 0})
                assert response.status_code == 200

                fault_frame = None
                for _ in range(8):
                    candidate = json.loads(ws.receive_text())
                    line_zero = next(
                        (line for line in candidate["true_physical_state"]["line_loadings"] if line["line_index"] == 0),
                        None,
                    )
                    if line_zero is not None and (line_zero["loading_percent"] or 0) == 0:
                        fault_frame = candidate
                        break

                assert fault_frame is not None
                assert fault_frame["active_scenarios"]["tripped_lines"] == [0]
                assert fault_frame["ml_verdicts"]
                print("live_line_trip_verdicts=", {k: v["verdict"] for k, v in fault_frame["ml_verdicts"].items()})
        finally:
            client.post("/ot/reset")
            client.post("/ot/stop")
