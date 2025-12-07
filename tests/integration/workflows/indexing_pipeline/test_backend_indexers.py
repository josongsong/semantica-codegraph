"""
Backend Indexers Tests

Mock Indexers의 기본 동작을 테스트합니다.
"""

import pytest
from src.indexing.domain import (
    FileIndexDocument,
    GraphEdgeRecord,
    GraphNodeRecord,
    VectorIndexRecord,
)
from src.infra.indexing.mock_indexers import (
    MockEmbeddingProvider,
    MockKuzuIndexer,
    MockQdrantIndexer,
    MockZoektIndexer,
)

# ==============================================================================
# MockZoektIndexer Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_zoekt_indexer_basic():
    """Zoekt 기본 동작 테스트"""
    indexer = MockZoektIndexer()

    # Given: FileIndexDocument
    doc = FileIndexDocument(
        id="doc-1",
        repo_id="repo-123",
        file_path="file.py",
        language="python",
        namespace="main",
        text="def foo(): pass",
        source_file_hash="hash-123",
    )

    # When: 파일 인덱싱
    await indexer.index_file(doc)

    # Then: 인덱싱된 파일 목록 확인
    files = await indexer.get_indexed_files("repo-123", "main")
    assert "file.py" in files


@pytest.mark.asyncio
async def test_zoekt_indexer_delete():
    """Zoekt 파일 삭제 테스트"""
    indexer = MockZoektIndexer()

    # Given: 파일 인덱싱
    doc = FileIndexDocument(
        id="doc-1",
        repo_id="repo-123",
        file_path="file.py",
        language="python",
        namespace="main",
        text="def foo(): pass",
        source_file_hash="hash-123",
    )
    await indexer.index_file(doc)

    # When: 파일 삭제
    await indexer.delete_file("repo-123", "main", "file.py")

    # Then: 파일 목록에 없음
    files = await indexer.get_indexed_files("repo-123", "main")
    assert "file.py" not in files


# ==============================================================================
# MockQdrantIndexer Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_qdrant_indexer_basic():
    """Qdrant 기본 동작 테스트"""
    indexer = MockQdrantIndexer()

    # Given: VectorIndexRecord
    record = VectorIndexRecord(
        id="vec-1",
        repo_id="repo-123",
        namespace="main",
        vector=[0.1, 0.2, 0.3],
        payload={"ref_id": "chunk-1"},
    )

    # When: 벡터 upsert
    await indexer.upsert_vector(record)

    # Then: 벡터 개수 확인
    count = await indexer.get_vector_count("main")
    assert count == 1


@pytest.mark.asyncio
async def test_qdrant_indexer_batch():
    """Qdrant 배치 upsert 테스트"""
    indexer = MockQdrantIndexer()

    # Given: 여러 VectorIndexRecord
    records = [
        VectorIndexRecord(
            id=f"vec-{i}",
            repo_id="repo-123",
            namespace="main",
            vector=[0.1 * i, 0.2 * i, 0.3 * i],
            payload={"ref_id": f"chunk-{i}"},
        )
        for i in range(10)
    ]

    # When: 배치 upsert
    await indexer.upsert_vectors_batch(records)

    # Then: 벡터 개수 확인
    count = await indexer.get_vector_count("main")
    assert count == 10


# ==============================================================================
# MockKuzuIndexer Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_kuzu_indexer_basic():
    """Kùzu 기본 동작 테스트"""
    indexer = MockKuzuIndexer()

    # Given: GraphNodeRecord
    node = GraphNodeRecord(
        id="node-1",
        repo_id="repo-123",
        namespace="main",
        kind="function",
        attrs={"name": "foo"},
    )

    # When: 노드 upsert
    await indexer.upsert_node(node)

    # Then: 노드 개수 확인
    count = await indexer.get_node_count("main")
    assert count == 1


@pytest.mark.asyncio
async def test_kuzu_indexer_edge_cascade_delete():
    """Kùzu 노드 삭제 시 엣지 자동 삭제 테스트"""
    indexer = MockKuzuIndexer()

    # Given: 노드 2개 + 엣지 1개
    node1 = GraphNodeRecord(
        id="node-1",
        repo_id="repo-123",
        namespace="main",
        kind="function",
        attrs={"name": "foo"},
    )
    node2 = GraphNodeRecord(
        id="node-2",
        repo_id="repo-123",
        namespace="main",
        kind="function",
        attrs={"name": "bar"},
    )
    edge = GraphEdgeRecord(
        id="edge-1",
        repo_id="repo-123",
        namespace="main",
        src_id="node-1",
        dst_id="node-2",
        edge_type="calls",
    )

    await indexer.upsert_node(node1)
    await indexer.upsert_node(node2)
    await indexer.upsert_edge(edge)

    # When: node-1 삭제
    await indexer.delete_node("node-1", "main")

    # Then: 엣지도 자동 삭제됨
    edge_count = await indexer.get_edge_count("main")
    assert edge_count == 0


# ==============================================================================
# MockEmbeddingProvider Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_embedding_provider_basic():
    """EmbeddingProvider 기본 동작 테스트"""
    provider = MockEmbeddingProvider(dimension=128)

    # When: 임베딩 생성
    vector = await provider.generate_embedding("def foo(): pass")

    # Then: 차원 확인
    assert len(vector) == 128
    assert provider.get_embedding_dimension() == 128


@pytest.mark.asyncio
async def test_embedding_provider_batch():
    """EmbeddingProvider 배치 생성 테스트"""
    provider = MockEmbeddingProvider(dimension=128)

    # Given: 여러 텍스트
    texts = ["text-1", "text-2", "text-3"]

    # When: 배치 임베딩 생성
    vectors = await provider.generate_embeddings_batch(texts)

    # Then: 개수 및 차원 확인
    assert len(vectors) == 3
    assert all(len(v) == 128 for v in vectors)
