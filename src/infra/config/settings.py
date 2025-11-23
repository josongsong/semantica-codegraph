from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """애플리케이션 설정"""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Database
    database_url: str = "postgresql://codegraph:codegraph_dev@localhost:5432/codegraph"

    # Qdrant
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection_name: str = "codegraph"

    # Zoekt
    zoekt_url: str = "http://localhost:6070"

    # LiteLLM
    litellm_model: str = "gpt-4"
    litellm_api_key: str = ""

    # Application
    log_level: str = "INFO"
    chunk_size: int = 512
    chunk_overlap: int = 50


settings = Settings()
