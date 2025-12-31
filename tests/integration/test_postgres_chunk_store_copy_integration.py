"""
Integration Test: PostgreSQL COPY 최적화

Container를 사용한 실제 환경 테스트
"""

import pytest

from codegraph_engine.code_foundation.infrastructure.chunk.models import Chunk


@pytest.mark.integration
@pytest.mark.asyncio
async def test_copy_performance_with_container():
    """
    Container를 통한 COPY 성능 테스트

    실제 프로덕션 환경과 동일하게 Container 사용
    """
    import time

    from codegraph_shared.container import Container

    # Container 초기화 (프로덕션과 동일)
    container = Container()
    chunk_store = container.chunk_store

    # 500개 청크 생성
    chunks = [
        Chunk(
            chunk_id=f"chunk:test_integration:perf:{i}",
            repo_id="test_integration",
            snapshot_id="snap1",
            project_id=None,
            module_path=None,
            file_path=f"file_{i}.py",
            parent_id=None,
            children=[],
            kind="file",
            fqn=f"file_{i}.py",
            language="python",
            symbol_visibility="public",
            symbol_id=f"sym_{i}",
            symbol_owner_id=None,
            start_line=1,
            end_line=100,
            original_start_line=1,
            original_end_line=100,
            content_hash=f"hash_{i}",
            version=1,
            is_deleted=False,
            last_indexed_commit=None,
            summary=f"Integration test {i}",
            importance=1.0,
            attrs={"test": True},
            is_test=False,
            is_overlay=False,
            overlay_session_id=None,
            base_chunk_id=None,
        )
        for i in range(500)
    ]

    # 성능 측정
    start = time.perf_counter()
    await chunk_store.save_chunks(chunks)
    elapsed_ms = (time.perf_counter() - start) * 1000

    print(f"\n✅ COPY Performance: {elapsed_ms:.2f}ms for 500 chunks")

    # 성능 검증: 200ms 이하 (COPY 최적화)
    assert elapsed_ms < 200, f"Too slow: {elapsed_ms:.2f}ms (expected < 200ms)"

    # Cleanup
    # CachedStore를 거치므로 실제 PostgresStore 접근
    postgres_store = chunk_store.store if hasattr(chunk_store, "store") else chunk_store
    pool = await postgres_store._postgres_store._ensure_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            DELETE FROM chunks WHERE repo_id = 'test_integration'
        """)
        print("   Cleaned up test data")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_copy_upsert_with_container():
    """
    Container를 통한 UPSERT 동작 검증
    """
    from codegraph_shared.container import Container

    container = Container()
    chunk_store = container.chunk_store

    # 초기 청크
    initial = Chunk(
        chunk_id="chunk:test_integration:upsert:1",
        repo_id="test_integration",
        snapshot_id="snap1",
        project_id=None,
        module_path=None,
        file_path="test.py",
        parent_id=None,
        children=[],
        kind="file",
        fqn="test.py",
        language="python",
        symbol_visibility="public",
        symbol_id="sym1",
        symbol_owner_id=None,
        start_line=1,
        end_line=10,
        original_start_line=1,
        original_end_line=10,
        content_hash="hash_v1",
        version=1,
        is_deleted=False,
        last_indexed_commit=None,
        summary="Version 1",
        importance=1.0,
        attrs={"version": 1},
        is_test=False,
        is_overlay=False,
        overlay_session_id=None,
        base_chunk_id=None,
    )

    await chunk_store.save_chunks([initial])

    # 업데이트 청크 (같은 ID)
    updated = Chunk(
        chunk_id="chunk:test_integration:upsert:1",  # 같은 ID
        repo_id="test_integration",
        snapshot_id="snap2",
        project_id=None,
        module_path=None,
        file_path="test.py",
        parent_id=None,
        children=["child1"],
        kind="file",
        fqn="test.py",
        language="python",
        symbol_visibility="public",
        symbol_id="sym1",
        symbol_owner_id=None,
        start_line=1,
        end_line=20,
        original_start_line=1,
        original_end_line=20,
        content_hash="hash_v2",
        version=2,
        is_deleted=False,
        last_indexed_commit="commit123",
        summary="Version 2",
        importance=0.8,
        attrs={"version": 2},
        is_test=False,
        is_overlay=False,
        overlay_session_id=None,
        base_chunk_id=None,
    )

    await chunk_store.save_chunks([updated])

    # 검증
    retrieved = await chunk_store.get_chunk("chunk:test_integration:upsert:1")

    assert retrieved is not None
    assert retrieved.snapshot_id == "snap2", "Should be updated"
    assert retrieved.end_line == 20, "Should be updated"
    assert retrieved.version == 2, "Should be updated"
    assert retrieved.summary == "Version 2", "Should be updated"

    print("\n✅ UPSERT: ON CONFLICT works correctly")

    # Cleanup
    postgres_store = chunk_store.store if hasattr(chunk_store, "store") else chunk_store
    pool = await postgres_store._postgres_store._ensure_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            DELETE FROM chunks WHERE repo_id = 'test_integration'
        """)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_copy_large_batch_with_container():
    """
    Container를 통한 대용량 배치 테스트
    """
    import time

    from codegraph_shared.container import Container

    container = Container()
    chunk_store = container.chunk_store

    total_chunks = 1000

    chunks = [
        Chunk(
            chunk_id=f"chunk:test_integration:large:{i}",
            repo_id="test_integration",
            snapshot_id="snap1",
            project_id=None,
            module_path=None,
            file_path=f"file_{i}.py",
            parent_id=None,
            children=[],
            kind="file",
            fqn=f"file_{i}.py",
            language="python",
            symbol_visibility="public",
            symbol_id=f"sym_{i}",
            symbol_owner_id=None,
            start_line=1,
            end_line=100,
            original_start_line=1,
            original_end_line=100,
            content_hash=f"hash_{i}",
            version=1,
            is_deleted=False,
            last_indexed_commit=None,
            summary=f"Large batch {i}",
            importance=1.0,
            attrs={"batch": True},
            is_test=False,
            is_overlay=False,
            overlay_session_id=None,
            base_chunk_id=None,
        )
        for i in range(total_chunks)
    ]

    start = time.perf_counter()
    await chunk_store.save_chunks(chunks)
    elapsed_ms = (time.perf_counter() - start) * 1000

    print(f"\n✅ Large Batch: {elapsed_ms:.2f}ms for {total_chunks} chunks")
    print(f"   Average: {elapsed_ms / total_chunks:.2f}ms per chunk")

    # 성능 검증: 500ms 이하
    assert elapsed_ms < 500, f"Too slow: {elapsed_ms:.2f}ms"

    # Cleanup
    postgres_store = chunk_store.store if hasattr(chunk_store, "store") else chunk_store
    pool = await postgres_store._postgres_store._ensure_pool()
    async with pool.acquire() as conn:
        count = await conn.fetchval("""
            SELECT COUNT(*) FROM chunks
            WHERE repo_id = 'test_integration'
            AND chunk_id LIKE 'chunk:test_integration:large:%'
        """)
        assert count == total_chunks, f"Expected {total_chunks}, got {count}"

        await conn.execute("""
            DELETE FROM chunks WHERE repo_id = 'test_integration'
        """)
