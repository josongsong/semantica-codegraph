"""
End-to-End system integration test.

Verifies Qdrant modes work with the full application stack.
"""

import uuid
from pathlib import Path

import pytest

from codegraph_engine.code_foundation.infrastructure.chunk.store import ChunkStore
from codegraph_shared.infra.config.settings import Settings
from codegraph_shared.infra.di import InfraContainer


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.e2e
class TestSystemIntegrationE2E:
    """전체 시스템 통합 테스트."""

    async def test_full_stack_memory_mode(self):
        """전체 스택이 memory 모드로 동작."""
        settings = Settings(
            qdrant_mode="memory",
            database_url="sqlite+aiosqlite:///:memory:",
        )

        infra = InfraContainer(settings)

        try:
            # 1. Qdrant 확인
            qdrant = infra.qdrant
            assert qdrant.mode == "memory"

            is_healthy = await qdrant.healthcheck()
            assert is_healthy is True

            # 2. 실제 벡터 작업
            test_vectors = [
                {
                    "id": str(uuid.uuid4()),
                    "vector": [float(i) / 10] * 1024,
                    "payload": {
                        "repo_id": "test-repo",
                        "file_path": f"/test/file{i}.py",
                        "chunk_index": i,
                    },
                }
                for i in range(10)
            ]

            await qdrant.upsert_vectors(test_vectors)

            # 3. 검색 작업
            results = await qdrant.search(
                query_vector=[0.5] * 1024,
                limit=5,
            )

            assert len(results) == 5
            assert all("repo_id" in r["payload"] for r in results)

            # 4. Count 확인
            count = await qdrant.count()
            assert count == 10

        finally:
            await qdrant.close()

    async def test_full_stack_embedded_mode(self, tmp_path):
        """전체 스택이 embedded 모드로 동작."""
        storage_path = tmp_path / "e2e_embedded"

        settings = Settings(
            qdrant_mode="embedded",
            qdrant_storage_path=str(storage_path),
            database_url="sqlite+aiosqlite:///:memory:",
        )

        infra = InfraContainer(settings)

        try:
            # 1. Qdrant 확인
            qdrant = infra.qdrant
            assert qdrant.mode == "embedded"

            # Lazy initialization 트리거 (디렉토리 생성됨)
            await qdrant.healthcheck()
            assert storage_path.exists()

            # 2. 실제 작업 시뮬레이션
            test_vectors = [
                {
                    "id": str(uuid.uuid4()),
                    "vector": [0.1] * 1024,
                    "payload": {
                        "repo_id": "real-repo",
                        "file_path": "/src/main.py",
                        "content": "def main(): pass",
                        "language": "python",
                    },
                }
            ]

            await qdrant.upsert_vectors(test_vectors)

            # 3. 검색 및 검증
            results = await qdrant.search(
                query_vector=[0.1] * 1024,
                limit=1,
            )

            assert len(results) == 1
            assert results[0]["payload"]["language"] == "python"

        finally:
            await qdrant.close()

    async def test_container_lifecycle_complete(self, tmp_path):
        """컨테이너 전체 생명주기."""
        from codegraph_shared.infra.vector import _LockFileManager

        storage_path = tmp_path / "lifecycle_test"

        settings = Settings(
            qdrant_mode="embedded",
            qdrant_storage_path=str(storage_path),
        )

        # Phase 1: 컨테이너 생성 및 작업
        infra1 = InfraContainer(settings)
        qdrant1 = infra1.qdrant

        try:
            await qdrant1.upsert_vectors(
                [
                    {
                        "id": str(uuid.uuid4()),
                        "vector": [0.5] * 1024,
                        "payload": {"lifecycle": "phase1"},
                    }
                ]
            )

            count1 = await qdrant1.count()
            assert count1 == 1

        finally:
            await qdrant1.close()
            _LockFileManager.release_lock(storage_path)

        # Phase 2: 새 컨테이너로 데이터 확인
        infra2 = InfraContainer(settings)
        qdrant2 = infra2.qdrant

        try:
            count2 = await qdrant2.count()
            assert count2 == 1

            results = await qdrant2.search(query_vector=[0.5] * 1024, limit=1)
            assert len(results) == 1
            assert results[0]["payload"]["lifecycle"] == "phase1"

        finally:
            await qdrant2.close()
            _LockFileManager.release_lock(storage_path)

    async def test_qdrant_async_direct_access(self):
        """qdrant_async 프로퍼티 직접 사용."""
        settings = Settings(qdrant_mode="memory")
        infra = InfraContainer(settings)

        try:
            # AsyncQdrantClient 직접 접근
            client = infra.qdrant_async

            # 컬렉션 생성
            from qdrant_client.models import Distance, VectorParams

            test_collection = "direct_access_test"
            await client.create_collection(
                collection_name=test_collection,
                vectors_config=VectorParams(size=256, distance=Distance.COSINE),
            )

            # 벡터 삽입
            from qdrant_client.models import PointStruct

            await client.upsert(
                collection_name=test_collection,
                points=[PointStruct(id=str(uuid.uuid4()), vector=[0.1] * 256) for _ in range(10)],
            )

            # 검색
            results = await client.search(
                collection_name=test_collection,
                query_vector=[0.1] * 256,
                limit=5,
            )

            assert len(results) == 5

        finally:
            await client.close()

    async def test_multiple_modes_different_containers(self, tmp_path):
        """서로 다른 모드로 독립적인 컨테이너들."""
        # Memory container
        settings_memory = Settings(qdrant_mode="memory")
        infra_memory = InfraContainer(settings_memory)

        # Embedded container
        settings_embedded = Settings(
            qdrant_mode="embedded",
            qdrant_storage_path=str(tmp_path / "multi_mode_test"),
        )
        infra_embedded = InfraContainer(settings_embedded)

        try:
            # 각각 독립적으로 동작
            await infra_memory.qdrant.upsert_vectors(
                [
                    {
                        "id": str(uuid.uuid4()),
                        "vector": [0.1] * 1024,
                        "payload": {"mode": "memory"},
                    }
                ]
            )

            await infra_embedded.qdrant.upsert_vectors(
                [
                    {
                        "id": str(uuid.uuid4()),
                        "vector": [0.2] * 1024,
                        "payload": {"mode": "embedded"},
                    }
                ]
            )

            # 각각 count 확인
            count_memory = await infra_memory.qdrant.count()
            count_embedded = await infra_embedded.qdrant.count()

            assert count_memory == 1
            assert count_embedded == 1

        finally:
            await infra_memory.qdrant.close()
            await infra_embedded.qdrant.close()
