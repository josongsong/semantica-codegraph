"""
Integration tests for Qdrant modes.

Tests real Qdrant client behavior with actual connections.
Requires qdrant-client to be installed.
"""

import asyncio
from pathlib import Path

import pytest
from qdrant_client.models import Distance, VectorParams

from codegraph_shared.infra.vector import create_qdrant_client
from codegraph_shared.infra.vector.qdrant import QdrantAdapter


@pytest.mark.asyncio
@pytest.mark.integration
class TestQdrantModesIntegration:
    """실제 Qdrant 클라이언트 통합 테스트."""

    async def test_memory_mode_full_lifecycle(self):
        """Memory 모드 전체 라이프사이클."""
        client = create_qdrant_client(mode="memory")

        try:
            # 1. 연결 확인
            collections = await client.get_collections()
            assert collections is not None
            assert hasattr(collections, "collections")

            # 2. 컬렉션 생성
            test_collection = "test_memory_collection"
            await client.create_collection(
                collection_name=test_collection,
                vectors_config=VectorParams(size=128, distance=Distance.COSINE),
            )

            # 3. 컬렉션 존재 확인
            collections = await client.get_collections()
            collection_names = [c.name for c in collections.collections]
            assert test_collection in collection_names

            # 4. 벡터 삽입
            from qdrant_client.models import PointStruct

            await client.upsert(
                collection_name=test_collection,
                points=[PointStruct(id=1, vector=[0.1] * 128, payload={"test": "data"})],
            )

            # 5. 검색
            results = await client.search(collection_name=test_collection, query_vector=[0.1] * 128, limit=1)
            assert len(results) == 1
            assert results[0].payload["test"] == "data"

            # 6. 점 조회
            points = await client.retrieve(collection_name=test_collection, ids=[1])
            assert len(points) == 1
            assert points[0].id == 1

            # 7. 점 삭제
            await client.delete(
                collection_name=test_collection,
                points_selector=[1],
            )

            # 8. 컬렉션 삭제
            await client.delete_collection(collection_name=test_collection)

            # 9. 삭제 확인
            collections = await client.get_collections()
            collection_names = [c.name for c in collections.collections]
            assert test_collection not in collection_names

        finally:
            await client.close()

    async def test_embedded_mode_persistence(self, tmp_path):
        """Embedded 모드는 재시작 후에도 데이터 유지."""
        import uuid

        from codegraph_shared.infra.vector import _LockFileManager

        storage_path = tmp_path / "qdrant_persist_test"
        test_collection = "persist_test"
        test_id = str(uuid.uuid4())  # ✅ UUID 사용

        # Phase 1: 데이터 저장
        client1 = create_qdrant_client(mode="embedded", storage_path=str(storage_path))
        try:
            await client1.create_collection(
                collection_name=test_collection,
                vectors_config=VectorParams(size=64, distance=Distance.COSINE),
            )

            from qdrant_client.models import PointStruct

            await client1.upsert(
                collection_name=test_collection,
                points=[PointStruct(id=test_id, vector=[0.5] * 64, payload={"persisted": True})],
            )

            # 데이터 확인
            points = await client1.retrieve(collection_name=test_collection, ids=[test_id])
            assert len(points) == 1
            assert points[0].payload["persisted"] is True

        finally:
            await client1.close()
            _LockFileManager.release_lock(storage_path)

        # Phase 2: 재시작 후 데이터 확인
        client2 = create_qdrant_client(mode="embedded", storage_path=str(storage_path))
        try:
            # 컬렉션 존재 확인
            collections = await client2.get_collections()
            collection_names = [c.name for c in collections.collections]
            assert test_collection in collection_names

            # 데이터 존재 확인
            points = await client2.retrieve(collection_name=test_collection, ids=[test_id])
            assert len(points) == 1
            assert points[0].id == test_id
            assert points[0].payload["persisted"] is True

            # 검색으로도 확인
            results = await client2.search(collection_name=test_collection, query_vector=[0.5] * 64, limit=1)
            assert len(results) > 0
            assert results[0].payload["persisted"] is True

        finally:
            await client2.close()
            _LockFileManager.release_lock(storage_path)

    async def test_embedded_mode_multiple_collections(self, tmp_path):
        """Embedded 모드에서 여러 컬렉션 관리."""
        storage_path = tmp_path / "multi_collection_test"
        client = create_qdrant_client(mode="embedded", storage_path=str(storage_path))

        try:
            collections_to_create = ["col1", "col2", "col3"]

            # 여러 컬렉션 생성
            for col_name in collections_to_create:
                await client.create_collection(
                    collection_name=col_name,
                    vectors_config=VectorParams(size=32, distance=Distance.COSINE),
                )

            # 모든 컬렉션 확인
            collections = await client.get_collections()
            collection_names = [c.name for c in collections.collections]

            for col_name in collections_to_create:
                assert col_name in collection_names

            # 각 컬렉션에 데이터 삽입
            from qdrant_client.models import PointStruct

            for i, col_name in enumerate(collections_to_create):
                await client.upsert(
                    collection_name=col_name,
                    points=[PointStruct(id=i + 1, vector=[float(i)] * 32, payload={"col": col_name})],
                )

            # 각 컬렉션 데이터 확인
            for i, col_name in enumerate(collections_to_create):
                points = await client.retrieve(collection_name=col_name, ids=[i + 1])
                assert len(points) == 1
                assert points[0].payload["col"] == col_name

        finally:
            await client.close()

    async def test_adapter_memory_mode_operations(self):
        """QdrantAdapter memory 모드 통합 테스트."""
        import uuid

        adapter = QdrantAdapter(mode="memory", collection="test_adapter")

        # ✅ UUID 생성
        test_id_1 = str(uuid.uuid4())
        test_id_2 = str(uuid.uuid4())

        try:
            # Healthcheck
            is_healthy = await adapter.healthcheck()
            assert is_healthy is True

            # Collection 자동 생성 및 upsert
            await adapter.upsert_vectors(
                [
                    {
                        "id": test_id_1,
                        "vector": [0.1] * 1024,
                        "payload": {"source": "test", "index": 1},
                    },
                    {
                        "id": test_id_2,
                        "vector": [0.2] * 1024,
                        "payload": {"source": "test", "index": 2},
                    },
                ]
            )

            # Count
            count = await adapter.count()
            assert count == 2

            # Search
            results = await adapter.search(query_vector=[0.1] * 1024, limit=2)
            assert len(results) == 2
            assert all("source" in r["payload"] for r in results)

            # Get by ID
            point = await adapter.get_by_id(test_id_1)
            assert point is not None
            assert point["id"] == test_id_1
            assert point["payload"]["index"] == 1

            # Delete by ID
            await adapter.delete_by_id([test_id_1])
            count_after_delete = await adapter.count()
            assert count_after_delete == 1

        finally:
            await adapter.close()

    async def test_adapter_embedded_mode_with_filters(self, tmp_path):
        """QdrantAdapter embedded 모드 필터링 테스트."""
        storage_path = tmp_path / "filter_test"
        adapter = QdrantAdapter(
            mode="embedded",
            storage_path=str(storage_path),
            collection="filtered_collection",
        )

        try:
            # 다양한 payload로 벡터 삽입
            await adapter.upsert_vectors(
                [
                    {
                        "id": f"doc-{i}",
                        "vector": [float(i) / 10] * 1024,
                        "payload": {"category": "A" if i < 5 else "B", "value": i},
                    }
                    for i in range(10)
                ]
            )

            # 전체 검색
            all_results = await adapter.search(query_vector=[0.3] * 1024, limit=10)
            assert len(all_results) == 10

            # 필터 검색 (category=A)
            from qdrant_client.models import FieldCondition, Filter, MatchValue

            filter_a = Filter(must=[FieldCondition(key="category", match=MatchValue(value="A"))])
            results_a = await adapter.search(query_vector=[0.3] * 1024, limit=10, filter_dict=filter_a)
            assert len(results_a) == 5
            assert all(r["payload"]["category"] == "A" for r in results_a)

            # 필터 검색 (value >= 5)
            from qdrant_client.models import Range

            filter_range = Filter(must=[FieldCondition(key="value", range=Range(gte=5))])
            results_range = await adapter.search(query_vector=[0.7] * 1024, limit=10, filter_dict=filter_range)
            assert len(results_range) == 5
            assert all(r["payload"]["value"] >= 5 for r in results_range)

        finally:
            await adapter.close()

    async def test_memory_mode_concurrent_operations(self):
        """Memory 모드 동시 작업 테스트."""
        adapter = QdrantAdapter(mode="memory", collection="concurrent_test")

        try:
            # 동시에 여러 벡터 삽입
            tasks = []
            for i in range(10):
                task = adapter.upsert_vectors(
                    [
                        {
                            "id": f"concurrent-{i}",
                            "vector": [float(i)] * 1024,
                            "payload": {"batch": i},
                        }
                    ]
                )
                tasks.append(task)

            await asyncio.gather(*tasks)

            # 모든 데이터 확인
            count = await adapter.count()
            assert count == 10

        finally:
            await adapter.close()


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.server
class TestServerModeIntegration:
    """Server 모드 통합 테스트 (Docker 필요)."""

    async def test_server_mode_connection(self):
        """Server 모드 연결 테스트."""
        try:
            client = create_qdrant_client(mode="server", url="http://localhost:6333")
            collections = await client.get_collections()
            assert collections is not None
            await client.close()
        except Exception as e:
            pytest.skip(f"Server mode requires Docker: {e}")

    async def test_server_mode_with_grpc(self):
        """Server 모드 gRPC 연결 테스트."""
        try:
            client = create_qdrant_client(
                mode="server",
                host="localhost",
                port=6333,
                grpc_port=6334,
                prefer_grpc=True,
            )

            test_collection = "grpc_test"
            await client.create_collection(
                collection_name=test_collection,
                vectors_config=VectorParams(size=128, distance=Distance.COSINE),
            )

            from qdrant_client.models import PointStruct

            # Bulk insert (gRPC should be faster)
            points = [PointStruct(id=i, vector=[0.1] * 128, payload={"index": i}) for i in range(100)]

            await client.upsert(collection_name=test_collection, points=points)

            # Verify
            count_result = await client.count(collection_name=test_collection)
            assert count_result.count == 100

            # Cleanup
            await client.delete_collection(collection_name=test_collection)
            await client.close()

        except Exception as e:
            pytest.skip(f"Server mode requires Docker: {e}")
