"""
Unit tests for QdrantAdapter validation logic.

Tests all parameter validation and edge cases.
"""

from unittest.mock import AsyncMock, patch

import pytest

from codegraph_shared.infra.vector.qdrant import QdrantAdapter


class TestQdrantAdapterValidation:
    """QdrantAdapter 초기화 검증 테스트."""

    def test_valid_memory_mode(self):
        """Memory 모드는 최소한의 파라미터로 생성."""
        adapter = QdrantAdapter(mode="memory")
        assert adapter.mode == "memory"
        assert adapter.collection == "codegraph"

    def test_valid_embedded_mode(self):
        """Embedded 모드는 storage_path와 함께 생성."""
        adapter = QdrantAdapter(mode="embedded", storage_path="./data/test")
        assert adapter.mode == "embedded"
        assert adapter.storage_path == "./data/test"

    def test_valid_server_mode(self):
        """Server 모드는 host/port와 함께 생성."""
        adapter = QdrantAdapter(mode="server", host="qdrant", port=6333)
        assert adapter.mode == "server"
        assert adapter.host == "qdrant"
        assert adapter.port == 6333

    def test_invalid_mode_raises(self):
        """유효하지 않은 mode는 ValueError."""
        with pytest.raises(ValueError, match="Invalid mode"):
            QdrantAdapter(mode="invalid_mode")

    @pytest.mark.parametrize(
        "invalid_mode",
        ["MEMORY", "Embedded", "SERVER", " memory", "mem", "", "unknown"],
    )
    def test_invalid_mode_variations(self, invalid_mode):
        """다양한 잘못된 mode 입력."""
        with pytest.raises(ValueError, match="Invalid mode"):
            QdrantAdapter(mode=invalid_mode)

    def test_embedded_without_storage_path_raises(self):
        """Embedded 모드에서 storage_path 누락 시 에러."""
        with pytest.raises(ValueError, match="storage_path is required"):
            QdrantAdapter(mode="embedded", storage_path="")

    def test_embedded_with_whitespace_storage_path_raises(self):
        """Embedded 모드에서 공백만 있는 storage_path는 에러."""
        with pytest.raises(ValueError, match="storage_path is required"):
            QdrantAdapter(mode="embedded", storage_path="   ")

    def test_server_without_host_raises(self):
        """Server 모드에서 host 누락 시 에러."""
        with pytest.raises(ValueError, match="host is required"):
            QdrantAdapter(mode="server", host="")

    def test_server_with_whitespace_host_raises(self):
        """Server 모드에서 공백만 있는 host는 에러."""
        with pytest.raises(ValueError, match="host is required"):
            QdrantAdapter(mode="server", host="   ")

    @pytest.mark.parametrize("invalid_port", [0, -1, -100, 65536, 99999, 100000])
    def test_server_invalid_port_raises(self, invalid_port):
        """Server 모드에서 잘못된 포트는 에러."""
        with pytest.raises(ValueError, match="Invalid port"):
            QdrantAdapter(mode="server", host="localhost", port=invalid_port)

    @pytest.mark.parametrize("valid_port", [1, 80, 443, 6333, 8080, 65535])
    def test_server_valid_port_accepted(self, valid_port):
        """Server 모드에서 유효한 포트는 허용."""
        adapter = QdrantAdapter(mode="server", host="localhost", port=valid_port)
        assert adapter.port == valid_port

    @pytest.mark.parametrize("invalid_grpc_port", [0, -1, 65536, 70000])
    def test_server_invalid_grpc_port_raises(self, invalid_grpc_port):
        """Server 모드에서 잘못된 gRPC 포트는 에러."""
        with pytest.raises(ValueError, match="Invalid grpc_port"):
            QdrantAdapter(mode="server", host="localhost", grpc_port=invalid_grpc_port)

    def test_empty_collection_name_raises(self):
        """빈 collection 이름은 에러."""
        with pytest.raises(ValueError, match="collection name is required"):
            QdrantAdapter(collection="")

    def test_whitespace_collection_name_raises(self):
        """공백만 있는 collection 이름은 에러."""
        with pytest.raises(ValueError, match="collection name is required"):
            QdrantAdapter(collection="   ")

    def test_too_long_collection_name_raises(self):
        """255자보다 긴 collection 이름은 에러."""
        long_name = "a" * 256
        with pytest.raises(ValueError, match="collection name too long"):
            QdrantAdapter(collection=long_name)

    def test_max_length_collection_name_accepted(self):
        """255자 collection 이름은 허용."""
        max_name = "a" * 255
        adapter = QdrantAdapter(collection=max_name)
        assert adapter.collection == max_name

    @pytest.mark.parametrize("invalid_concurrency", [0, -1, 17, 20, 100])
    def test_invalid_upsert_concurrency_raises(self, invalid_concurrency):
        """잘못된 upsert_concurrency는 에러."""
        with pytest.raises(ValueError, match="Invalid upsert_concurrency"):
            QdrantAdapter(upsert_concurrency=invalid_concurrency)

    @pytest.mark.parametrize("valid_concurrency", [1, 4, 8, 16])
    def test_valid_upsert_concurrency_accepted(self, valid_concurrency):
        """유효한 upsert_concurrency는 허용."""
        adapter = QdrantAdapter(upsert_concurrency=valid_concurrency)
        assert adapter.upsert_concurrency == valid_concurrency


