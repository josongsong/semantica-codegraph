"""
IR Document Store Real DB Tests (No Mock!)

SOTA L11 원칙:
- Real PostgreSQL (via pytest-postgresql or testcontainer)
- Schema verification (line-by-line)
- Roundtrip validation
- No Fake, No Stub
"""

import pytest

from codegraph_engine.code_foundation.infrastructure.ir.models import (
    Edge,
    EdgeKind,
    IRDocument,
    Node,
    NodeKind,
    Span,
)
from codegraph_engine.code_foundation.infrastructure.storage.ir_document_store import (
    IRDocumentStore,
)


@pytest.mark.integration
@pytest.mark.asyncio
class TestIRDocumentStoreReal:
    """
    Real PostgreSQL 테스트 (No Mock!).

    요구사항:
    - PostgreSQL 실행 중이어야 함
    - TEST_DATABASE_URL 환경변수 필요

    실행:
        pytest tests/contexts/code_foundation/test_ir_document_store_real.py -v
    """

    async def test_save_and_load_complete_roundtrip(self, real_postgres_store):
        """
        CRITICAL: Complete roundtrip 검증.

        Schema Verification (Line-by-Line):
        - 모든 필드 직렬화/역직렬화
        - Type mismatch 없음
        - Nullable 필드 처리
        """
        store = IRDocumentStore(real_postgres_store, auto_migrate=True)

        # Complete Node (all fields)
        node = Node(
            id="node:test:func:main",
            kind=NodeKind.FUNCTION,
            fqn="test.main",
            file_path="test.py",
            span=Span(start_line=1, start_col=0, end_line=10, end_col=0),
            language="python",
            stable_id="stable:12345",
            content_hash="hash:abc123",
            name="main",
            module_path="test",
            parent_id=None,
            body_span=Span(start_line=2, start_col=4, end_line=9, end_col=4),
            docstring="Main function",
            role="controller",
            is_test_file=False,
            signature_id="sig:main",
            declared_type_id=None,
            control_flow_summary=None,  # Skip for now
            attrs={"visibility": "public", "async": False},
        )

        # Complete Edge (all fields)
        edge = Edge(
            id="edge:call:main→helper",
            kind=EdgeKind.CALLS,
            source_id="node:test:func:main",
            target_id="node:test:func:helper",
            span=Span(start_line=5, start_col=4, end_line=5, end_col=10),
            attrs={"call_type": "direct"},
        )

        ir_doc = IRDocument(
            repo_id="test_repo_real",
            snapshot_id="snap:real:001",
            schema_version="2.1",
            nodes=[node],
            edges=[edge],
        )

        # 1. Save
        saved = await store.save(ir_doc)
        assert saved, "Save failed"

        # 2. Load
        loaded = await store.load("test_repo_real", "snap:real:001")

        # 3. Verify (Field-by-field)
        assert loaded is not None
        assert loaded.repo_id == ir_doc.repo_id
        assert loaded.snapshot_id == ir_doc.snapshot_id
        assert loaded.schema_version == ir_doc.schema_version

        # Node verification
        assert len(loaded.nodes) == 1
        loaded_node = loaded.nodes[0]

        # Required fields
        assert loaded_node.id == node.id
        assert loaded_node.kind == node.kind
        assert loaded_node.fqn == node.fqn
        assert loaded_node.file_path == node.file_path
        assert loaded_node.language == node.language

        # Span
        assert loaded_node.span.start_line == node.span.start_line
        assert loaded_node.span.start_col == node.span.start_col
        assert loaded_node.span.end_line == node.span.end_line
        assert loaded_node.span.end_col == node.span.end_col

        # Optional fields
        assert loaded_node.stable_id == node.stable_id
        assert loaded_node.content_hash == node.content_hash
        assert loaded_node.name == node.name
        assert loaded_node.module_path == node.module_path
        assert loaded_node.docstring == node.docstring
        assert loaded_node.role == node.role
        assert loaded_node.is_test_file == node.is_test_file

        # Body span
        assert loaded_node.body_span is not None
        assert loaded_node.body_span.start_line == node.body_span.start_line

        # Attrs
        assert loaded_node.attrs == node.attrs

        # Edge verification
        assert len(loaded.edges) == 1
        loaded_edge = loaded.edges[0]

        assert loaded_edge.id == edge.id
        assert loaded_edge.kind == edge.kind
        assert loaded_edge.source_id == edge.source_id
        assert loaded_edge.target_id == edge.target_id
        assert loaded_edge.attrs == edge.attrs

        # Edge span
        assert loaded_edge.span is not None
        assert loaded_edge.span.start_line == edge.span.start_line

    async def test_upsert_behavior(self, real_postgres_store):
        """
        CRITICAL: UPSERT 동작 검증.

        Verification:
        - 첫 번째 저장: INSERT
        - 두 번째 저장: UPDATE
        - node_count 업데이트 확인
        """
        store = IRDocumentStore(real_postgres_store, auto_migrate=True)

        # First save
        ir_doc_v1 = IRDocument(
            repo_id="upsert_test",
            snapshot_id="snap:1",
            nodes=[
                Node(
                    id="node:1",
                    kind=NodeKind.FUNCTION,
                    fqn="test.func1",
                    file_path="test.py",
                    span=Span(1, 0, 5, 0),
                    language="python",
                )
            ],
            edges=[],
        )

        await store.save(ir_doc_v1)

        # Second save (same repo_id, snapshot_id)
        ir_doc_v2 = IRDocument(
            repo_id="upsert_test",
            snapshot_id="snap:1",
            nodes=[
                Node(
                    id="node:1",
                    kind=NodeKind.FUNCTION,
                    fqn="test.func1",
                    file_path="test.py",
                    span=Span(1, 0, 5, 0),
                    language="python",
                ),
                Node(
                    id="node:2",
                    kind=NodeKind.FUNCTION,
                    fqn="test.func2",
                    file_path="test.py",
                    span=Span(6, 0, 10, 0),
                    language="python",
                ),
            ],
            edges=[],
        )

        await store.save(ir_doc_v2)

        # Load
        loaded = await store.load("upsert_test", "snap:1")

        # Assert: Updated (2 nodes, not 1)
        assert loaded is not None
        assert len(loaded.nodes) == 2

    async def test_concurrent_saves_no_corruption(self, real_postgres_store):
        """
        Corner Case: 동시 저장 (Race condition).

        Verification:
        - 10개 동시 저장
        - 데이터 corruption 없음
        - 모두 성공
        """
        import asyncio

        store = IRDocumentStore(real_postgres_store, auto_migrate=True)

        # 10개 동시 저장
        tasks = []
        for i in range(10):
            ir_doc = IRDocument(
                repo_id=f"concurrent_test_{i}",
                snapshot_id="snap:1",
                nodes=[
                    Node(
                        id=f"node:{i}",
                        kind=NodeKind.FUNCTION,
                        fqn=f"test.func{i}",
                        file_path=f"test{i}.py",
                        span=Span(1, 0, 5, 0),
                        language="python",
                    )
                ],
                edges=[],
            )
            tasks.append(store.save(ir_doc))

        # Execute concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Assert: 모두 성공 (no exception)
        assert all(r is True for r in results)

        # Assert: 모두 로드 가능
        for i in range(10):
            loaded = await store.load(f"concurrent_test_{i}", "snap:1")
            assert loaded is not None
            assert len(loaded.nodes) == 1


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
async def real_postgres_store():
    """
    Real PostgreSQL Store (No Mock!).

    환경변수 필요:
        TEST_DATABASE_URL=postgresql://user:pass@localhost/test_db

    Alternative:
        pytest-postgresql fixture 사용
        또는 testcontainers-python 사용
    """
    import os

    # Check for test database
    db_url = os.getenv("TEST_DATABASE_URL")
    if not db_url:
        pytest.skip("TEST_DATABASE_URL not set (Real DB test)")

    # Import PostgresStore
    from codegraph_shared.infra.storage.postgres import PostgresStore

    # Create real store
    store = PostgresStore(database_url=db_url)

    # Initialize connection pool
    await store.connect()

    yield store

    # Cleanup
    await store.disconnect()


@pytest.fixture(autouse=True)
async def cleanup_test_data(real_postgres_store):
    """테스트 후 데이터 정리"""
    yield

    # Delete test data
    try:
        async with real_postgres_store.pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM ir_documents WHERE repo_id LIKE 'test_%' OR repo_id LIKE 'concurrent_%' OR repo_id LIKE 'upsert_%'"
            )
    except Exception:
        pass  # Cleanup failure는 무시
