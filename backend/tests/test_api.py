"""
test_api.py
-----------
Integration tests for all FastAPI endpoints using TestClient.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def client():
    """TestClient wraps the lifespan context manager automatically."""
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------

class TestHealthEndpoint:
    def test_health_returns_200(self, client):
        response = client.get("/health")
        assert response.status_code == 200

    def test_health_returns_ok(self, client):
        data = response = client.get("/health").json()
        assert data["status"] == "ok"

    def test_health_response_schema(self, client):
        data = client.get("/health").json()
        assert "status" in data


# ---------------------------------------------------------------------------
# GET /feeder/topology
# ---------------------------------------------------------------------------

class TestTopologyEndpoint:
    def test_topology_returns_200(self, client):
        response = client.get("/feeder/topology")
        assert response.status_code == 200

    def test_topology_has_buses_and_lines(self, client):
        data = client.get("/feeder/topology").json()
        assert "buses" in data
        assert "lines" in data

    def test_topology_bus_count(self, client):
        data = client.get("/feeder/topology").json()
        assert data["total_buses"] == 7

    def test_topology_line_count(self, client):
        data = client.get("/feeder/topology").json()
        assert data["total_lines"] == 5

    def test_topology_bus_has_coordinates(self, client):
        data = client.get("/feeder/topology").json()
        for bus in data["buses"]:
            assert "x" in bus
            assert "y" in bus

    def test_topology_bus_has_nominal_voltage(self, client):
        data = client.get("/feeder/topology").json()
        for bus in data["buses"]:
            assert "vn_kv" in bus
            assert bus["vn_kv"] in (11.0, 33.0)

    def test_topology_line_has_from_to_bus(self, client):
        data = client.get("/feeder/topology").json()
        for line in data["lines"]:
            assert "from_bus" in line
            assert "to_bus" in line
            assert line["from_bus"] != line["to_bus"]

    def test_topology_feeder_name(self, client):
        data = client.get("/feeder/topology").json()
        assert "feeder_name" in data
        assert len(data["feeder_name"]) > 0


# ---------------------------------------------------------------------------
# POST /feeder/tick
# ---------------------------------------------------------------------------

class TestTickEndpoint:
    def test_tick_returns_200(self, client):
        response = client.post("/feeder/tick")
        assert response.status_code == 200

    def test_tick_power_flow_converged(self, client):
        data = client.post("/feeder/tick").json()
        assert data["power_flow_converged"] is True

    def test_tick_has_bus_voltages(self, client):
        data = client.post("/feeder/tick").json()
        assert "bus_voltages" in data
        assert len(data["bus_voltages"]) == 7

    def test_tick_has_line_loadings(self, client):
        data = client.post("/feeder/tick").json()
        assert "line_loadings" in data
        assert len(data["line_loadings"]) == 5

    def test_tick_no_nan_voltages(self, client):
        data = client.post("/feeder/tick").json()
        for bv in data["bus_voltages"]:
            if bv["vm_pu"] is not None:
                assert bv["vm_pu"] == bv["vm_pu"], "NaN detected in vm_pu"

    def test_tick_state_estimation_success(self, client):
        data = client.post("/feeder/tick").json()
        assert data["state_estimation_success"] is True

    def test_tick_has_estimated_voltages(self, client):
        data = client.post("/feeder/tick").json()
        assert "estimated_voltages" in data
        assert len(data["estimated_voltages"]) > 0

    def test_tick_total_load_positive(self, client):
        data = client.post("/feeder/tick").json()
        assert data["total_load_mw"] > 0.0

    def test_tick_losses_non_negative(self, client):
        data = client.post("/feeder/tick").json()
        assert data["total_loss_mw"] >= 0.0

    def test_tick_schema_keys(self, client):
        data = client.post("/feeder/tick").json()
        for key in (
            "power_flow_converged", "bus_voltages", "line_loadings",
            "total_load_mw", "total_loss_mw", "state_estimation_success",
            "estimated_voltages", "chi2_test_passed", "chi2_statistic",
            "chi2_threshold",
        ):
            assert key in data, f"Missing key '{key}' in /feeder/tick response"


# ---------------------------------------------------------------------------
# POST /feeder/inject-bad-data
# ---------------------------------------------------------------------------

class TestInjectBadDataEndpoint:
    def _prime_tick(self, client):
        """Ensure the feeder has measurements seeded."""
        client.post("/feeder/tick")

    def test_inject_bad_data_returns_200(self, client):
        self._prime_tick(client)
        response = client.post(
            "/feeder/inject-bad-data",
            json={"measurement_index": 0, "magnitude_multiplier": 5.0},
        )
        assert response.status_code == 200

    def test_inject_bad_data_detects_anomaly(self, client):
        """A 5x injection must be flagged as ANOMALY_DETECTED."""
        client.post("/feeder/reset")
        client.post("/feeder/tick")
        data = client.post(
            "/feeder/inject-bad-data",
            json={"measurement_index": 0, "magnitude_multiplier": 5.0},
        ).json()
        assert data["bad_data_detected"] is True
        assert data["verdict"] == "ANOMALY_DETECTED"

    def test_inject_bad_data_schema_keys(self, client):
        client.post("/feeder/reset")
        client.post("/feeder/tick")
        data = client.post(
            "/feeder/inject-bad-data",
            json={"measurement_index": 0, "magnitude_multiplier": 5.0},
        ).json()
        for key in (
            "injected_measurement_index", "magnitude_multiplier",
            "bad_data_detected", "flagged_measurements", "chi2_test_passed",
            "chi2_statistic", "chi2_threshold", "lnr_threshold", "verdict",
        ):
            assert key in data, f"Missing key '{key}' in inject-bad-data response"

    def test_inject_bad_data_reflects_correct_index(self, client):
        client.post("/feeder/reset")
        client.post("/feeder/tick")
        data = client.post(
            "/feeder/inject-bad-data",
            json={"measurement_index": 2, "magnitude_multiplier": 5.0},
        ).json()
        assert data["injected_measurement_index"] == 2

    def test_inject_identity_multiplier_rejected(self, client):
        """magnitude_multiplier ~1.0 should be rejected by schema validator."""
        response = client.post(
            "/feeder/inject-bad-data",
            json={"measurement_index": 0, "magnitude_multiplier": 1.0},
        )
        assert response.status_code == 422

    def test_inject_invalid_index_rejected(self, client):
        """Measurement index 999 should return 422."""
        client.post("/feeder/reset")
        client.post("/feeder/tick")
        response = client.post(
            "/feeder/inject-bad-data",
            json={"measurement_index": 999, "magnitude_multiplier": 5.0},
        )
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# POST /feeder/reset
# ---------------------------------------------------------------------------

class TestResetEndpoint:
    def test_reset_returns_200(self, client):
        response = client.post("/feeder/reset")
        assert response.status_code == 200

    def test_reset_returns_ok_status(self, client):
        data = client.post("/feeder/reset").json()
        assert data["status"] == "ok"

    def test_reset_clears_bad_data(self, client):
        """After reset, a fresh tick should show clean chi2."""
        # Inject bad data
        client.post("/feeder/tick")
        client.post(
            "/feeder/inject-bad-data",
            json={"measurement_index": 0, "magnitude_multiplier": 10.0},
        )
        # Reset and re-tick
        client.post("/feeder/reset")
        tick_data = client.post("/feeder/tick").json()
        # After reset, state estimation should succeed on clean data
        assert tick_data["state_estimation_success"] is True

    def test_reset_schema(self, client):
        data = client.post("/feeder/reset").json()
        assert "status" in data
        assert "message" in data
