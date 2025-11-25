from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Semantica Codegraph Application Settings

    Environment variables should use SEMANTICA_ prefix.
    Example: SEMANTICA_DATABASE_URL, SEMANTICA_QDRANT_URL
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="SEMANTICA_",
    )

    # ========================================================================
    # Database (PostgreSQL)
    # ========================================================================
    database_url: str = "postgresql://codegraph:codegraph_dev@localhost:5432/codegraph"
    postgres_min_pool_size: int = 2
    postgres_max_pool_size: int = 10

    # ========================================================================
    # Vector Search (Qdrant)
    # ========================================================================
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection_name: str = "codegraph"
    qdrant_vector_size: int = 1536  # OpenAI embedding dimension

    # ========================================================================
    # Lexical Search (Zoekt)
    # ========================================================================
    zoekt_host: str = "localhost"
    zoekt_port: int = 6070
    zoekt_url: str = "http://localhost:6070"
    zoekt_repos_root: str = "./repos"
    zoekt_index_cmd: str = "zoekt-index"

    # ========================================================================
    # Graph Database (Kuzu)
    # ========================================================================
    kuzu_db_path: str = "./data/kuzu"
    kuzu_buffer_pool_size: int = 1024 * 1024 * 1024  # 1GB

    # ========================================================================
    # Cache (Redis)
    # ========================================================================
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: str | None = None

    # ========================================================================
    # LLM (OpenAI / LiteLLM)
    # ========================================================================
    litellm_model: str = "gpt-4"
    litellm_api_key: str = ""
    openai_api_key: str = ""
    embedding_model: str = "text-embedding-3-small"
    embedding_dimension: int = 1536

    # ========================================================================
    # Search Weights
    # ========================================================================
    search_weight_lexical: float = 0.3
    search_weight_vector: float = 0.3
    search_weight_symbol: float = 0.2
    search_weight_fuzzy: float = 0.1
    search_weight_domain: float = 0.1
    search_weight_runtime: float = 0.0  # Phase 3

    # ========================================================================
    # Application
    # ========================================================================
    log_level: str = "INFO"
    chunk_size: int = 512
    chunk_overlap: int = 50
    repos_base_path: str = "./repos"
    index_batch_size: int = 100
    vector_batch_size: int = 50


# Eager loading (module-level instantiation)
settings = Settings()
