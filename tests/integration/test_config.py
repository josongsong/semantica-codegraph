"""
Config Settings Tests

Tests for application configuration and settings.
"""

import os
from unittest.mock import patch

from codegraph_shared.infra.config.settings import Settings


class TestSettingsBasics:
    """Test basic settings functionality."""

    def test_settings_creation(self):
        """Test settings can be instantiated."""
        settings = Settings()
        assert settings is not None

    def test_settings_is_pydantic_model(self):
        """Test settings is a Pydantic model."""
        settings = Settings()
        assert hasattr(settings, "model_dump")
        assert hasattr(settings, "model_validate")

    def test_module_level_singleton(self):
        """Test module-level settings is instantiated."""
        from codegraph_shared.infra.config.settings import settings as settings1
        from codegraph_shared.infra.config.settings import settings as settings2

        assert settings1 is settings2


class TestDefaultValues:
    """Test default configuration values."""

    def test_database_defaults(self):
        """Test database default values."""
        settings = Settings()

        assert settings.database_url == "postgresql://codegraph:codegraph_dev@localhost:5432/codegraph"
        assert settings.postgres_min_pool_size == 2
        assert settings.postgres_max_pool_size == 10

    def test_qdrant_defaults(self):
        """Test Qdrant default values."""
        settings = Settings()

        assert settings.qdrant_url == "http://localhost:6333"
        assert settings.qdrant_collection_name == "codegraph"
        assert settings.qdrant_vector_size == 1536

    def test_zoekt_defaults(self):
        """Test Zoekt default values."""
        settings = Settings()

        assert settings.zoekt_host == "localhost"
        assert settings.zoekt_port == 6070
        assert settings.zoekt_repos_root == "./repos"

    def test_kuzu_defaults(self):
        """Test Kuzu default values."""
        settings = Settings()

        assert settings.kuzu_db_path == "./data/kuzu"
        assert settings.kuzu_buffer_pool_size == 1024 * 1024 * 1024  # 1GB

    def test_redis_defaults(self):
        """Test Redis default values."""
        settings = Settings()

        assert settings.redis_host == "localhost"
        assert settings.redis_port == 6379
        assert settings.redis_db == 0
        assert settings.redis_password is None

    def test_llm_defaults(self):
        """Test LLM default values."""
        settings = Settings()

        assert settings.litellm_model == "gpt-4"
        assert settings.embedding_model == "text-embedding-3-small"
        assert settings.embedding_dimension == 1536

    def test_search_weight_defaults(self):
        """Test search weight default values."""
        settings = Settings()

        assert settings.search_weight_lexical == 0.3
        assert settings.search_weight_vector == 0.3
        assert settings.search_weight_symbol == 0.2
        assert settings.search_weight_fuzzy == 0.1
        assert settings.search_weight_domain == 0.1

    def test_application_defaults(self):
        """Test application default values."""
        settings = Settings()

        assert settings.log_level == "INFO"
        assert settings.chunk_size == 512
        assert settings.chunk_overlap == 50

    def test_api_server_defaults(self):
        """Test API server default values."""
        settings = Settings()

        assert settings.api_host == "0.0.0.0"
        assert settings.api_port == 8000
        assert isinstance(settings.cors_origins, list)
        assert "http://localhost:3000" in settings.cors_origins


