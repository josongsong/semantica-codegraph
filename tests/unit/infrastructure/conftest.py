"""
Pytest configuration for infra tests.
"""

import os

import pytest

# Prevent .env file loading in tests
os.environ.setdefault("SEMANTICA_DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SEMANTICA_REDIS_HOST", "localhost")
os.environ.setdefault("SEMANTICA_QDRANT_HOST", "localhost")


@pytest.fixture
def mock_settings():
    """Mock settings for testing."""
    from codegraph_shared.infra.config.settings import Settings

    return Settings(
        database_url="sqlite:///:memory:",
        redis_host="localhost",
        redis_port=6379,
        qdrant_host="localhost",
        qdrant_port=6333,
    )
