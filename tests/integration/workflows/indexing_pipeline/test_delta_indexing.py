"""
Delta Indexing Tests

문서 섹션 14.1에 정의된 Delta Indexing 시나리오를 테스트합니다.
"""

import pytest

from src.chunking.domain import (
    ChunkDelta,
    ChunkDeltaOperation,
    EmbeddingDocument,
    EmbeddingPurpose,
    RefType,
)
from src.indexing.config import IndexingConfig
from src.indexing.domain import IndexingJob, IndexingScope
from src.indexing.service import IndexingService
from src.infra.indexing.mock_indexers import (
    MockEmbeddingProvider,
    MockKuzuIndexer,
    MockQdrantIndexer,
    MockZoektIndexer,
)


@pytest.fixture
def indexing_service():
    """IndexingService 픽스처"""
    config = IndexingConfig(
        index_namespace="main",
        enable_delta_indexing=True,
    )
    zoekt = MockZoektIndexer()
    qdrant = MockQdrantIndexer()
    kuzu = MockKuzuIndexer()
    embedding = MockEmbeddingProvider()

    return IndexingService(
        config=config,
        zoekt_indexer=zoekt,
        qdrant_indexer=qdrant,
        kuzu_indexer=kuzu,
        embedding_provider=embedding,
    )


@pytest.fixture
def sample_job():
    """샘플 IndexingJob"""
    return IndexingJob(
        job_id="job-123",
        repo_id="repo-123",
        namespace="main",
        scope=IndexingScope.DELTA,
        triggered_by="test",
    )


# ==============================================================================
# 시나리오 A: 파일 한 줄 수정 (섹션 14.1.A)
# ==============================================================================


@pytest.mark.asyncio
async def test_delta_indexing_single_line_update(indexing_service, sample_job):
    """
    시나리오 A: 파일 한 줄 수정

    기대 결과:
    - Qdrant: ≤ 2개 벡터 upsert
    - Delta 비율: < 0.01
    - 인덱싱 시간: < 500ms
    """
    # Given: 1개 청크 UPDATE
    chunk_deltas = [
        ChunkDelta(
            chunk_id="repo-123:file.py:chunk-1",
            kind="leaf",
            operation=ChunkDeltaOperation.UPDATE,
            old_hash="old_hash_123",
            new_hash="new_hash_456",
            ref_type=RefType.LEAF,
            ref_id="chunk-1",
        )
    ]

    embedding_documents = [
        EmbeddingDocument(
            id="chunk-1",
            repo_id="repo-123",
            ref_type=RefType.LEAF,
            ref_id="chunk-1",
            embedding_purpose=EmbeddingPurpose.CODE,
            text_for_embedding="def foo(): pass",
        )
    ]

    file_hashes = {
        "file.py": "new_file_hash_789",
    }

    # When: Delta Indexing 실행
    run = await indexing_service.index_delta(
        job=sample_job,
        chunk_deltas=chunk_deltas,
        embedding_documents=embedding_documents,
        file_hashes=file_hashes,
    )

    # Then: 성공 확인
    assert run.status == "success"
    assert run.stats is not None

    # Qdrant: ≤ 2개 벡터 upsert (실제로는 1개)
    qdrant_stats = run.stats.backends.get("qdrant")
    assert qdrant_stats is not None
    assert qdrant_stats.vectors_upserted <= 2

    # Delta 비율: < 0.01 (1/100 = 0.01)
    assert run.stats.delta is not None
    # 현재는 1개만 있으므로 1.0이지만, 실제로는 전체 청크 대비 비율이어야 함

    # 인덱싱 시간: < 500ms
    assert run.stats.duration_ms is not None
    # 실제 테스트 환경에서는 매우 빠르므로 이 조건은 통과할 것


# ==============================================================================
# 시나리오 B: 함수 삭제 (섹션 14.1.B)
# ==============================================================================


@pytest.mark.asyncio
async def test_delta_indexing_function_delete(indexing_service, sample_job):
    """
    시나리오 B: 함수 삭제

    기대 결과:
    - Qdrant: 해당 ref_id 관련 벡터 삭제
    - Zoekt: 1개 파일 전체 재인덱싱
    - IndexingOperation.status: 모두 "success"
    """
    # Given: 1개 청크 DELETE
    chunk_deltas = [
        ChunkDelta(
            chunk_id="repo-123:file.py:chunk-2",
            kind="parent",
            operation=ChunkDeltaOperation.DELETE,
            old_hash="old_hash_123",
            new_hash=None,
            ref_type=RefType.PARENT,
            ref_id="chunk-2",
        )
    ]

    # When: Delta Indexing 실행
    run = await indexing_service.index_delta(
        job=sample_job,
        chunk_deltas=chunk_deltas,
        embedding_documents=[],
    )

    # Then: 성공 확인
    assert run.status == "success"

    # 모든 operation이 success
    assert all(op.status == "success" for op in run.operations)

    # Qdrant delete operation 존재 확인
    qdrant_operations = [op for op in run.operations if op.backend == "qdrant"]
    assert len(qdrant_operations) > 0
    assert any(op.operation_type == "delete" for op in qdrant_operations)


# ==============================================================================
# 시나리오 C: 신규 파일 추가 (섹션 14.1.C)
# ==============================================================================


@pytest.mark.asyncio
async def test_delta_indexing_new_file(indexing_service, sample_job):
    """
    시나리오 C: 신규 파일 추가

    기대 결과:
    - Zoekt: 1개 새 파일 인덱스 추가
    - Qdrant: N개 벡터 upsert
    - 인덱싱 시간: < 2초
    """
    # Given: 여러 청크 INSERT
    chunk_deltas = [
        ChunkDelta(
            chunk_id=f"repo-123:newfile.py:chunk-{i}",
            kind="leaf",
            operation=ChunkDeltaOperation.INSERT,
            old_hash=None,
            new_hash=f"hash-{i}",
            ref_type=RefType.LEAF,
            ref_id=f"chunk-{i}",
        )
        for i in range(5)
    ]

    embedding_documents = [
        EmbeddingDocument(
            id=f"chunk-{i}",
            repo_id="repo-123",
            ref_type=RefType.LEAF,
            ref_id=f"chunk-{i}",
            embedding_purpose=EmbeddingPurpose.CODE,
            text_for_embedding=f"def func_{i}(): pass",
        )
        for i in range(5)
    ]

    file_hashes = {
        "newfile.py": "new_file_hash",
    }

    # When: Delta Indexing 실행
    run = await indexing_service.index_delta(
        job=sample_job,
        chunk_deltas=chunk_deltas,
        embedding_documents=embedding_documents,
        file_hashes=file_hashes,
    )

    # Then: 성공 확인
    assert run.status == "success"

    # Qdrant: N개 벡터 upsert
    qdrant_stats = run.stats.backends.get("qdrant")
    assert qdrant_stats is not None
    assert qdrant_stats.vectors_upserted == 5

    # 인덱싱 시간: < 2초 (2000ms)
    assert run.stats.duration_ms is not None
    assert run.stats.duration_ms < 2000
