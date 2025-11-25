"""
PostgreSQL Database Tests

Simple tests for PostgreSQL storage adapter.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.infra.storage.postgres import PostgresStore


class TestPostgresStoreBasics:
    """Test basic PostgresStore functionality."""

    def test_postgres_store_creation(self):
        """Test PostgresStore can be instantiated."""
        store = PostgresStore(
            connection_string="postgresql://test:test@localhost/test",
            min_pool_size=1,
            max_pool_size=5,
        )

        assert store is not None
        assert store.connection_string == "postgresql://test:test@localhost/test"
        assert store.min_pool_size == 1
        assert store.max_pool_size == 5

    def test_pool_not_initialized_by_default(self):
        """Test pool is not initialized on instantiation."""
        store = PostgresStore(connection_string="postgresql://test:test@localhost/test")

        assert store._pool is None

    def test_pool_property_raises_if_not_initialized(self):
        """Test pool property raises RuntimeError if not initialized."""
        store = PostgresStore(connection_string="postgresql://test:test@localhost/test")

        with pytest.raises(RuntimeError, match="PostgresStore pool not initialized"):
            _ = store.pool


class TestPostgresStoreInitialization:
    """Test PostgresStore initialization with mocks."""

    @pytest.mark.asyncio
    async def test_initialize_creates_pool(self):
        """Test initialize creates connection pool."""
        with patch("asyncpg.create_pool", new_callable=AsyncMock) as mock_create_pool:
            mock_pool = MagicMock()
            mock_create_pool.return_value = mock_pool

            store = PostgresStore(
                connection_string="postgresql://test:test@localhost/test",
                min_pool_size=2,
                max_pool_size=10,
            )

            await store.initialize()

            # Should create pool with correct parameters
            mock_create_pool.assert_called_once_with(
                "postgresql://test:test@localhost/test",
                min_size=2,
                max_size=10,
                command_timeout=60,
            )

            # Pool should be set
            assert store._pool is mock_pool

    @pytest.mark.asyncio
    async def test_initialize_idempotent(self):
        """Test initialize can be called multiple times safely."""
        with patch("asyncpg.create_pool", new_callable=AsyncMock) as mock_create_pool:
            mock_pool = MagicMock()
            mock_create_pool.return_value = mock_pool

            store = PostgresStore(connection_string="postgresql://test:test@localhost/test")

            await store.initialize()
            await store.initialize()  # Second call

            # Should only create pool once
            assert mock_create_pool.call_count == 1

    @pytest.mark.asyncio
    async def test_ensure_pool_lazy_initialization(self):
        """Test _ensure_pool performs lazy initialization."""
        with patch("asyncpg.create_pool", new_callable=AsyncMock) as mock_create_pool:
            mock_pool = MagicMock()
            mock_create_pool.return_value = mock_pool

            store = PostgresStore(connection_string="postgresql://test:test@localhost/test")

            pool = await store._ensure_pool()

            # Should create pool
            mock_create_pool.assert_called_once()
            assert pool is mock_pool


class TestPostgresStoreClose:
    """Test PostgresStore cleanup."""

    @pytest.mark.asyncio
    async def test_close_terminates_pool(self):
        """Test close terminates connection pool."""
        with patch("asyncpg.create_pool", new_callable=AsyncMock) as mock_create_pool:
            mock_pool = MagicMock()
            mock_pool.close = AsyncMock()
            mock_create_pool.return_value = mock_pool

            store = PostgresStore(connection_string="postgresql://test:test@localhost/test")
            await store.initialize()

            await store.close()

            # Should close pool
            mock_pool.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_without_pool(self):
        """Test close works even if pool not initialized."""
        store = PostgresStore(connection_string="postgresql://test:test@localhost/test")

        # Should not raise
        await store.close()


class TestPostgresStoreContextManager:
    """Test PostgresStore async context manager."""

    @pytest.mark.asyncio
    async def test_context_manager_usage(self):
        """Test async context manager initializes and closes."""
        with patch("asyncpg.create_pool", new_callable=AsyncMock) as mock_create_pool:
            mock_pool = MagicMock()
            mock_pool.close = AsyncMock()
            mock_create_pool.return_value = mock_pool

            store = PostgresStore(connection_string="postgresql://test:test@localhost/test")

            async with store as entered_store:
                # Should initialize and return self
                assert entered_store is store
                assert store._pool is mock_pool

            # Should close pool on exit
            mock_pool.close.assert_called_once()


class TestPostgresStoreConnectionString:
    """Test connection string handling."""

    def test_connection_string_formats(self):
        """Test various connection string formats are accepted."""
        # Standard format
        store1 = PostgresStore("postgresql://user:pass@localhost:5432/dbname")
        assert store1.connection_string == "postgresql://user:pass@localhost:5432/dbname"

        # With SSL
        store2 = PostgresStore("postgresql://user:pass@localhost/dbname?sslmode=require")
        assert "sslmode=require" in store2.connection_string

        # Minimal
        store3 = PostgresStore("postgresql://localhost/test")
        assert store3.connection_string == "postgresql://localhost/test"


class TestPostgresStorePoolConfiguration:
    """Test pool size configuration."""

    def test_custom_pool_sizes(self):
        """Test custom pool sizes are stored."""
        store = PostgresStore(
            connection_string="postgresql://localhost/test",
            min_pool_size=5,
            max_pool_size=20,
        )

        assert store.min_pool_size == 5
        assert store.max_pool_size == 20

    def test_default_pool_sizes(self):
        """Test default pool sizes."""
        store = PostgresStore(connection_string="postgresql://localhost/test")

        assert store.min_pool_size == 2
        assert store.max_pool_size == 10
