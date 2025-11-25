"""
Semantica Codegraph Configuration

Centralized configuration management using pydantic-settings.
All environment variables should use SEMANTICA_ prefix.

Usage:
    from src.config import settings

    # Access settings
    db_url = settings.database_url
    qdrant_url = settings.qdrant_url
"""

from src.infra.config.settings import Settings, settings

__all__ = ["Settings", "settings"]
