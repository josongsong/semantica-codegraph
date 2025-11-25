"""
API Server Tests

Simple smoke tests for FastAPI server endpoints.
"""

import pytest
from fastapi.testclient import TestClient

from server.api_server.main import app


@pytest.fixture
def client():
    """Create test client."""
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


# ==============================================================================
# Root and Health Endpoints
# ==============================================================================


def test_root_endpoint(client):
    """Test GET / returns service information."""
    response = client.get("/")

    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "Semantica CodeGraph API"
    assert data["version"] == "2.0.0"
    assert data["status"] == "online"
    assert "indexes" in data
    assert "endpoints" in data


def test_health_endpoint(client):
    """Test GET /health returns health status."""
    response = client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ["healthy", "ok"]  # Either is acceptable


# ==============================================================================
# Search Endpoints - Basic Validation
# ==============================================================================


def test_unified_search_missing_params(client):
    """Test unified search with missing required parameters."""
    response = client.get("/search/")

    assert response.status_code == 422  # Validation error


def test_unified_search_with_params(client):
    """Test unified search with valid parameters."""
    response = client.get(
        "/search/",
        params={
            "q": "test query",
            "repo_id": "test_repo",
        },
    )

    # Should succeed or fail gracefully (not 422)
    assert response.status_code in [200, 500, 503]


def test_lexical_search_validation(client):
    """Test lexical search parameter validation."""
    response = client.get("/search/lexical")

    assert response.status_code == 422  # Missing required params


def test_fuzzy_search_validation(client):
    """Test fuzzy search parameter validation."""
    response = client.get("/search/fuzzy")

    assert response.status_code == 422  # Missing required params


def test_domain_search_validation(client):
    """Test domain search parameter validation."""
    response = client.get("/search/domain")

    assert response.status_code == 422  # Missing required params


def test_invalid_limit_param(client):
    """Test search with invalid limit parameter."""
    response = client.get(
        "/search/",
        params={
            "q": "test",
            "repo_id": "test_repo",
            "limit": 999,  # Exceeds max limit of 200
        },
    )

    assert response.status_code == 422  # Validation error


def test_invalid_weight_param(client):
    """Test unified search with invalid weight parameter."""
    response = client.get(
        "/search/",
        params={
            "q": "test",
            "repo_id": "test_repo",
            "fuzzy_weight": 1.5,  # Exceeds max of 1.0
        },
    )

    assert response.status_code == 422  # Validation error


# ==============================================================================
# Indexing Endpoints - Validation
# ==============================================================================


def test_index_repo_missing_params(client):
    """Test POST /index/repo with missing parameters."""
    response = client.post("/index/repo", json={})

    assert response.status_code == 422  # Validation error


def test_incremental_index_missing_params(client):
    """Test POST /index/incremental with missing parameters."""
    response = client.post("/index/incremental", json={})

    assert response.status_code == 422  # Validation error


def test_index_health(client):
    """Test GET /index/health returns health status."""
    response = client.get("/index/health")

    assert response.status_code == 200
    data = response.json()
    # Should have indexes field
    assert "indexes" in data or "status" in data
