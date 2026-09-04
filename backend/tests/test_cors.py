"""Browser-equivalent CORS regression tests for the public frontend origins."""

import pytest
from fastapi.testclient import TestClient

from app.main import app


PRODUCTION_ORIGIN = "https://grid-sentinel-sepia.vercel.app"
CURRENT_PREVIEW_ORIGIN = "https://grid-sentinel-1m7wgpdwp-srisai-kedars-projects.vercel.app"
REJECTED_ORIGIN = "https://evil-example.com"

STATE_CHANGING_ENDPOINTS = (
    "/ot/start",
    "/ot/stop",
    "/feeder/tick",
    "/feeder/inject-bad-data",
    "/feeder/reset",
    "/ot/attack/data-injection",
    "/ot/attack/command-injection",
    "/ot/attack/replay",
    "/ot/fault/line-trip",
    "/ot/fault/short-circuit",
    "/ot/reset",
)


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.mark.parametrize("origin", [PRODUCTION_ORIGIN, CURRENT_PREVIEW_ORIGIN])
@pytest.mark.parametrize("endpoint", STATE_CHANGING_ENDPOINTS)
def test_post_preflight_allows_required_origins(client, origin, endpoint):
    response = client.options(
        endpoint,
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code in (200, 204)
    assert response.headers["access-control-allow-origin"] == origin
    assert "POST" in response.headers["access-control-allow-methods"]
    assert "content-type" in response.headers["access-control-allow-headers"].lower()


def test_preflight_rejects_untrusted_origin(client):
    response = client.options(
        "/ot/start",
        headers={
            "Origin": REJECTED_ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


@pytest.mark.parametrize("origin", [PRODUCTION_ORIGIN, CURRENT_PREVIEW_ORIGIN])
def test_state_changing_requests_return_cors_headers(client, origin):
    start_response = client.post("/ot/start", headers={"Origin": origin})
    assert start_response.status_code == 200
    assert start_response.headers["access-control-allow-origin"] == origin

    attack_response = client.post(
        "/ot/attack/data-injection",
        headers={"Origin": origin},
        json={"rtu_id": 2, "voltage_pu": 1.15, "duration_ticks": 1},
    )
    assert attack_response.status_code == 200
    assert attack_response.headers["access-control-allow-origin"] == origin

    client.post("/ot/stop", headers={"Origin": origin})
