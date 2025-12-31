"""
Auto-detect Storage Backend

개인 랩탑 환경 고려:
1. PostgreSQL 있으면 → PostgreSQL 사용
2. 없으면 → SQLite 자동 fallback (설치 불필요!)

Zero configuration for personal laptop use.
"""

import os
from typing import TYPE_CHECKING, Union

from codegraph_shared.common.observability import get_logger

if TYPE_CHECKING:
    from codegraph_shared.infra.storage.postgres import PostgresStore
    from codegraph_shared.infra.storage.sqlite import SQLiteStore

logger = get_logger(__name__)


def create_auto_store() -> Union["PostgresStore", "SQLiteStore"]:
    """
    Auto-detect and create appropriate storage backend.

    Detection order:
    1. Check DATABASE_URL env var
    2. Try PostgreSQL connection
    3. Fallback to SQLite

    Returns:
        PostgresStore or SQLiteStore
    """
    # Check env var
    database_url = os.getenv("SEMANTICA_DATABASE_URL") or os.getenv("DATABASE_URL")

    if database_url and database_url.startswith("sqlite"):
        # Explicit SQLite
        from codegraph_shared.infra.storage.sqlite import SQLiteStore

        db_path = database_url.replace("sqlite:///", "")
        logger.info(f"Using SQLite (explicit): {db_path}")
        return SQLiteStore(db_path=db_path)

    if database_url and database_url.startswith("postgres"):
        # Explicit PostgreSQL
        try:
            from codegraph_shared.infra.storage.postgres import PostgresStore

            logger.info("Using PostgreSQL (explicit)")
            return PostgresStore(connection_string=database_url)
        except Exception as e:
            logger.warning(f"PostgreSQL connection failed: {e}")
            logger.info("Falling back to SQLite...")

    # Auto-detect: Try PostgreSQL first
    if database_url:
        try:
            import asyncio

            # Quick connection test
            import asyncpg

            from codegraph_shared.infra.storage.postgres import PostgresStore

            async def test_postgres():
                try:
                    conn = await asyncpg.connect(database_url, timeout=2.0)
                    await conn.close()
                    return True
                except Exception:
                    return False

            is_available = asyncio.run(test_postgres())

            if is_available:
                logger.info("Using PostgreSQL (auto-detected)")
                return PostgresStore(connection_string=database_url)
        except Exception as e:
            logger.debug(f"PostgreSQL not available: {e}")

    # Fallback to SQLite (always works)
    from codegraph_shared.infra.storage.sqlite import SQLiteStore

    logger.info("Using SQLite (fallback - no PostgreSQL found)")
    logger.info("  ✅ Zero configuration")
    logger.info("  ✅ No installation needed")
    logger.info("  ✅ File-based: data/codegraph.db")

    return SQLiteStore(db_path="data/codegraph.db")


# Convenience alias
AutoStore = create_auto_store
