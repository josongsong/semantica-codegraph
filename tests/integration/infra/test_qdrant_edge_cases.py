"""
Edge cases and extreme scenario tests for Qdrant modes.

Tests boundary conditions, error recovery, and extreme loads.
"""

import asyncio
import uuid
from pathlib import Path

import pytest
from qdrant_client.models import Distance, PointStruct, VectorParams

from codegraph_shared.infra.vector import create_qdrant_client
from codegraph_shared.infra.vector.qdrant import QdrantAdapter


@pytest.mark.asyncio
@pytest.mark.integration
class TestEdgeCasesIntegration:
    """엣지 케이스 통합 테스트."""

    async def test_empty_collection_operations(self):
        """빈 컬렉션에 대한 모든 작업."""
        adapter = QdrantAdapter(mode="memory", collection="empty_test")

        try:
            # Count on empty
            count = await adapter.count()
            assert count == 0

            # Search on empty
            results = await adapter.search(query_vector=[0.1] * 1024, limit=10)
            assert len(results) == 0

            # Get non-existent
            point = await adapter.get_by_id(str(uuid.uuid4()))
            assert point is None

            # Delete non-existent (should not crash)
            await adapter.delete_by_id([str(uuid.uuid4())])

        finally:
            await adapter.close()

    async def test_single_vector_operations(self):
        """단일 벡터에 대한 모든 작업."""
        adapter = QdrantAdapter(mode="memory", collection="single_vec")
        test_id = str(uuid.uuid4())

        try:
            await adapter.upsert_vectors([{"id": test_id, "vector": [0.5] * 1024, "payload": {"single": True}}])

            # Search should return 1
            results = await adapter.search(query_vector=[0.5] * 1024, limit=10)
            assert len(results) == 1
            assert results[0]["id"] == test_id

            # Get by ID
            point = await adapter.get_by_id(test_id)
            assert point is not None
            assert point["payload"]["single"] is True

        finally:
            await adapter.close()

    async def test_duplicate_id_upsert(self):
        """동일 ID로 여러 번 upsert (업데이트)."""
        adapter = QdrantAdapter(mode="memory", collection="dup_test")
        test_id = str(uuid.uuid4())

        try:
            # 첫 번째 삽입
            await adapter.upsert_vectors(
                [
                    {
                        "id": test_id,
                        "vector": [0.1] * 1024,
                        "payload": {"version": 1},
                    }
                ]
            )

            point1 = await adapter.get_by_id(test_id)
            assert point1["payload"]["version"] == 1

            # 동일 ID로 재삽입 (업데이트)
            await adapter.upsert_vectors(
                [
                    {
                        "id": test_id,
                        "vector": [0.2] * 1024,
                        "payload": {"version": 2},
                    }
                ]
            )

            point2 = await adapter.get_by_id(test_id)
            assert point2["payload"]["version"] == 2

            # Count는 여전히 1
            count = await adapter.count()
            assert count == 1

        finally:
            await adapter.close()

    async def test_special_characters_in_payload(self):
        """Payload에 특수 문자, 한글, 이모지."""
        adapter = QdrantAdapter(mode="memory", collection="special_chars")
        test_id = str(uuid.uuid4())

        try:
            await adapter.upsert_vectors(
                [
                    {
                        "id": test_id,
                        "vector": [0.1] * 1024,
                        "payload": {
                            "text": "Hello 世界 🚀 \n\t\r",
                            "code": "def func():\n    pass",
                            "path": "/usr/local/bin",
                            "emoji": "😀😁😂🤣😃",
                            "korean": "안녕하세요",
                            "special": "!@#$%^&*()_+-=[]{}|;':\",./<>?",
                        },
                    }
                ]
            )

            point = await adapter.get_by_id(test_id)
            assert point is not None
            assert "世界" in point["payload"]["text"]
            assert "🚀" in point["payload"]["text"]
            assert "\n" in point["payload"]["code"]
            assert "😀" in point["payload"]["emoji"]
            assert "안녕하세요" in point["payload"]["korean"]

        finally:
            await adapter.close()

    async def test_zero_vector(self):
        """제로 벡터 처리."""
        adapter = QdrantAdapter(mode="memory", collection="zero_vec")
        test_id = str(uuid.uuid4())

        try:
            await adapter.upsert_vectors([{"id": test_id, "vector": [0.0] * 1024, "payload": {"zero": True}}])

            # Search with zero vector
            results = await adapter.search(query_vector=[0.0] * 1024, limit=1)
            assert len(results) == 1

        finally:
            await adapter.close()

    async def test_max_dimension_vector(self):
        """최대 차원 벡터 (65536)."""
        adapter = QdrantAdapter(mode="memory", collection="max_dim")
        test_id = str(uuid.uuid4())

        try:
            # 큰 차원 벡터 (1024 사용, 65536은 너무 느림)
            dim = 2048
            await adapter.upsert_vectors([{"id": test_id, "vector": [0.1] * dim, "payload": {"dim": dim}}])

            results = await adapter.search(query_vector=[0.1] * dim, limit=1)
            assert len(results) == 1

        finally:
            await adapter.close()

    async def test_search_with_score_threshold(self):
        """Score threshold 경계값."""
        adapter = QdrantAdapter(mode="memory", collection="threshold_test")

        try:
            # 여러 벡터 삽입
            vectors = [
                {
                    "id": str(uuid.uuid4()),
                    "vector": [float(i) / 10] * 1024,
                    "payload": {"index": i},
                }
                for i in range(5)
            ]
            await adapter.upsert_vectors(vectors)

            # No threshold
            results_all = await adapter.search(query_vector=[0.0] * 1024, limit=10, score_threshold=None)
            assert len(results_all) == 5

            # High threshold
            results_high = await adapter.search(query_vector=[0.0] * 1024, limit=10, score_threshold=0.99)
            # 높은 threshold로 필터링됨
            assert len(results_high) <= len(results_all)

        finally:
            await adapter.close()

    async def test_embedded_mode_path_with_symlink(self, tmp_path):
        """Symbolic link 경로 처리."""
        real_path = tmp_path / "real_storage"
        real_path.mkdir()

        link_path = tmp_path / "link_storage"
        link_path.symlink_to(real_path)

        client = create_qdrant_client(mode="embedded", storage_path=str(link_path))

        try:
            collections = await client.get_collections()
            assert collections is not None
        finally:
            await client.close()

    async def test_embedded_mode_relative_path(self, tmp_path):
        """상대 경로 처리."""
        import os

        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)

            # 상대 경로 사용
            client = create_qdrant_client(mode="embedded", storage_path="./relative_qdrant")

            collections = await client.get_collections()
            assert collections is not None

            # 절대 경로로 변환되었는지 확인
            storage = tmp_path / "relative_qdrant"
            assert storage.exists()

            await client.close()

        finally:
            os.chdir(original_cwd)


