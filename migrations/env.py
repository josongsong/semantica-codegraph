"""Alembic environment configuration.

This setup reads the DB URL from `SEMANTICA_DB_CONNECTION_STRING` (via core.config.Settings)
and supports both offline and online migrations. Autogenerate is available once SQLAlchemy
models are wired; until then, write migration scripts manually in migrations/versions/.
"""

from __future__ import annotations

import asyncio
import sys
from logging.config import fileConfig
from typing import Any, Dict

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# Ensure project root is on sys.path so we can import core.config
sys.path.append(".")

from core.config import Settings  # noqa: E402

# Alembic Config object, provides access to the .ini file
config = context.config

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

settings = Settings()

# Allow overriding DB URL via `-x db_url=...`
x_args: Dict[str, Any] = context.get_x_argument(as_dictionary=True)
db_url: str = x_args.get("db_url") or settings.db_connection_string
config.set_main_option("sqlalchemy.url", db_url)

# TODO: set metadata when SQLAlchemy models are introduced
target_metadata = None


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    context.configure(
        url=db_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode with async engine."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async def do_run_migrations() -> None:
        async with connectable.connect() as connection:
            await connection.run_sync(_run_sync_migrations)
        await connectable.dispose()

    def _run_sync_migrations(connection: Connection) -> None:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()

    asyncio.run(do_run_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
