"""
Global Configuration

Application settings using Pydantic Settings.
Loads configuration from environment variables and .env files.
"""


from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings.

    All settings can be overridden via environment variables.
    Example: SEMANTICA_VECTOR_HOST=localhost
    """

    model_config = SettingsConfigDict(
        env_prefix="SEMANTICA_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Vector Store Settings (Qdrant)
    vector_host: str = "localhost"
    vector_port: int = 6333
    vector_collection: str = "codegraph"

    # Database Settings (PostgreSQL)
    db_connection_string: str = "postgresql://user:pass@localhost:5432/codegraph"

    # Redis Settings (Session, Cache, Collaboration)
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_password: str | None = None
    redis_db: int = 0

    # Lexical Search Settings (Zoekt)
    zoekt_host: str = "http://localhost"
    zoekt_port: int = 6070

    # Graph Store Settings (Kùzu)
    kuzu_db_path: str = "./data/kuzu"
    kuzu_buffer_pool_size: int = 1024  # MB

    # LLM Settings
    openai_api_key: str | None = None
    embedding_model: str = "text-embedding-3-small"
    embedding_dimension: int = 1536

    # Application Settings
    log_level: str = "INFO"
    environment: str = "development"

    # API Settings
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_reload: bool = True


# Global settings instance
settings = Settings()
