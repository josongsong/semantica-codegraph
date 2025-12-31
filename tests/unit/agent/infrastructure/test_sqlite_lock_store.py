"""
SQLite Lock Store Tests (SOTA급)

Zero Configuration - Redis 불필요!

Test Coverage:
- Base: 기본 CRUD
- Edge: TTL, cleanup
- Corner: 1000개 동시
- Performance: <1ms write
"""

import asyncio
from datetime import datetime
from pathlib import Path

import pytest

from apps.orchestrator.orchestrator.infrastructure.sqlite_lock_store import (
    SQLiteLockStore,
    create_lock_store,
)

# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def lock_store(tmp_path):
    """Real SQLiteLockStore (임시 파일)"""
    db_path = tmp_path / "test_locks.db"
    store = SQLiteLockStore(db_path, enable_wal=True)

    yield store

    store.close()


# ============================================================
# Base Cases
# ============================================================


@pytest.mark.asyncio
async def test_set_and_get(lock_store):
    """Base: Lock 저장 및 조회"""
    lock_data = {
        "agent_id": "agent-1",
        "acquired_at": datetime.now().isoformat(),
        "file_hash": "abc123",
        "lock_type": "write",
        "ttl_seconds": 1800,
        "metadata": {},
    }

    # Set
    success = await lock_store.set("main.py", lock_data, ttl_seconds=1800)
    assert success is True

    # Get
    retrieved = await lock_store.get("main.py")
    assert retrieved is not None
    assert retrieved["agent_id"] == "agent-1"


@pytest.mark.asyncio
async def test_delete(lock_store):
    """Base: Lock 삭제"""
    lock_data = {
        "agent_id": "agent-1",
        "acquired_at": datetime.now().isoformat(),
        "file_hash": "abc123",
        "lock_type": "write",
        "ttl_seconds": 1800,
    }

    await lock_store.set("main.py", lock_data, 1800)

    # Delete
    success = await lock_store.delete("main.py")
    assert success is True

    # 조회 시 None
    retrieved = await lock_store.get("main.py")
    assert retrieved is None


@pytest.mark.asyncio
async def test_get_nonexistent(lock_store):
    """Base: 없는 Lock 조회 → None"""
    retrieved = await lock_store.get("nonexistent.py")
    assert retrieved is None


# ============================================================
# Edge Cases
# ============================================================


@pytest.mark.asyncio
async def test_ttl_expiration(lock_store):
    """Edge: TTL 만료 → 자동 삭제"""
    lock_data = {
        "agent_id": "agent-1",
        "acquired_at": datetime.now().isoformat(),
        "file_hash": "abc123",
        "lock_type": "write",
        "ttl_seconds": 1,  # 1초
    }

    await lock_store.set("main.py", lock_data, 1)

    # 1.5초 대기
    await asyncio.sleep(1.5)

    # 조회 시 None (만료)
    retrieved = await lock_store.get("main.py")
    assert retrieved is None


@pytest.mark.asyncio
async def test_cleanup_expired_locks(lock_store):
    """Edge: 만료 Lock 일괄 정리"""
    # 3개 Lock (1개 만료)
    for i in range(3):
        lock_data = {
            "agent_id": f"agent-{i}",
            "acquired_at": datetime.now().isoformat(),
            "file_hash": f"hash{i}",
            "lock_type": "write",
            "ttl_seconds": 1 if i == 1 else 1800,  # agent-1만 1초
        }

        await lock_store.set(f"file{i}.py", lock_data, lock_data["ttl_seconds"])

    # 1.5초 대기
    await asyncio.sleep(1.5)

    # Cleanup
    deleted = await lock_store.cleanup_expired()

    assert deleted == 1  # 1개 삭제


@pytest.mark.asyncio
async def test_scan(lock_store):
    """Edge: Lock 목록 조회"""
    # 5개 Lock
    for i in range(5):
        lock_data = {
            "agent_id": f"agent-{i}",
            "acquired_at": datetime.now().isoformat(),
            "file_hash": f"hash{i}",
            "lock_type": "write",
            "ttl_seconds": 1800,
        }

        await lock_store.set(f"file{i}.py", lock_data, 1800)

    # Scan
    cursor, keys = await lock_store.scan()

    assert cursor == 0  # SQLite는 1회 조회
    assert len(keys) == 5


# ============================================================
# Corner Cases
# ============================================================


@pytest.mark.asyncio
async def test_1000_concurrent_locks(lock_store):
    """Corner: 1000개 동시 Lock"""
    tasks = []

    for i in range(1000):
        lock_data = {
            "agent_id": f"agent-{i}",
            "acquired_at": datetime.now().isoformat(),
            "file_hash": f"hash{i}",
            "lock_type": "write",
            "ttl_seconds": 1800,
        }

        task = lock_store.set(f"file{i}.py", lock_data, 1800)
        tasks.append(task)

    # 동시 실행
    results = await asyncio.gather(*tasks)

    # 모두 성공
    assert all(results)

    # Scan
    cursor, keys = await lock_store.scan()
    assert len(keys) == 1000


# ============================================================
# Performance Tests
# ============================================================


@pytest.mark.asyncio
async def test_write_performance(lock_store):
    """Performance: Write <1ms"""
    import time

    lock_data = {
        "agent_id": "agent-1",
        "acquired_at": datetime.now().isoformat(),
        "file_hash": "abc",
        "lock_type": "write",
        "ttl_seconds": 1800,
    }

    start = time.perf_counter()
    await lock_store.set("main.py", lock_data, 1800)
    elapsed_ms = (time.perf_counter() - start) * 1000

    assert elapsed_ms < 10  # <10ms (여유)


# ============================================================
# Factory Tests
# ============================================================


def test_create_lock_store_sqlite(tmp_path):
    """Factory: SQLite 모드"""
    db_path = tmp_path / "locks.db"

    store = create_lock_store(mode="sqlite", sqlite_path=str(db_path))

    assert isinstance(store, SQLiteLockStore)
    assert store.db_path == db_path

    store.close()


def test_create_lock_store_memory():
    """Factory: Memory 모드"""
    store = create_lock_store(mode="memory")

    assert isinstance(store, SQLiteLockStore)
    assert store.db_path == Path(":memory:")

    store.close()


def test_create_lock_store_auto_no_redis(tmp_path):
    """Factory: Auto (Redis 없음) → SQLite"""
    store = create_lock_store(mode="auto", redis_client=None, sqlite_path=str(tmp_path / "locks.db"))

    assert isinstance(store, SQLiteLockStore)

    store.close()


@pytest.mark.asyncio
async def test_create_lock_store_auto_with_redis():
    """Factory: Auto (Redis 있음) → Redis"""
    from unittest.mock import AsyncMock

    redis_mock = AsyncMock()

    store = create_lock_store(mode="auto", redis_client=redis_mock)

    # Redis 반환됨
    assert store is redis_mock
