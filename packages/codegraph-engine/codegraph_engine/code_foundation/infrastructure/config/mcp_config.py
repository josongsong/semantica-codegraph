"""
MCP Service Layer Configuration (SOTA)

RFC-052: MCP Service Layer Architecture
Centralized configuration for MCP services.

Design Principles:
- No hardcoding in business logic
- Environment variable support
- Type-safe config (Pydantic)
- Defaults for dev/test/prod
"""

from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class MCPConfig(BaseSettings):
    """
    MCP Service Layer Configuration.

    Environment Variables:
    - MCP_DB_PATH: Database directory path
    - MCP_EVIDENCE_TTL_DAYS: Evidence TTL (default: 30)
    - MCP_SESSION_CLEANUP_DAYS: Session cleanup threshold (default: 7)
    - MCP_CONNECTION_POOL_SIZE: SQLite connection pool size (default: 5)
    - MCP_ENGINE_VERSION: QueryEngine version (default: "1.0.0")
    """

    model_config = SettingsConfigDict(
        env_prefix="MCP_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # Ignore extra fields
    )

    # Database
    db_path: Path = Field(
        default=Path.home() / ".codegraph" / "mcp",
        description="Database directory path",
    )

    connection_pool_size: int = Field(
        default=5,
        ge=1,
        le=20,
        description="SQLite connection pool size (max: 20)",
    )

    # Evidence
    evidence_ttl_days: int = Field(
        default=30,
        ge=1,
        le=365,
        description="Evidence TTL in days",
    )

    evidence_min_session_ttl_days: int = Field(
        default=7,
        ge=1,
        le=90,
        description="Minimum TTL after session end (debugging buffer)",
    )

    # Session
    session_cleanup_days: int = Field(
        default=7,
        ge=1,
        le=90,
        description="Session cleanup threshold in days",
    )

    # QueryEngine
    engine_version: str = Field(
        default="1.0.0",
        description="QueryEngine version for VerificationSnapshot",
    )

    ruleset_hash: str = Field(
        default="default",
        description="Taint/security ruleset hash",
    )

    # Budget Profiles
    budget_light_max_nodes: int = Field(default=100, ge=1)
    budget_light_max_depth: int = Field(default=5, ge=1)
    budget_light_timeout_ms: int = Field(default=5000, ge=100)

    budget_default_max_nodes: int = Field(default=1000, ge=1)
    budget_default_max_depth: int = Field(default=10, ge=1)
    budget_default_timeout_ms: int = Field(default=30000, ge=100)

    budget_heavy_max_nodes: int = Field(default=10000, ge=1)
    budget_heavy_max_depth: int = Field(default=20, ge=1)
    budget_heavy_timeout_ms: int = Field(default=120000, ge=100)

    # Monitoring
    enable_metrics: bool = Field(
        default=True,
        description="Enable prometheus metrics",
    )

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(
        default="INFO",
        description="Log level",
    )

    @property
    def evidence_db_path(self) -> Path:
        """Evidence database file path"""
        return self.db_path / "evidence.db"

    @property
    def session_db_path(self) -> Path:
        """Session database file path"""
        return self.db_path / "sessions.db"

    def ensure_dirs(self) -> None:
        """Ensure database directories exist"""
        self.db_path.mkdir(parents=True, exist_ok=True)

    def validate(self) -> list[str]:
        """
        Validate configuration (Production-ready).

        Returns:
            List of validation errors (empty if valid)
        """
        errors = []

        # Budget validation
        if self.budget_light_max_depth >= self.budget_default_max_depth:
            errors.append("budget_light_max_depth must be < budget_default_max_depth")

        if self.budget_default_max_depth >= self.budget_heavy_max_depth:
            errors.append("budget_default_max_depth must be < budget_heavy_max_depth")

        # TTL validation
        if self.evidence_min_session_ttl_days > self.evidence_ttl_days:
            errors.append("evidence_min_session_ttl_days must be <= evidence_ttl_days")

        # Pool size validation
        if self.connection_pool_size > 20:
            errors.append("connection_pool_size too high (max: 20 for SQLite)")

        return errors


# Singleton instance
_config: MCPConfig | None = None


def get_mcp_config() -> MCPConfig:
    """
    Get MCP configuration singleton.

    Returns:
        MCPConfig instance

    Raises:
        ValueError: If configuration is invalid
    """
    global _config
    if _config is None:
        try:
            _config = MCPConfig()
        except (PermissionError, OSError):
            # .env file access error - use defaults
            _config = MCPConfig.model_construct()  # Bypass validation for defaults

        # Validate configuration
        validation_errors = _config.validate()
        if validation_errors:
            raise ValueError(f"Invalid MCP configuration: {', '.join(validation_errors)}")

        try:
            _config.ensure_dirs()
        except (PermissionError, OSError) as e:
            # Can't create dirs - log warning but continue
            import logging

            logging.warning(f"mcp_config_dir_creation_failed: {e}")

    return _config


def reload_config() -> MCPConfig:
    """
    Reload configuration (for testing).

    Returns:
        Fresh MCPConfig instance
    """
    global _config
    _config = MCPConfig()
    _config.ensure_dirs()
    return _config
