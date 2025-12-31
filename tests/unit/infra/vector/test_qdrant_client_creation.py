"""
Unit tests for Qdrant client creation helper.

Tests all modes, edge cases, and error conditions.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from codegraph_shared.infra.vector import QdrantMode, create_qdrant_client


class TestQdrantClientCreation:
    """create_qdrant_client 헬퍼 함수 단위 테스트."""

    def test_memory_mode_creates_memory_client(self):
        """Memory 모드는 :memory: 경로로 클라이언트 생성."""
        with patch("src.infra.vector.AsyncQdrantClient") as mock_client:
            create_qdrant_client(mode="memory")
            mock_client.assert_called_once_with(":memory:")

    def test_embedded_mode_creates_directory(self, tmp_path):
        """Embedded 모드는 디렉토리를 자동 생성."""
        storage_path = tmp_path / "qdrant_data"

        with patch("src.infra.vector.AsyncQdrantClient") as mock_client:
            create_qdrant_client(mode="embedded", storage_path=str(storage_path))

            # 디렉토리 생성 확인
            assert storage_path.exists()
            assert storage_path.is_dir()

            # 절대 경로로 호출 확인
            mock_client.assert_called_once()
            call_path = mock_client.call_args.kwargs["path"]
            assert Path(call_path).is_absolute()

    def test_embedded_mode_default_path(self, tmp_path):
        """Embedded 모드는 기본 경로를 사용."""
        with patch("src.infra.vector.AsyncQdrantClient") as mock_client:
            # 임시 경로 사용 (lock 충돌 방지)
            storage = tmp_path / "default_path_test"
            create_qdrant_client(mode="embedded", storage_path=str(storage))

            call_path = mock_client.call_args.kwargs["path"]
            assert Path(call_path).is_absolute()

    def test_embedded_mode_invalid_root_path_raises(self):
        """Embedded 모드에서 루트가 유효하지 않으면 에러."""
        # 절대 존재하지 않는 루트 경로
        invalid_path = "/nonexistent_root_12345_super_invalid/parent/qdrant"

        with pytest.raises((FileNotFoundError, ValueError, OSError, PermissionError)):
            create_qdrant_client(mode="embedded", storage_path=invalid_path)

    def test_embedded_mode_permission_error(self, tmp_path):
        """Embedded 모드에서 쓰기 권한 없으면 에러."""
        storage_path = tmp_path / "readonly" / "qdrant"
        storage_path.parent.mkdir(parents=True)

        with patch("pathlib.Path.mkdir", side_effect=PermissionError("No permission")):
            with pytest.raises(PermissionError, match="No write permission"):
                create_qdrant_client(mode="embedded", storage_path=str(storage_path))

    def test_server_mode_with_url(self):
        """Server 모드는 URL로 연결."""
        with patch("src.infra.vector.AsyncQdrantClient") as mock_client:
            create_qdrant_client(mode="server", url="http://qdrant:6333")

            mock_client.assert_called_once_with(url="http://qdrant:6333", timeout=60)

    def test_server_mode_with_host_port(self):
        """Server 모드는 host/port로 연결 (gRPC 포함)."""
        with patch("src.infra.vector.AsyncQdrantClient") as mock_client:
            create_qdrant_client(
                mode="server",
                host="qdrant.example.com",
                port=6333,
                grpc_port=6334,
                prefer_grpc=True,
                timeout=60,
            )

            call_kwargs = mock_client.call_args.kwargs
            assert call_kwargs["host"] == "qdrant.example.com"
            assert call_kwargs["port"] == 6333
            assert call_kwargs["grpc_port"] == 6334
            assert call_kwargs["prefer_grpc"] is True
            assert call_kwargs["timeout"] == 60
            assert "grpc_options" in call_kwargs

    def test_server_mode_url_takes_precedence(self):
        """Server 모드에서 URL이 host보다 우선."""
        with patch("src.infra.vector.AsyncQdrantClient") as mock_client:
            create_qdrant_client(mode="server", url="http://priority:6333", host="ignored", port=9999)

            # URL만 사용, host/port 무시
            mock_client.assert_called_once_with(url="http://priority:6333", timeout=60)

    def test_server_mode_without_host_or_url_raises(self):
        """Server 모드에서 host와 url이 모두 없으면 에러."""
        with pytest.raises(ValueError, match="host or url is required"):
            create_qdrant_client(mode="server", host=None, url=None)

    def test_invalid_mode_raises(self):
        """잘못된 mode는 ValueError."""
        with pytest.raises(ValueError, match="Invalid mode"):
            create_qdrant_client(mode="invalid_mode")

    @pytest.mark.parametrize(
        "invalid_mode",
        [
            "MEMORY",  # 대문자
            "Memory",  # CamelCase
            " memory",  # 앞 공백
            "memory ",  # 뒤 공백
            "",  # 빈 문자열
            "mem",  # 축약형
        ],
    )
    def test_invalid_mode_variations(self, invalid_mode):
        """다양한 잘못된 mode 입력."""
        with pytest.raises(ValueError, match="Invalid mode"):
            create_qdrant_client(mode=invalid_mode)

    @pytest.mark.parametrize("invalid_port", [0, -1, 65536, 99999])
    def test_server_mode_invalid_port_raises(self, invalid_port):
        """Server 모드에서 잘못된 포트는 에러."""
        with pytest.raises(ValueError, match="Invalid port"):
            create_qdrant_client(mode="server", host="localhost", port=invalid_port)

    @pytest.mark.parametrize("invalid_grpc_port", [0, -1, 65536, 99999])
    def test_server_mode_invalid_grpc_port_raises(self, invalid_grpc_port):
        """Server 모드에서 잘못된 gRPC 포트는 에러."""
        with pytest.raises(ValueError, match="Invalid grpc_port"):
            create_qdrant_client(mode="server", host="localhost", grpc_port=invalid_grpc_port)

    @pytest.mark.parametrize("valid_port", [1, 80, 6333, 8080, 65535])
    def test_server_mode_valid_ports(self, valid_port):
        """Server 모드 유효한 포트 범위."""
        with patch("src.infra.vector.AsyncQdrantClient"):
            # 에러 없이 생성되어야 함
            create_qdrant_client(mode="server", host="localhost", port=valid_port)

    def test_qdrant_mode_enum_values(self):
        """QdrantMode Enum 값 확인."""
        assert QdrantMode.MEMORY.value == "memory"
        assert QdrantMode.EMBEDDED.value == "embedded"
        assert QdrantMode.SERVER.value == "server"

    def test_embedded_mode_with_special_characters_in_path(self, tmp_path):
        """특수 문자가 포함된 경로 처리."""
        special_path = tmp_path / "path with spaces" / "한글경로" / "qdrant"

        with patch("src.infra.vector.AsyncQdrantClient"):
            create_qdrant_client(mode="embedded", storage_path=str(special_path))

            assert special_path.exists()
            assert special_path.is_dir()

    def test_embedded_mode_very_deep_nesting(self, tmp_path):
        """매우 깊은 중첩 경로."""
        deep_path = tmp_path
        for i in range(20):  # 20 levels deep
            deep_path = deep_path / f"level{i}"

        with patch("src.infra.vector.AsyncQdrantClient"):
            create_qdrant_client(mode="embedded", storage_path=str(deep_path))

            assert deep_path.exists()

    def test_embedded_mode_idempotent_directory_creation(self, tmp_path):
        """동일 경로로 여러 번 호출해도 안전."""
        from codegraph_shared.infra.vector import _LockFileManager

        storage_path = tmp_path / "qdrant_data"

        with patch("src.infra.vector.AsyncQdrantClient"):
            # 첫 번째 호출
            create_qdrant_client(mode="embedded", storage_path=str(storage_path))
            assert storage_path.exists()

            # Lock 해제
            _LockFileManager.release_lock(storage_path)

            # 두 번째 호출 (exist_ok=True로 안전)
            create_qdrant_client(mode="embedded", storage_path=str(storage_path))
            assert storage_path.exists()

            _LockFileManager.release_lock(storage_path)


class TestQdrantClientLogging:
    """로깅 동작 테스트 (structlog 사용)."""

    def test_memory_mode_creates_client(self):
        """Memory 모드 클라이언트 생성 확인."""
        with patch("src.infra.vector.AsyncQdrantClient") as mock_client:
            client = create_qdrant_client(mode="memory")
            mock_client.assert_called_once_with(":memory:")
            assert client is not None

    def test_embedded_mode_creates_with_path(self, tmp_path):
        """Embedded 모드 경로와 함께 생성."""
        storage_path = tmp_path / "test_qdrant"

        with patch("src.infra.vector.AsyncQdrantClient") as mock_client:
            create_qdrant_client(mode="embedded", storage_path=str(storage_path))

            # 절대 경로로 호출되었는지 확인
            call_path = mock_client.call_args.kwargs["path"]
            assert Path(call_path).is_absolute()
            assert storage_path.exists()

    def test_server_mode_creates_with_connection_info(self):
        """Server 모드 연결 정보와 함께 생성."""
        with patch("src.infra.vector.AsyncQdrantClient") as mock_client:
            create_qdrant_client(mode="server", host="qdrant.example.com", port=6333)

            call_kwargs = mock_client.call_args.kwargs
            assert call_kwargs["host"] == "qdrant.example.com"
            assert call_kwargs["port"] == 6333
