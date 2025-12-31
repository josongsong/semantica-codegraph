"""
IR Loader Tests - Base/Edge/Corner Cases (SOTA L11)

Test Coverage:
- Base Case: 정상 로드
- Edge Case: 경계 조건 (빈 IR, 대용량 IR)
- Corner Case: 극한 조건 (cache eviction, concurrent access)
- Error Case: 실패 처리
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from codegraph_engine.code_foundation.infrastructure.ir.models import Node

import pytest

from codegraph_engine.code_foundation.infrastructure.ir.models import IRDocument
from codegraph_engine.code_foundation.infrastructure.storage.ir_document_store import (
    IRDocumentStore,
)
from codegraph_runtime.llm_arbitration.infrastructure.ir_loader import (
    ContainerIRLoader,
    PostgresIRLoader,
)


class TestPostgresIRLoader:
    """PostgresIRLoader 테스트 (Real Store)"""

    @pytest.mark.asyncio
    async def test_load_ir_base_case(self, mock_postgres_store, sample_ir_doc):
        """Base Case: 정상 IR Document 로드"""
        # Setup
        ir_store = IRDocumentStore(mock_postgres_store, auto_migrate=False)
        await ir_store.save(sample_ir_doc)

        loader = PostgresIRLoader(ir_document_store=ir_store)

        # Execute
        result = await loader.load_ir(
            repo_id=sample_ir_doc.repo_id,
            snapshot_id=sample_ir_doc.snapshot_id,
        )

        # Assert
        assert result is not None
        assert result.repo_id == sample_ir_doc.repo_id
        assert result.snapshot_id == sample_ir_doc.snapshot_id
        assert len(result.nodes) == len(sample_ir_doc.nodes)

    @pytest.mark.asyncio
    async def test_load_ir_cache_hit(self, mock_postgres_store, sample_ir_doc):
        """Performance: Cache hit (O(1))"""
        ir_store = IRDocumentStore(mock_postgres_store, auto_migrate=False)
        await ir_store.save(sample_ir_doc)

        loader = PostgresIRLoader(ir_document_store=ir_store, cache_size=10)

        # First load (cache miss)
        result1 = await loader.load_ir(sample_ir_doc.repo_id, sample_ir_doc.snapshot_id)

        # Second load (cache hit)
        result2 = await loader.load_ir(sample_ir_doc.repo_id, sample_ir_doc.snapshot_id)

        # Assert
        assert result1 is not None
        assert result2 is not None
        assert result1 is result2  # Same object (cache)

    @pytest.mark.asyncio
    async def test_load_ir_not_found(self, mock_postgres_store):
        """Edge Case: IR Document 없음"""
        ir_store = IRDocumentStore(mock_postgres_store, auto_migrate=False)
        loader = PostgresIRLoader(ir_document_store=ir_store)

        # Execute
        result = await loader.load_ir("nonexistent", "snapshot:999")

        # Assert: None 반환 (예외 던지지 않음)
        assert result is None

    @pytest.mark.asyncio
    async def test_load_ir_empty_nodes(self, mock_postgres_store):
        """Edge Case: 빈 IR Document (nodes=[], edges=[])"""
        empty_ir = IRDocument(
            repo_id="empty_repo",
            snapshot_id="snap:1",
            nodes=[],
            edges=[],
        )

        ir_store = IRDocumentStore(mock_postgres_store, auto_migrate=False)
        await ir_store.save(empty_ir)

        loader = PostgresIRLoader(ir_document_store=ir_store)
        result = await loader.load_ir("empty_repo", "snap:1")

        # Assert: 빈 IR도 정상 로드
        assert result is not None
        assert len(result.nodes) == 0
        assert len(result.edges) == 0

    @pytest.mark.asyncio
    async def test_cache_eviction(self, mock_postgres_store, sample_ir_doc):
        """Corner Case: Cache eviction (LRU)"""
        ir_store = IRDocumentStore(mock_postgres_store, auto_migrate=False)

        # Cache size = 2
        loader = PostgresIRLoader(ir_document_store=ir_store, cache_size=2)

        # Save 3 IR documents
        for i in range(3):
            ir = IRDocument(
                repo_id=f"repo:{i}",
                snapshot_id=f"snap:{i}",
                nodes=[],
                edges=[],
            )
            await ir_store.save(ir)

        # Load 3 documents (cache eviction 발생)
        for i in range(3):
            result = await loader.load_ir(f"repo:{i}", f"snap:{i}")
            assert result is not None

        # Cache size should be 2 (최대 크기)
        assert len(loader._cache) == 2

    @pytest.mark.asyncio
    async def test_concurrent_load(self, mock_postgres_store, sample_ir_doc):
        """Corner Case: 동시 로드 (Race condition 없음)"""
        import asyncio

        ir_store = IRDocumentStore(mock_postgres_store, auto_migrate=False)
        await ir_store.save(sample_ir_doc)

        loader = PostgresIRLoader(ir_document_store=ir_store)

        # 동시에 10번 로드
        tasks = [loader.load_ir(sample_ir_doc.repo_id, sample_ir_doc.snapshot_id) for _ in range(10)]

        results = await asyncio.gather(*tasks)

        # Assert: 모두 성공
        assert all(r is not None for r in results)
        assert all(r.repo_id == sample_ir_doc.repo_id for r in results)

    @pytest.mark.asyncio
    async def test_load_large_ir(self, mock_postgres_store):
        """Edge Case: 대용량 IR Document (10K+ nodes)"""
        from codegraph_engine.code_foundation.infrastructure.ir.models import Node

        # 10K nodes
        large_ir = IRDocument(
            repo_id="large_repo",
            snapshot_id="snap:large",
            nodes=[
                Node(
                    id=f"node:{i}",
                    name=f"func_{i}",
                    kind="function",
                    file_path=f"file_{i % 100}.py",
                )
                for i in range(10000)
            ],
            edges=[],
        )

        ir_store = IRDocumentStore(mock_postgres_store, auto_migrate=False)

        # Save
        saved = await ir_store.save(large_ir)
        assert saved

        # Load
        loader = PostgresIRLoader(ir_document_store=ir_store)
        result = await loader.load_ir("large_repo", "snap:large")

        # Assert
        assert result is not None
        assert len(result.nodes) == 10000


class TestContainerIRLoader:
    """ContainerIRLoader 테스트 (Integration)"""

    @pytest.mark.asyncio
    async def test_load_ir_delegates_to_postgres_loader(self, mock_postgres_store):
        """Integration: PostgresIRLoader로 위임"""
        from unittest.mock import AsyncMock, MagicMock

        # Mock PostgresIRLoader
        mock_postgres_loader = MagicMock()
        mock_postgres_loader.load_ir = AsyncMock(return_value=None)

        loader = ContainerIRLoader(postgres_loader=mock_postgres_loader)

        # Execute
        await loader.load_ir("repo:1", "snap:1")

        # Assert: PostgresIRLoader.load_ir 호출됨
        mock_postgres_loader.load_ir.assert_called_once_with("repo:1", "snap:1")


class TestIRDocumentStore:
    """IRDocumentStore 테스트 (Database)"""

    @pytest.mark.asyncio
    async def test_save_and_load_roundtrip(self, mock_postgres_store, sample_ir_doc):
        """Base Case: Save → Load 라운드트립"""
        store = IRDocumentStore(mock_postgres_store, auto_migrate=False)

        # Save
        saved = await store.save(sample_ir_doc)
        assert saved

        # Load
        loaded = await store.load(sample_ir_doc.repo_id, sample_ir_doc.snapshot_id)

        # Assert
        assert loaded is not None
        assert loaded.repo_id == sample_ir_doc.repo_id
        assert loaded.snapshot_id == sample_ir_doc.snapshot_id

    @pytest.mark.asyncio
    async def test_save_duplicate_upsert(self, mock_postgres_store, sample_ir_doc):
        """Edge Case: 중복 저장 (UPSERT)"""
        store = IRDocumentStore(mock_postgres_store, auto_migrate=False)

        # First save
        await store.save(sample_ir_doc)

        # Second save (UPSERT)
        sample_ir_doc.nodes.append(Node(id="new_node", name="new", kind="function", file_path="new.py"))
        saved = await store.save(sample_ir_doc)

        # Assert: 성공
        assert saved

        # Load
        loaded = await store.load(sample_ir_doc.repo_id, sample_ir_doc.snapshot_id)
        assert len(loaded.nodes) == len(sample_ir_doc.nodes)

    @pytest.mark.asyncio
    async def test_load_nonexistent(self, mock_postgres_store):
        """Edge Case: 존재하지 않는 IR"""
        store = IRDocumentStore(mock_postgres_store, auto_migrate=False)

        result = await store.load("nonexistent", "snap:999")

        # Assert: None 반환 (예외 던지지 않음)
        assert result is None


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def sample_ir_doc():
    """Sample IR Document for testing"""
    from codegraph_engine.code_foundation.infrastructure.ir.models import Edge, Node

    return IRDocument(
        repo_id="test_repo",
        snapshot_id="snap:test",
        schema_version="2.1",
        nodes=[
            Node(id="node:1", name="main", kind="function", file_path="main.py"),
            Node(id="node:2", name="helper", kind="function", file_path="utils.py"),
        ],
        edges=[
            Edge(source="node:1", target="node:2", kind="calls"),
        ],
    )


@pytest.fixture
def mock_postgres_store():
    """Mock PostgresStore for testing"""
    from unittest.mock import AsyncMock, MagicMock

    mock = MagicMock()
    mock.pool = MagicMock()

    # Mock connection
    mock_conn = MagicMock()
    mock_conn.execute = AsyncMock()
    mock_conn.fetchrow = AsyncMock(return_value=None)

    # Mock acquire context manager
    mock.pool.acquire = MagicMock()
    mock.pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock.pool.acquire.return_value.__aexit__ = AsyncMock()

    return mock