class TestEnvironmentVariables:
    """Test environment variable loading."""

    def test_env_prefix(self):
        """Test SEMANTICA_ prefix is used."""
        with patch.dict(os.environ, {"SEMANTICA_DATABASE_URL": "postgresql://test:test@test:5432/test"}):
            settings = Settings()
            assert settings.database_url == "postgresql://test:test@test:5432/test"

    def test_env_override_database_url(self):
        """Test environment variable overrides database_url."""
        custom_url = "postgresql://custom:custom@custom:5432/custom"

        with patch.dict(os.environ, {"SEMANTICA_DATABASE_URL": custom_url}):
            settings = Settings()
            assert settings.database_url == custom_url

    def test_env_override_qdrant_url(self):
        """Test environment variable overrides qdrant_url."""
        with patch.dict(os.environ, {"SEMANTICA_QDRANT_URL": "http://qdrant:6333"}):
            settings = Settings()
            assert settings.qdrant_url == "http://qdrant:6333"

    def test_env_override_api_port(self):
        """Test environment variable overrides api_port."""
        with patch.dict(os.environ, {"SEMANTICA_API_PORT": "9000"}):
            settings = Settings()
            assert settings.api_port == 9000

    def test_env_override_log_level(self):
        """Test environment variable overrides log_level."""
        with patch.dict(os.environ, {"SEMANTICA_LOG_LEVEL": "DEBUG"}):
            settings = Settings()
            assert settings.log_level == "DEBUG"

    def test_multiple_env_overrides(self):
        """Test multiple environment variables at once."""
        env_vars = {
            "SEMANTICA_DATABASE_URL": "postgresql://multi:multi@multi:5432/multi",
            "SEMANTICA_API_PORT": "8080",
            "SEMANTICA_LOG_LEVEL": "WARNING",
        }

        with patch.dict(os.environ, env_vars):
            settings = Settings()
            assert settings.database_url == "postgresql://multi:multi@multi:5432/multi"
            assert settings.api_port == 8080
            assert settings.log_level == "WARNING"


class TestTypeValidation:
    """Test Pydantic type validation."""

    def test_port_must_be_int(self):
        """Test port must be integer."""
        # Pydantic will coerce string to int
        with patch.dict(os.environ, {"SEMANTICA_API_PORT": "8000"}):
            settings = Settings()
            assert isinstance(settings.api_port, int)
            assert settings.api_port == 8000

    def test_pool_size_must_be_int(self):
        """Test pool size must be integer."""
        with patch.dict(os.environ, {"SEMANTICA_POSTGRES_MAX_POOL_SIZE": "20"}):
            settings = Settings()
            assert isinstance(settings.postgres_max_pool_size, int)
            assert settings.postgres_max_pool_size == 20

    def test_weight_must_be_float(self):
        """Test search weight must be float."""
        with patch.dict(os.environ, {"SEMANTICA_SEARCH_WEIGHT_LEXICAL": "0.5"}):
            settings = Settings()
            assert isinstance(settings.search_weight_lexical, float)
            assert settings.search_weight_lexical == 0.5


class TestCorsFunctionality:
    """Test CORS origins configuration."""

    def test_cors_origins_is_list(self):
        """Test cors_origins is a list."""
        settings = Settings()
        assert isinstance(settings.cors_origins, list)

    def test_cors_origins_contains_strings(self):
        """Test cors_origins contains strings."""
        settings = Settings()
        for origin in settings.cors_origins:
            assert isinstance(origin, str)

    def test_cors_origins_from_env(self):
        """Test cors_origins can be set from environment."""
        # Pydantic list from JSON string
        with patch.dict(os.environ, {"SEMANTICA_CORS_ORIGINS": '["http://example.com", "http://test.com"]'}):
            settings = Settings()
            assert "http://example.com" in settings.cors_origins
            assert "http://test.com" in settings.cors_origins


class TestOptionalValues:
    """Test optional configuration values."""

    def test_redis_password_can_be_none(self):
        """Test redis_password can be None."""
        settings = Settings()
        assert settings.redis_password is None

    def test_redis_password_from_env(self):
        """Test redis_password can be set from environment."""
        with patch.dict(os.environ, {"SEMANTICA_REDIS_PASSWORD": "secret123"}):
            settings = Settings()
            assert settings.redis_password == "secret123"

    def test_api_keys_default_empty(self):
        """Test API keys default to empty string."""
        settings = Settings()
        # These may be empty by default
        assert isinstance(settings.litellm_api_key, str)
        assert isinstance(settings.openai_api_key, str)


class TestModelDump:
    """Test settings serialization."""

    def test_model_dump_returns_dict(self):
        """Test model_dump returns dictionary."""
        settings = Settings()
        config_dict = settings.model_dump()

        assert isinstance(config_dict, dict)
        assert "database_url" in config_dict
        assert "qdrant_url" in config_dict

    def test_model_dump_includes_all_fields(self):
        """Test model_dump includes all configuration fields."""
        settings = Settings()
        config_dict = settings.model_dump()

        # Check some key fields
        required_fields = [
            "database_url",
            "qdrant_url",
            "zoekt_host",
            "kuzu_db_path",
            "redis_host",
            "api_host",
            "api_port",
        ]

        for field in required_fields:
            assert field in config_dict
