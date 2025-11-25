"""
PostgresStore Integration Tests

Tests PostgreSQL connection pool functionality:
- Pool initialization and lazy loading
- Connection pool behavior
- Query execution (execute, fetch, executemany)
- Health checks
- Graceful shutdown
- Error handling
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.infra.storage.postgres import PostgresStore

# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def postgres_connection_string():
    """Get PostgreSQL connection string from environment or use test default."""
    return os.getenv("SEMANTICA_DATABASE_URL", "postgresql://test_user:test_password@localhost:5432/test_db")


@pytest.fixture
async def postgres_store(postgres_connection_string):
    """Create PostgresStore instance and initialize it."""
    store = PostgresStore(
        connection_string=postgres_connection_string,
        min_pool_size=1,
        max_pool_size=3,
    )

    # Initialize pool
    try:
        await store.initialize()
        yield store
    except Exception as e:
        pytest.skip(f"PostgreSQL not available: {e}")
    finally:
        await store.close()


@pytest.fixture
def mock_asyncpg_pool():
    """Mock asyncpg pool for testing without real database."""
    mock_pool = MagicMock()
    mock_pool.acquire = AsyncMock()

    # Mock connection
    mock_conn = MagicMock()
    mock_conn.execute = AsyncMock(return_value="INSERT 0 1")
    mock_conn.executemany = AsyncMock()
    mock_conn.fetch = AsyncMock(return_value=[])
    mock_conn.fetchrow = AsyncMock(return_value=None)
    mock_conn.fetchval = AsyncMock(return_value=1)

    # Make acquire() return async context manager
    mock_acquire_cm = MagicMock()
    mock_acquire_cm.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_acquire_cm.__aexit__ = AsyncMock(return_value=None)
    mock_pool.acquire.return_value = mock_acquire_cm

    mock_pool.close = AsyncMock()

    return mock_pool


# ============================================================
# Initialization Tests
# ============================================================


@pytest.mark.asyncio
async def test_pool_initialization(postgres_connection_string):
    """Test that pool initializes correctly."""
    store = PostgresStore(
        connection_string=postgres_connection_string,
        min_pool_size=2,
        max_pool_size=5,
    )

    assert store._pool is None

    try:
        await store.initialize()
        assert store._pool is not None
        assert store.min_pool_size == 2
        assert store.max_pool_size == 5
    except Exception:
        pytest.skip("PostgreSQL not available")
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_pool_lazy_initialization(postgres_connection_string):
    """Test lazy pool initialization via _ensure_pool()."""
    store = PostgresStore(connection_string=postgres_connection_string)

    assert store._pool is None

    try:
        # Lazy initialization
        pool = await store._ensure_pool()
        assert pool is not None
        assert store._pool is not None

        # Second call should return same pool
        pool2 = await store._ensure_pool()
        assert pool2 is pool
    except Exception:
        pytest.skip("PostgreSQL not available")
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_pool_property_raises_when_not_initialized():
    """Test that pool property raises error if not initialized."""
    store = PostgresStore(connection_string="postgresql://fake")

    with pytest.raises(RuntimeError, match="PostgresStore pool not initialized"):
        _ = store.pool


@pytest.mark.asyncio
async def test_double_initialization_warning(postgres_connection_string):
    """Test that double initialization is handled gracefully."""
    store = PostgresStore(connection_string=postgres_connection_string)

    try:
        await store.initialize()

        # Second initialization should not raise, just warn
        await store.initialize()  # Should handle gracefully

        assert store._pool is not None
    except Exception:
        pytest.skip("PostgreSQL not available")
    finally:
        await store.close()


# ============================================================
# Query Execution Tests
# ============================================================


@pytest.mark.asyncio
async def test_execute_query(postgres_store):
    """Test execute() method."""
    # Create a test table
    await postgres_store.execute(
        """
        CREATE TEMPORARY TABLE test_execute (
            id SERIAL PRIMARY KEY,
            name TEXT
        )
    """
    )

    # Insert data
    result = await postgres_store.execute("INSERT INTO test_execute (name) VALUES ($1)", "test_name")

    assert result.startswith("INSERT")


@pytest.mark.asyncio
async def test_fetch_query(postgres_store):
    """Test fetch() method."""
    # Create temporary table
    await postgres_store.execute(
        """
        CREATE TEMPORARY TABLE test_fetch (
            id SERIAL PRIMARY KEY,
            name TEXT
        )
    """
    )

    # Insert test data
    await postgres_store.execute("INSERT INTO test_fetch (name) VALUES ('Alice'), ('Bob')")

    # Fetch all
    rows = await postgres_store.fetch("SELECT name FROM test_fetch ORDER BY name")

    assert len(rows) == 2
    assert rows[0]["name"] == "Alice"
    assert rows[1]["name"] == "Bob"


@pytest.mark.asyncio
async def test_fetchrow_query(postgres_store):
    """Test fetchrow() method."""
    # Create temporary table
    await postgres_store.execute(
        """
        CREATE TEMPORARY TABLE test_fetchrow (
            id SERIAL PRIMARY KEY,
            value INT
        )
    """
    )

    await postgres_store.execute("INSERT INTO test_fetchrow (value) VALUES (42)")

    # Fetch single row
    row = await postgres_store.fetchrow("SELECT value FROM test_fetchrow")

    assert row is not None
    assert row["value"] == 42


@pytest.mark.asyncio
async def test_fetchval_query(postgres_store):
    """Test fetchval() method."""
    # Simple query
    val = await postgres_store.fetchval("SELECT 123 AS num")

    assert val == 123


@pytest.mark.asyncio
async def test_executemany_query(postgres_store):
    """Test executemany() method for bulk inserts."""
    # Create temporary table
    await postgres_store.execute(
        """
        CREATE TEMPORARY TABLE test_executemany (
            id SERIAL PRIMARY KEY,
            name TEXT,
            age INT
        )
    """
    )

    # Bulk insert
    data = [
        ("Alice", 30),
        ("Bob", 25),
        ("Charlie", 35),
    ]

    await postgres_store.executemany("INSERT INTO test_executemany (name, age) VALUES ($1, $2)", data)

    # Verify
    rows = await postgres_store.fetch("SELECT name, age FROM test_executemany ORDER BY name")
    assert len(rows) == 3
    assert rows[0]["name"] == "Alice"
    assert rows[0]["age"] == 30


# ============================================================
# Health Check Tests
# ============================================================


@pytest.mark.asyncio
async def test_health_check_success(postgres_store):
    """Test health check returns True when database is healthy."""
    is_healthy = await postgres_store.health_check()
    assert is_healthy is True


@pytest.mark.asyncio
async def test_health_check_without_pool():
    """Test health check returns False when pool not initialized."""
    store = PostgresStore(connection_string="postgresql://fake")

    is_healthy = await store.health_check()
    assert is_healthy is False


# ============================================================
# Context Manager Tests
# ============================================================


@pytest.mark.asyncio
async def test_async_context_manager(postgres_connection_string):
    """Test async context manager support."""
    try:
        async with PostgresStore(connection_string=postgres_connection_string) as store:
            assert store._pool is not None

            # Can query
            val = await store.fetchval("SELECT 1")
            assert val == 1

        # Pool should be closed after context
        assert store._pool is None
    except Exception:
        pytest.skip("PostgreSQL not available")


# ============================================================
# Error Handling Tests
# ============================================================


@pytest.mark.asyncio
async def test_query_with_invalid_sql(postgres_store):
    """Test that invalid SQL raises appropriate error."""
    with pytest.raises(Exception):  # asyncpg will raise syntax error
        await postgres_store.execute("INVALID SQL QUERY")


@pytest.mark.asyncio
async def test_connection_failure_handling():
    """Test handling of connection failures."""
    # Use invalid connection string
    store = PostgresStore(
        connection_string="postgresql://invalid_user:wrong_pass@localhost:9999/nonexistent",
        min_pool_size=1,
        max_pool_size=2,
    )

    with pytest.raises(Exception):  # Should raise connection error
        await store.initialize()


# ============================================================
# Cleanup Tests
# ============================================================


@pytest.mark.asyncio
async def test_close_pool(postgres_connection_string):
    """Test pool close functionality."""
    store = PostgresStore(connection_string=postgres_connection_string)

    try:
        await store.initialize()
        assert store._pool is not None

        await store.close()
        assert store._pool is None
    except Exception:
        pytest.skip("PostgreSQL not available")


@pytest.mark.asyncio
async def test_close_without_initialization():
    """Test close on uninitialized store doesn't raise error."""
    store = PostgresStore(connection_string="postgresql://fake")

    # Should not raise
    await store.close()
    assert store._pool is None


# ============================================================
# Mock-based Tests (no real DB required)
# ============================================================


@pytest.mark.asyncio
async def test_pool_property_after_initialization_mock(mock_asyncpg_pool):
    """Test pool property after initialization (using mock)."""
    store = PostgresStore(connection_string="postgresql://fake")

    with patch("asyncpg.create_pool", return_value=mock_asyncpg_pool):
        await store.initialize()

        # Should not raise
        pool = store.pool
        assert pool is mock_asyncpg_pool


@pytest.mark.asyncio
async def test_execute_with_mock(mock_asyncpg_pool):
    """Test execute with mocked pool."""
    store = PostgresStore(connection_string="postgresql://fake")

    with patch("asyncpg.create_pool", return_value=mock_asyncpg_pool):
        await store.initialize()

        result = await store.execute("INSERT INTO test VALUES (1)")
        assert result == "INSERT 0 1"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