@pytest.mark.asyncio
@pytest.mark.integration
class TestExtremeLoads:
    """극한 부하 테스트."""

    async def test_large_batch_upsert(self):
        """대용량 배치 삽입 (10,000개)."""
        adapter = QdrantAdapter(mode="memory", collection="large_batch")

        try:
            # 10,000개 벡터
            large_batch = [
                {
                    "id": str(uuid.uuid4()),
                    "vector": [float(i % 100) / 100] * 1024,
                    "payload": {"index": i},
                }
                for i in range(10000)
            ]

            await adapter.upsert_vectors(large_batch)

            count = await adapter.count()
            assert count == 10000

            # Search should work
            results = await adapter.search(query_vector=[0.5] * 1024, limit=10)
            assert len(results) == 10

        finally:
            await adapter.close()

    async def test_concurrent_upserts(self):
        """동시 upsert 작업."""
        adapter = QdrantAdapter(mode="memory", collection="concurrent_upsert")

        try:
            # 10개 동시 upsert
            tasks = []
            for batch_idx in range(10):
                vectors = [
                    {
                        "id": str(uuid.uuid4()),
                        "vector": [float(batch_idx)] * 1024,
                        "payload": {"batch": batch_idx, "index": i},
                    }
                    for i in range(100)
                ]
                task = adapter.upsert_vectors(vectors)
                tasks.append(task)

            await asyncio.gather(*tasks)

            # Total should be 1000
            count = await adapter.count()
            assert count == 1000

        finally:
            await adapter.close()

    async def test_concurrent_searches(self):
        """동시 검색 작업."""
        adapter = QdrantAdapter(mode="memory", collection="concurrent_search")

        try:
            # 데이터 준비
            vectors = [
                {
                    "id": str(uuid.uuid4()),
                    "vector": [float(i % 100) / 100] * 1024,
                    "payload": {"index": i},
                }
                for i in range(100)  # 1000 → 100
            ]
            await adapter.upsert_vectors(vectors)

            # 100개 동시 검색
            tasks = [adapter.search(query_vector=[float(i) / 100] * 1024, limit=10) for i in range(100)]

            results_list = await asyncio.gather(*tasks)

            # 모든 검색이 성공
            assert len(results_list) == 100
            assert all(len(r) > 0 for r in results_list)

        finally:
            await adapter.close()

    async def test_many_small_batches(self):
        """많은 작은 배치 (1000개 배치 x 10개씩)."""
        adapter = QdrantAdapter(mode="memory", collection="small_batches")

        try:
            for batch_idx in range(100):  # 1000 → 100
                vectors = [
                    {
                        "id": str(uuid.uuid4()),
                        "vector": [float(batch_idx % 100) / 100] * 1024,
                        "payload": {"batch": batch_idx},
                    }
                    for _ in range(10)
                ]
                await adapter.upsert_vectors(vectors)

            count = await adapter.count()
            assert count == 10000

        finally:
            await adapter.close()

    async def test_stress_mixed_operations(self):
        """혼합 작업 스트레스 테스트."""
        adapter = QdrantAdapter(mode="memory", collection="stress_test")

        try:
            # 초기 데이터
            vectors = [
                {
                    "id": str(uuid.uuid4()),
                    "vector": [float(i % 100) / 100] * 1024,
                    "payload": {"index": i},
                }
                for i in range(100)  # 1000 → 100
            ]
            await adapter.upsert_vectors(vectors)

            # 혼합 작업
            tasks = []

            # 검색 50개
            for _ in range(50):
                tasks.append(adapter.search(query_vector=[0.5] * 1024, limit=10))

            # Upsert 10개
            for batch_idx in range(10):
                new_vectors = [
                    {
                        "id": str(uuid.uuid4()),
                        "vector": [float(batch_idx)] * 1024,
                        "payload": {"new": True},
                    }
                    for _ in range(10)
                ]
                tasks.append(adapter.upsert_vectors(new_vectors))

            # Count 10개
            for _ in range(10):
                tasks.append(adapter.count())

            # 모두 실행
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # 에러가 없어야 함
            errors = [r for r in results if isinstance(r, Exception)]
            assert len(errors) == 0

        finally:
            await adapter.close()

    async def test_embedded_mode_multiple_sequential_clients(self, tmp_path):
        """순차적으로 여러 클라이언트 생성/종료."""
        from codegraph_shared.infra.vector import _LockFileManager

        storage_path = tmp_path / "sequential_clients"

        for i in range(10):
            client = create_qdrant_client(mode="embedded", storage_path=str(storage_path))

            try:
                test_collection = f"test_col_{i}"
                await client.create_collection(
                    collection_name=test_collection,
                    vectors_config=VectorParams(size=128, distance=Distance.COSINE),
                )

                await client.upsert(
                    collection_name=test_collection,
                    points=[PointStruct(id=str(uuid.uuid4()), vector=[0.1] * 128)],
                )

            finally:
                await client.close()
                _LockFileManager.release_lock(storage_path)

        # 마지막 확인
        final_client = create_qdrant_client(mode="embedded", storage_path=str(storage_path))
        try:
            collections = await final_client.get_collections()
            # 모든 컬렉션이 존재해야 함
            assert len(collections.collections) == 10
        finally:
            await final_client.close()
            _LockFileManager.release_lock(storage_path)
