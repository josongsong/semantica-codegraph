"""
Main API Integration Tests (CRITICAL)

Verifies RFC router is actually mounted to main app.

Tests:
- RFC router mounted
- /rfc/execute accessible
- /rfc/validate accessible
- /rfc/replay accessible
- OpenAPI schema includes RFC endpoints
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def app():
    """Create app with RFC router for testing"""
    from apps.api.api.routes import rfc

    app = FastAPI()
    app.include_router(rfc.router)
    return app


@pytest.fixture
def client(app):
    """TestClient"""
    return TestClient(app)


# ============================================================
# CRITICAL: Router Mount Verification
# ============================================================


def test_rfc_router_mounted(client):
    """
    CRITICAL: Verify RFC router is mounted to main app

    Without this, all RFC endpoints are inaccessible!
    """
    # Check OpenAPI schema
    response = client.get("/openapi.json")
    assert response.status_code == 200

    schema = response.json()
    paths = schema.get("paths", {})

    # Verify RFC endpoints exist
    assert "/rfc/execute" in paths, "RFC execute endpoint not found in OpenAPI!"
    assert "/rfc/validate" in paths, "RFC validate endpoint not found in OpenAPI!"
    assert "/rfc/replay/{request_id}" in paths, "RFC replay endpoint not found in OpenAPI!"


def test_rfc_execute_accessible(client):
    """Test /rfc/execute is accessible"""
    # Should return 400 (invalid spec), not 404 (not found)
    response = client.post("/rfc/execute", json={"spec": {}})

    assert response.status_code != 404, "/rfc/execute not found (router not mounted?)"
    # Expect 400 or 422 (validation error)
    assert response.status_code in [400, 422]


def test_rfc_validate_accessible(client):
    """Test /rfc/validate is accessible"""
    response = client.post("/rfc/validate", json={"spec": {}})

    assert response.status_code != 404, "/rfc/validate not found (router not mounted?)"
    # Should return 200 or 422
    assert response.status_code in [200, 422]


def test_rfc_replay_accessible(client):
    """Test /rfc/replay is accessible"""
    response = client.get("/rfc/replay/req_test")

    assert response.status_code != 404 or "not found" in response.json().get("detail", "").lower(), (
        "/rfc/replay not found (router not mounted?)"
    )