class TestQdrantAdapterClientCreation:
    """QdrantAdapter 클라이언트 생성 테스트."""

    @pytest.mark.asyncio
    async def test_memory_mode_client_creation(self):
        """Memory 모드 클라이언트 생성."""
        adapter = QdrantAdapter(mode="memory")

        with patch("src.infra.vector.create_qdrant_client") as mock_helper:
            mock_helper.return_value = AsyncMock()
            client = await adapter._get_client()

            mock_helper.assert_called_once_with(
                mode="memory",
                storage_path=adapter.storage_path,
                host=adapter.host,
                port=adapter.port,
                grpc_port=adapter.grpc_port,
                prefer_grpc=adapter.prefer_grpc,
            )
            assert client is not None

    @pytest.mark.asyncio
    async def test_embedded_mode_client_creation(self):
        """Embedded 모드 클라이언트 생성."""
        adapter = QdrantAdapter(mode="embedded", storage_path="./data/test")

        with patch("src.infra.vector.create_qdrant_client") as mock_helper:
            mock_helper.return_value = AsyncMock()
            client = await adapter._get_client()

            mock_helper.assert_called_once()
            call_kwargs = mock_helper.call_args.kwargs
            assert call_kwargs["mode"] == "embedded"
            assert call_kwargs["storage_path"] == "./data/test"

    @pytest.mark.asyncio
    async def test_server_mode_client_creation(self):
        """Server 모드 클라이언트 생성."""
        adapter = QdrantAdapter(
            mode="server",
            host="qdrant.example.com",
            port=6333,
            grpc_port=6334,
            prefer_grpc=True,
        )

        with patch("src.infra.vector.create_qdrant_client") as mock_helper:
            mock_helper.return_value = AsyncMock()
            client = await adapter._get_client()

            call_kwargs = mock_helper.call_args.kwargs
            assert call_kwargs["mode"] == "server"
            assert call_kwargs["host"] == "qdrant.example.com"
            assert call_kwargs["port"] == 6333
            assert call_kwargs["prefer_grpc"] is True

    @pytest.mark.asyncio
    async def test_client_lazy_initialization(self):
        """클라이언트는 lazy initialization (첫 호출 시만 생성)."""
        adapter = QdrantAdapter(mode="memory")

        with patch("src.infra.vector.create_qdrant_client") as mock_helper:
            mock_helper.return_value = AsyncMock()

            # 첫 번째 호출
            client1 = await adapter._get_client()
            assert mock_helper.call_count == 1

            # 두 번째 호출 (캐시됨)
            client2 = await adapter._get_client()
            assert mock_helper.call_count == 1  # 여전히 1번

            assert client1 is client2  # 동일 인스턴스


class TestQdrantAdapterDefaults:
    """QdrantAdapter 기본값 테스트."""

    def test_default_mode_is_embedded(self):
        """기본 모드는 embedded."""
        adapter = QdrantAdapter()
        assert adapter.mode == "embedded"

    def test_default_storage_path(self):
        """기본 storage_path."""
        adapter = QdrantAdapter()
        assert adapter.storage_path == "./data/qdrant_storage"

    def test_default_host(self):
        """기본 host는 localhost."""
        adapter = QdrantAdapter(mode="server")
        assert adapter.host == "localhost"

    def test_default_ports(self):
        """기본 포트 확인."""
        adapter = QdrantAdapter(mode="server")
        assert adapter.port == 6333
        assert adapter.grpc_port == 6334

    def test_default_collection(self):
        """기본 collection은 codegraph."""
        adapter = QdrantAdapter()
        assert adapter.collection == "codegraph"

    def test_default_prefer_grpc(self):
        """기본값으로 gRPC 선호."""
        adapter = QdrantAdapter(mode="server")
        assert adapter.prefer_grpc is True

    def test_default_upsert_concurrency(self):
        """기본 upsert_concurrency는 4."""
        adapter = QdrantAdapter()
        assert adapter.upsert_concurrency == 4
