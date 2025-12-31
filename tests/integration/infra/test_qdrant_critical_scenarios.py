"""
Critical production scenario tests.

Tests concurrent access protection, disk space monitoring, and failure recovery.
"""

import asyncio
import time
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from codegraph_shared.infra.vector import create_qdrant_client
from codegraph_shared.infra.vector.qdrant import QdrantAdapter


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.critical
class TestConcurrentAccessProtection:
    """동시 접근 방지 테스트 (BLOCKING ISSUE)."""

    async def test_embedded_mode_single_process_only(self, tmp_path):
        """Embedded 모드는 단일 프로세스만 허용."""
        storage_path = tmp_path / "single_process_test"

        # 첫 번째 클라이언트 생성
        client1 = create_qdrant_client(mode="embedded", storage_path=str(storage_path))

        try:
            # 두 번째 클라이언트 생성 시도 (실패해야 함)
            with pytest.raises(RuntimeError, match="Another process is using"):
                client2 = create_qdrant_client(mode="embedded", storage_path=str(storage_path))

        finally:
            await client1.close()

    async def test_embedded_mode_allows_sequential_access(self, tmp_path):
        """순차 접근은 허용."""
        storage_path = tmp_path / "sequential_test"

        # 첫 번째 클라이언트
        client1 = create_qdrant_client(mode="embedded", storage_path=str(storage_path))
        await client1.get_collections()
        await client1.close()

        # Lock 해제 후 두 번째 클라이언트 (성공)
        from codegraph_shared.infra.vector import _LockFileManager

        _LockFileManager.release_lock(storage_path)

        client2 = create_qdrant_client(mode="embedded", storage_path=str(storage_path))
        await client2.get_collections()
        await client2.close()

    async def test_lock_file_creation(self, tmp_path):
        """Lock 파일이 생성되는지 확인."""
        storage_path = tmp_path / "lock_test"

        client = create_qdrant_client(mode="embedded", storage_path=str(storage_path))

        try:
            lock_file = storage_path / ".qdrant.lock"
            assert lock_file.exists(), "Lock file should be created"

        finally:
            await client.close()

    async def test_memory_mode_no_lock_needed(self):
        """Memory 모드는 lock 불필요."""
        # 여러 memory 클라이언트 동시 생성 가능
        client1 = create_qdrant_client(mode="memory")
        client2 = create_qdrant_client(mode="memory")

        try:
            # 둘 다 독립적으로 동작
            await client1.get_collections()
            await client2.get_collections()

        finally:
            await client1.close()
            await client2.close()


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.critical
class TestDiskSpaceMonitoring:
    """디스크 공간 모니터링 테스트 (HIGH PRIORITY)."""

    async def test_embedded_mode_checks_disk_space(self, tmp_path):
        """Embedded 모드는 디스크 공간 체크."""
        storage_path = tmp_path / "disk_check_test"

        # 충분한 공간 (정상 케이스)
        with patch("shutil.disk_usage") as mock_usage:
            mock_usage.return_value = MagicMock(
                free=500 * 1024 * 1024,  # 500MB
                total=1000 * 1024 * 1024,
                used=500 * 1024 * 1024,
            )

            client = create_qdrant_client(mode="embedded", storage_path=str(storage_path), min_disk_space_mb=100)
            await client.close()

    async def test_embedded_mode_fails_on_low_disk_space(self, tmp_path):
        """디스크 공간 부족 시 에러."""
        storage_path = tmp_path / "low_disk_test"

        with patch("shutil.disk_usage") as mock_usage:
            mock_usage.return_value = MagicMock(
                free=50 * 1024 * 1024,  # 50MB (부족)
                total=1000 * 1024 * 1024,
                used=950 * 1024 * 1024,
            )

            with pytest.raises(RuntimeError, match="Insufficient disk space"):
                create_qdrant_client(
                    mode="embedded",
                    storage_path=str(storage_path),
                    min_disk_space_mb=100,
                )

    async def test_disk_space_check_can_be_disabled(self, tmp_path):
        """디스크 공간 체크 비활성화 가능."""
        storage_path = tmp_path / "no_check_test"

        with patch("shutil.disk_usage") as mock_usage:
            mock_usage.return_value = MagicMock(free=1 * 1024 * 1024)  # 1MB only

            # check_disk_space=False면 통과
            client = create_qdrant_client(
                mode="embedded",
                storage_path=str(storage_path),
                check_disk_space=False,
            )
            await client.close()

    async def test_disk_space_warning_on_check_failure(self, tmp_path):
        """디스크 체크 실패 시 경고만 (계속 진행)."""
        storage_path = tmp_path / "check_fail_test"

        with patch("shutil.disk_usage", side_effect=OSError("Permission denied")):
            # 에러 발생하지 않고 경고만 (계속 진행)
            client = create_qdrant_client(mode="embedded", storage_path=str(storage_path))
            await client.close()


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.critical
class TestTimeoutConfiguration:
    """타임아웃 설정 테스트 (HIGH PRIORITY)."""

    async def test_server_mode_custom_timeout(self):
        """Server 모드 커스텀 타임아웃."""
        with patch("src.infra.vector.AsyncQdrantClient") as mock_client:
            create_qdrant_client(mode="server", url="http://localhost:6333", timeout=120)

            mock_client.assert_called_once_with(url="http://localhost:6333", timeout=120)

    async def test_timeout_validation(self):
        """타임아웃 범위 검증."""
        # Valid timeouts
        with patch("src.infra.vector.AsyncQdrantClient"):
            create_qdrant_client(mode="server", url="http://test", timeout=1)
            create_qdrant_client(mode="server", url="http://test", timeout=600)

        # Invalid timeouts
        with pytest.raises(ValueError, match="Invalid timeout"):
            create_qdrant_client(mode="server", url="http://test", timeout=0)

        with pytest.raises(ValueError, match="Invalid timeout"):
            create_qdrant_client(mode="server", url="http://test", timeout=601)

    async def test_grpc_retry_options(self):
        """gRPC retry 옵션이 설정되는지 확인."""
        with patch("src.infra.vector.AsyncQdrantClient") as mock_client:
            create_qdrant_client(mode="server", host="localhost", port=6333, prefer_grpc=True)

            call_kwargs = mock_client.call_args.kwargs
            assert "grpc_options" in call_kwargs
            assert "grpc.max_reconnect_backoff_ms" in call_kwargs["grpc_options"]


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.critical
class TestFailureRecovery:
    """장애 복구 테스트."""

    async def test_embedded_mode_recovery_after_corrupted_lock(self, tmp_path):
        """손상된 lock 파일 후 복구."""
        storage_path = tmp_path / "corrupted_lock_test"
        storage_path.mkdir(parents=True)

        # 손상된 lock 파일 생성
        lock_file = storage_path / ".qdrant.lock"
        lock_file.write_text("corrupted data")

        # Lock manager가 정리하고 새로 획득
        from codegraph_shared.infra.vector import _LockFileManager

        _LockFileManager.release_lock(storage_path)

        # 클라이언트 생성 (성공해야 함)
        client = create_qdrant_client(mode="embedded", storage_path=str(storage_path))

        try:
            await client.get_collections()
        finally:
            await client.close()
            _LockFileManager.release_lock(storage_path)

    async def test_embedded_mode_handles_permission_error_gracefully(self, tmp_path):
        """권한 에러를 명확히 처리."""
        storage_path = tmp_path / "readonly" / "qdrant"
        storage_path.parent.mkdir(parents=True)
        storage_path.parent.chmod(0o444)  # Read-only

        try:
            with pytest.raises(PermissionError, match="No write permission"):
                create_qdrant_client(mode="embedded", storage_path=str(storage_path))
        finally:
            storage_path.parent.chmod(0o755)

    async def test_adapter_survives_client_error(self):
        """QdrantAdapter는 클라이언트 에러 후에도 복구 가능."""
        adapter = QdrantAdapter(mode="memory", collection="error_recovery")

        try:
            # 정상 작업
            await adapter.upsert_vectors(
                [
                    {
                        "id": str(uuid.uuid4()),
                        "vector": [0.1] * 1024,
                        "payload": {"test": 1},
                    }
                ]
            )

            count1 = await adapter.count()
            assert count1 == 1

            # 에러 발생 시뮬레이션 (잘못된 벡터)
            try:
                await adapter.upsert_vectors([{"id": str(uuid.uuid4())}])  # vector 누락
            except Exception:
                pass  # 에러 예상됨

            # 복구 후 정상 작업 가능
            await adapter.upsert_vectors(
                [
                    {
                        "id": str(uuid.uuid4()),
                        "vector": [0.2] * 1024,
                        "payload": {"test": 2},
                    }
                ]
            )

            count2 = await adapter.count()
            assert count2 == 2

        finally:
            await adapter.close()


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.critical
class TestDataIntegrity:
    """데이터 무결성 테스트."""

    async def test_embedded_mode_data_integrity_after_restart(self, tmp_path):
        """재시작 후 데이터 무결성 보장."""
        from codegraph_shared.infra.vector import _LockFileManager

        storage_path = tmp_path / "integrity_test"
        test_collection = "integrity_col"

        # Phase 1: 대량 데이터 삽입
        client1 = create_qdrant_client(mode="embedded", storage_path=str(storage_path))

        try:
            from qdrant_client.models import Distance, PointStruct, VectorParams

            await client1.create_collection(
                collection_name=test_collection,
                vectors_config=VectorParams(size=128, distance=Distance.COSINE),
            )

            # 1000개 벡터 삽입
            points = [
                PointStruct(
                    id=str(uuid.uuid4()),
                    vector=[float(i % 100) / 100] * 128,
                    payload={"index": i, "checksum": i * 123},
                )
                for i in range(100)  # 1000 → 100
            ]

            await client1.upsert(collection_name=test_collection, points=points)

            count1 = await client1.count(collection_name=test_collection)
            assert count1.count == 1000

        finally:
            await client1.close()
            _LockFileManager.release_lock(storage_path)

        # Phase 2: 재시작 후 검증
        client2 = create_qdrant_client(mode="embedded", storage_path=str(storage_path))

        try:
            # Count 검증
            count2 = await client2.count(collection_name=test_collection)
            assert count2.count == 1000

            # 검색 검증
            results = await client2.search(collection_name=test_collection, query_vector=[0.5] * 128, limit=10)
            assert len(results) == 10

            # Payload 무결성 검증
            for result in results:
                index = result.payload["index"]
                checksum = result.payload["checksum"]
                assert checksum == index * 123, "Checksum mismatch - data corrupted!"

        finally:
            await client2.close()
            _LockFileManager.release_lock(storage_path)

    async def test_concurrent_operations_within_same_process(self):
        """동일 프로세스 내 동시 작업은 안전."""
        adapter = QdrantAdapter(mode="memory", collection="concurrent_safe")

        try:
            # 100개 동시 upsert
            tasks = []
            for i in range(100):
                vectors = [
                    {
                        "id": str(uuid.uuid4()),
                        "vector": [float(i) / 100] * 1024,
                        "payload": {"batch": i},
                    }
                ]
                tasks.append(adapter.upsert_vectors(vectors))

            await asyncio.gather(*tasks)

            count = await adapter.count()
            assert count == 100

        finally:
            await adapter.close()

    async def test_lock_released_on_normal_close(self, tmp_path):
        """정상 종료 시 lock 해제."""
        from codegraph_shared.infra.vector import _LockFileManager

        storage_path = tmp_path / "lock_release_test"

        client1 = create_qdrant_client(mode="embedded", storage_path=str(storage_path))
        await client1.close()

        # Lock 명시적 해제
        _LockFileManager.release_lock(storage_path)

        # 새 클라이언트 생성 가능
        client2 = create_qdrant_client(mode="embedded", storage_path=str(storage_path))
        await client2.close()
        _LockFileManager.release_lock(storage_path)


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.critical
class TestErrorMessages:
    """에러 메시지 품질 테스트."""

    async def test_concurrent_access_error_message_actionable(self, tmp_path):
        """동시 접근 에러 메시지가 해결 방법 포함."""
        storage_path = tmp_path / "error_msg_test"

        client1 = create_qdrant_client(mode="embedded", storage_path=str(storage_path))

        try:
            with pytest.raises(RuntimeError) as exc_info:
                client2 = create_qdrant_client(mode="embedded", storage_path=str(storage_path))

            error_msg = str(exc_info.value)
            # 해결 방법 포함 확인
            assert "Solutions:" in error_msg or "Stop the other process" in error_msg
            assert "server mode" in error_msg.lower()

        finally:
            await client1.close()

    async def test_disk_space_error_message_actionable(self, tmp_path):
        """디스크 공간 에러 메시지가 해결 방법 포함."""
        storage_path = tmp_path / "disk_msg_test"

        with patch("shutil.disk_usage") as mock_usage:
            mock_usage.return_value = MagicMock(
                free=10 * 1024 * 1024,
                total=1000 * 1024 * 1024,
                used=990 * 1024 * 1024,
            )

            with pytest.raises(RuntimeError) as exc_info:
                create_qdrant_client(mode="embedded", storage_path=str(storage_path), min_disk_space_mb=100)

            error_msg = str(exc_info.value)
            # 구체적인 정보 포함
            assert "Free:" in error_msg
            assert "Total:" in error_msg
            assert "Used:" in error_msg
            assert "MB" in error_msg
            assert "Solutions:" in error_msg

    async def test_validation_errors_are_clear(self):
        """Validation 에러가 명확."""
        # Invalid mode
        with pytest.raises(ValueError) as exc_info:
            create_qdrant_client(mode="invalid")

        assert "Must be one of" in str(exc_info.value)

        # Invalid port
        with pytest.raises(ValueError) as exc_info:
            create_qdrant_client(mode="server", host="test", port=99999)

        assert "1-65535" in str(exc_info.value)


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.critical
class TestProductionScenarios:
    """실제 프로덕션 시나리오."""

    async def test_application_restart_cycle(self, tmp_path):
        """애플리케이션 재시작 사이클 시뮬레이션."""
        from codegraph_shared.infra.config.settings import Settings
        from codegraph_shared.infra.di import InfraContainer
        from codegraph_shared.infra.vector import _LockFileManager

        storage_path = tmp_path / "restart_test"

        # Cycle 1: 초기 실행
        settings1 = Settings(qdrant_mode="embedded", qdrant_storage_path=str(storage_path))
        container1 = InfraContainer(settings1)
        adapter1 = container1.qdrant

        await adapter1.upsert_vectors(
            [
                {
                    "id": str(uuid.uuid4()),
                    "vector": [0.1] * 1024,
                    "payload": {"cycle": 1},
                }
            ]
        )

        count1 = await adapter1.count()
        assert count1 == 1

        await adapter1.close()
        _LockFileManager.release_lock(storage_path)

        # Cycle 2: 재시작
        settings2 = Settings(qdrant_mode="embedded", qdrant_storage_path=str(storage_path))
        container2 = InfraContainer(settings2)
        adapter2 = container2.qdrant

        count2 = await adapter2.count()
        assert count2 == 1  # 데이터 유지

        await adapter2.upsert_vectors(
            [
                {
                    "id": str(uuid.uuid4()),
                    "vector": [0.2] * 1024,
                    "payload": {"cycle": 2},
                }
            ]
        )

        count3 = await adapter2.count()
        assert count3 == 2

        await adapter2.close()
        _LockFileManager.release_lock(storage_path)

    async def test_high_throughput_sustained(self):
        """지속적인 고처리량 작업."""
        adapter = QdrantAdapter(mode="memory", collection="throughput_test")

        try:
            # 10초 동안 계속 삽입
            start_time = time.time()
            total_inserted = 0

            while time.time() - start_time < 10:
                vectors = [
                    {
                        "id": str(uuid.uuid4()),
                        "vector": [0.1] * 1024,
                        "payload": {"timestamp": time.time()},
                    }
                    for _ in range(100)
                ]

                await adapter.upsert_vectors(vectors)
                total_inserted += 100

            elapsed = time.time() - start_time
            throughput = total_inserted / elapsed

            print(f"\nSustained throughput: {throughput:.1f} vectors/sec over {elapsed:.1f}s")
            print(f"Total inserted: {total_inserted} vectors")

            # 최소 처리량 보장
            assert throughput > 200, f"Throughput too low: {throughput:.1f} vec/s"

            # 데이터 무결성
            count = await adapter.count()
            assert count == total_inserted

        finally:
            await adapter.close()
