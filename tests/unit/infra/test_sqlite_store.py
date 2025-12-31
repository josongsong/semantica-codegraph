"""
SQLite Store Tests

개인 랩탑용 SQLite storage 테스트.
"""

import asyncio
import tempfile
from pathlib import Path

import pytest

from codegraph_shared.infra.storage.sqlite import SQLiteStore


@pytest.fixture
def sqlite_store():
    """Create temporary SQLite store (sync fixture for async tests)."""
    import asyncio

    with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as f:
        db_path = Path(f.name)

    store = SQLiteStore(db_path=db_path)

    # Setup
    async def setup():
        await store.initialize()
        await store.execute("""
            CREATE TABLE IF NOT EXISTS test_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT
            )
        """)

    asyncio.run(setup())

    yield store

    # Teardown
    async def teardown():
        await store.close()

    asyncio.run(teardown())
    db_path.unlink()  # Delete temp file


@pytest.mark.asyncio
async def test_sqlite_insert_and_fetch(sqlite_store):
    """Test basic insert and fetch."""
    # Insert
    await sqlite_store.execute(
        "INSERT INTO test_users (name, email) VALUES (?, ?)",
        "Alice",
        "alice@example.com",
    )

    # Fetch
    rows = await sqlite_store.fetch("SELECT * FROM test_users")

    assert len(rows) == 1
    assert rows[0]["name"] == "Alice"
    assert rows[0]["email"] == "alice@example.com"


@pytest.mark.asyncio
async def test_sqlite_fetchrow(sqlite_store):
    """Test fetchrow."""
    await sqlite_store.execute(
        "INSERT INTO test_users (name, email) VALUES (?, ?)",
        "Bob",
        "bob@example.com",
    )

    row = await sqlite_store.fetchrow("SELECT * FROM test_users WHERE name = ?", "Bob")

    assert row is not None
    assert row["name"] == "Bob"


@pytest.mark.asyncio
async def test_sqlite_fetchval(sqlite_store):
    """Test fetchval."""
    await sqlite_store.execute(
        "INSERT INTO test_users (name, email) VALUES (?, ?)",
        "Charlie",
        "charlie@example.com",
    )

    count = await sqlite_store.fetchval("SELECT COUNT(*) FROM test_users")

    assert count == 1


@pytest.mark.asyncio
async def test_sqlite_health_check(sqlite_store):
    """Test health check."""
    is_healthy = await sqlite_store.health_check()

    assert is_healthy is True


@pytest.mark.asyncio
async def test_sqlite_context_manager():
    """Test context manager support."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as f:
        db_path = Path(f.name)

    async with SQLiteStore(db_path=db_path) as store:
        await store.execute("""
            CREATE TABLE test (id INTEGER PRIMARY KEY, name TEXT)
        """)

        await store.execute("INSERT INTO test (name) VALUES (?)", "test")

        rows = await store.fetch("SELECT * FROM test")
        assert len(rows) == 1

    db_path.unlink()


@pytest.mark.asyncio
async def test_sqlite_concurrent_queries():
    """Test concurrent queries (개인 랩탑 실사용 시나리오)."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as f:
        db_path = Path(f.name)

    store = SQLiteStore(db_path=db_path)
    await store.initialize()

    await store.execute("""
        CREATE TABLE test (id INTEGER PRIMARY KEY, value INTEGER)
    """)

    # 10 concurrent inserts
    async def insert_value(val):
        await store.execute("INSERT INTO test (value) VALUES (?)", val)

    await asyncio.gather(*[insert_value(i) for i in range(10)])

    # Check all inserted
    count = await store.fetchval("SELECT COUNT(*) FROM test")
    assert count == 10

    await store.close()
    db_path.unlink()


@pytest.mark.asyncio
async def test_sqlite_none_handling():
    """Test NULL value handling."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as f:
        db_path = Path(f.name)

    store = SQLiteStore(db_path=db_path)
    await store.initialize()

    await store.execute("""
        CREATE TABLE test (id INTEGER PRIMARY KEY, name TEXT)
    """)

    await store.execute("INSERT INTO test (name) VALUES (?)", None)

    row = await store.fetchrow("SELECT * FROM test")
    assert row["name"] is None

    await store.close()
    db_path.unlink()
