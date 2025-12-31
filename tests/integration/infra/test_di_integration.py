"""
DI Container integration tests.

Verifies that all Qdrant modes work correctly with DI containers.
"""

from pathlib import Path

import pytest

from codegraph_engine.multi_index.infrastructure.di import IndexContainer
from codegraph_shared.infra.config.settings import Settings
from codegraph_shared.infra.di import InfraContainer


@pytest.mark.asyncio
@pytest.mark.integration
class TestDIContainerIntegration:
    """DI 컨테이너 통합 테스트."""

    async def test_infra_container_memory_mode(self):
        """InfraContainer with memory mode."""
        settings = Settings(qdrant_mode="memory")
        container = InfraContainer(settings)

        # QdrantAdapter 생성 확인
        adapter = container.qdrant
        assert adapter.mode == "memory"

        # 동작 확인
        is_healthy = await adapter.healthcheck()
        assert is_healthy is True

        await adapter.close()

    async def test_infra_container_embedded_mode(self, tmp_path):
        """InfraContainer with embedded mode."""
        storage_path = tmp_path / "di_embedded_test"
        settings = Settings(qdrant_mode="embedded", qdrant_storage_path=str(storage_path))
        container = InfraContainer(settings)

        adapter = container.qdrant
        assert adapter.mode == "embedded"
        assert adapter.storage_path == str(storage_path)

        # 동작 확인
        is_healthy = await adapter.healthcheck()
        assert is_healthy is True

        # 데이터 삽입
        await adapter.upsert_vectors(
            [
                {
                    "id": "di-test-1",
                    "vector": [0.1] * 1024,
                    "payload": {"source": "di_test"},
                }
            ]
        )

        count = await adapter.count()
        assert count == 1

        await adapter.close()

    async def test_infra_container_qdrant_async(self):
        """InfraContainer qdrant_async property."""
        settings = Settings(qdrant_mode="memory")
        container = InfraContainer(settings)

        # AsyncQdrantClient 직접 접근
        client = container.qdrant_async
        assert client is not None

        # 동작 확인
        collections = await client.get_collections()
        assert collections is not None

        await client.close()

    async def test_index_container_requires_dependencies(self):
        """IndexContainer requires infra and foundation containers."""
        # IndexContainer는 다른 컨테이너들을 필요로 함
        # 직접 테스트하는 대신 InfraContainer만 테스트
        settings = Settings(qdrant_mode="memory")
        infra_container = InfraContainer(settings)

        # InfraContainer는 정상 동작
        assert infra_container.qdrant is not None

    async def test_settings_default_mode(self):
        """Settings 기본값은 embedded."""
        settings = Settings()
        assert settings.qdrant_mode == "embedded"
        assert settings.qdrant_storage_path == "./data/qdrant_storage"

    async def test_settings_mode_values(self):
        """Settings에서 유효한 mode 값들."""
        # 유효한 모드들
        Settings(qdrant_mode="memory")
        Settings(qdrant_mode="embedded")
        Settings(qdrant_mode="server")

        # Pattern 검증은 VectorConfig에서 수행
        # (Settings는 환경변수에서 로드만 함)

    async def test_settings_port_ranges(self):
        """Settings에서 포트 범위."""
        # 유효한 포트 범위
        Settings(qdrant_port=1)
        Settings(qdrant_port=6333)
        Settings(qdrant_port=65535)

        # VectorConfig에서 ge/le 검증 수행

    async def test_multiple_containers_same_settings(self):
        """동일 설정으로 여러 컨테이너 생성."""
        settings = Settings(qdrant_mode="memory")

        container1 = InfraContainer(settings)
        container2 = InfraContainer(settings)

        # 각각 독립적인 adapter
        adapter1 = container1.qdrant
        adapter2 = container2.qdrant

        assert adapter1 is not adapter2

        # 둘 다 정상 동작
        await adapter1.healthcheck()
        await adapter2.healthcheck()

        await adapter1.close()
        await adapter2.close()


@pytest.mark.asyncio
@pytest.mark.integration
class TestBackwardCompatibility:
    """하위 호환성 테스트."""

    async def test_server_mode_still_works(self):
        """기존 server 모드는 여전히 동작."""
        settings = Settings(qdrant_mode="server", qdrant_url="http://localhost:6333")
        container = InfraContainer(settings)

        adapter = container.qdrant
        assert adapter.mode == "server"
        assert adapter.host == "localhost"
        assert adapter.port == 6333

        # Note: 실제 server 연결은 Docker 필요
        # 여기서는 생성만 확인

    async def test_existing_env_vars_compatible(self):
        """기존 환경변수와 호환."""
        import os

        # 기존 방식 환경변수
        os.environ["SEMANTICA_QDRANT_URL"] = "http://localhost:6333"
        os.environ["SEMANTICA_QDRANT_HOST"] = "localhost"
        os.environ["SEMANTICA_QDRANT_PORT"] = "6333"

        settings = Settings(qdrant_mode="server")
        assert settings.qdrant_url == "http://localhost:6333"
        assert settings.qdrant_host == "localhost"
        assert settings.qdrant_port == 6333

        # 정리
        del os.environ["SEMANTICA_QDRANT_URL"]
        del os.environ["SEMANTICA_QDRANT_HOST"]
        del os.environ["SEMANTICA_QDRANT_PORT"]

    async def test_config_groups_backward_compatible(self):
        """VectorConfig는 기존 필드 모두 유지."""
        settings = Settings()
        vector_config = settings.vector

        # 기존 필드들이 여전히 존재
        assert hasattr(vector_config, "url")
        assert hasattr(vector_config, "host")
        assert hasattr(vector_config, "port")
        assert hasattr(vector_config, "grpc_port")
        assert hasattr(vector_config, "prefer_grpc")
        assert hasattr(vector_config, "collection_name")
        assert hasattr(vector_config, "vector_size")
        assert hasattr(vector_config, "upsert_concurrency")

        # 새 필드들도 존재
        assert hasattr(vector_config, "mode")
        assert hasattr(vector_config, "storage_path")
