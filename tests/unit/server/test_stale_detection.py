"""
Unit Tests: STALE Detection

Big Tech L11: IN_PROGRESS가 오래되면 STALE 처리.

Test Coverage:
- STALE 감지 (30분 초과)
- 정상 IN_PROGRESS (30분 이내)
- created_at 없는 경우
- Timestamp vs datetime 처리
- Edge cases
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch

import pytest

from apps.mcp.mcp.main import IndexCheckResult, IndexStatusLoader


class TestStaleDetection:
    """STALE 감지 테스트."""

    @pytest.mark.asyncio
    async def test_in_progress_stale_returns_none(self):
        """IN_PROGRESS가 30분 초과면 None (STALE)."""
        loader = IndexStatusLoader(indexing_timeout=1800)  # 30분

        with patch("src.infra.storage.postgres.PostgresStore"):
            with patch("src.contexts.multi_index.infrastructure.version.store.IndexVersionStore") as MockStore:
                mock_store = MockStore.return_value

                # Mock old IN_PROGRESS (31분 전 생성)
                mock_version = Mock()
                from codegraph_engine.multi_index.infrastructure.version.models import IndexVersionStatus

                mock_version.status = IndexVersionStatus.INDEXING
                mock_version.created_at = datetime.now() - timedelta(minutes=31)

                mock_store.get_latest_version = AsyncMock(return_value=mock_version)

                result = await loader.load("default")

                # STALE → None
                assert result is None

    @pytest.mark.asyncio
    async def test_in_progress_fresh_returns_in_progress(self):
        """IN_PROGRESS가 30분 이내면 IN_PROGRESS."""
        loader = IndexStatusLoader(indexing_timeout=1800)

        with patch("src.infra.storage.postgres.PostgresStore"):
            with patch("src.contexts.multi_index.infrastructure.version.store.IndexVersionStore") as MockStore:
                mock_store = MockStore.return_value

                # Mock fresh IN_PROGRESS (5분 전 생성)
                mock_version = Mock()
                from codegraph_engine.multi_index.infrastructure.version.models import IndexVersionStatus

                mock_version.status = IndexVersionStatus.INDEXING
                mock_version.created_at = datetime.now() - timedelta(minutes=5)

                mock_store.get_latest_version = AsyncMock(return_value=mock_version)

                result = await loader.load("default")

                assert result == IndexCheckResult.IN_PROGRESS

    @pytest.mark.asyncio
    async def test_in_progress_boundary_29min(self):
        """IN_PROGRESS 경계값 테스트 (29분)."""
        loader = IndexStatusLoader(indexing_timeout=1800)

        with patch("src.infra.storage.postgres.PostgresStore"):
            with patch("src.contexts.multi_index.infrastructure.version.store.IndexVersionStore") as MockStore:
                mock_store = MockStore.return_value

                # 29분 전 (아직 유효)
                mock_version = Mock()
                from codegraph_engine.multi_index.infrastructure.version.models import IndexVersionStatus

                mock_version.status = IndexVersionStatus.INDEXING
                mock_version.created_at = datetime.now() - timedelta(minutes=29)

                mock_store.get_latest_version = AsyncMock(return_value=mock_version)

                result = await loader.load("default")

                assert result == IndexCheckResult.IN_PROGRESS

    @pytest.mark.asyncio
    async def test_in_progress_boundary_31min(self):
        """IN_PROGRESS 경계값 테스트 (31분)."""
        loader = IndexStatusLoader(indexing_timeout=1800)

        with patch("src.infra.storage.postgres.PostgresStore"):
            with patch("src.contexts.multi_index.infrastructure.version.store.IndexVersionStore") as MockStore:
                mock_store = MockStore.return_value

                # 31분 전 (STALE)
                mock_version = Mock()
                from codegraph_engine.multi_index.infrastructure.version.models import IndexVersionStatus

                mock_version.status = IndexVersionStatus.INDEXING
                mock_version.created_at = datetime.now() - timedelta(minutes=31)

                mock_store.get_latest_version = AsyncMock(return_value=mock_version)

                result = await loader.load("default")

                assert result is None  # STALE

    @pytest.mark.asyncio
    async def test_in_progress_no_created_at_returns_in_progress(self):
        """created_at 없으면 IN_PROGRESS (안전)."""
        loader = IndexStatusLoader(indexing_timeout=1800)

        with patch("src.infra.storage.postgres.PostgresStore"):
            with patch("src.contexts.multi_index.infrastructure.version.store.IndexVersionStore") as MockStore:
                mock_store = MockStore.return_value

                # created_at 없음
                mock_version = Mock()
                from codegraph_engine.multi_index.infrastructure.version.models import IndexVersionStatus

                mock_version.status = IndexVersionStatus.INDEXING
                mock_version.created_at = None

                mock_store.get_latest_version = AsyncMock(return_value=mock_version)

                result = await loader.load("default")

                # 안전: IN_PROGRESS 반환 (False positive보다 낫다)
                assert result == IndexCheckResult.IN_PROGRESS

    @pytest.mark.asyncio
    async def test_completed_always_returns_completed(self):
        """COMPLETED는 항상 COMPLETED (timestamp 무관)."""
        loader = IndexStatusLoader(indexing_timeout=1800)

        with patch("src.infra.storage.postgres.PostgresStore"):
            with patch("src.contexts.multi_index.infrastructure.version.store.IndexVersionStore") as MockStore:
                mock_store = MockStore.return_value

                # Old COMPLETED (1년 전)
                mock_version = Mock()
                from codegraph_engine.multi_index.infrastructure.version.models import IndexVersionStatus

                mock_version.status = IndexVersionStatus.COMPLETED
                mock_version.created_at = datetime.now() - timedelta(days=365)
                mock_version.version_id = 1
                mock_version.file_count = 100

                mock_store.get_latest_version = AsyncMock(return_value=mock_version)

                result = await loader.load("default")

                assert result == IndexCheckResult.COMPLETED


class TestIndexStatusCacheConfig:
    """IndexStatusCacheConfig 테스트."""

    def test_config_defaults(self):
        """Default 값 확인."""
        from apps.mcp.mcp.config import get_index_status_cache_config

        config = get_index_status_cache_config()

        assert config.ttl_completed == 1800  # 30분
        assert config.ttl_in_progress == 60  # 1분
        assert config.ttl_not_found == 300  # 5분
        assert config.indexing_timeout == 1800  # 30분
        assert config.l1_maxsize == 100

    def test_config_ttl_ordering(self):
        """TTL 순서 확인 (IN_PROGRESS가 가장 짧음)."""
        from apps.mcp.mcp.config import get_index_status_cache_config

        config = get_index_status_cache_config()

        # IN_PROGRESS는 빠른 재체크 위해 짧게
        assert config.ttl_in_progress < config.ttl_not_found
        assert config.ttl_in_progress < config.ttl_completed

    def test_config_frozen(self):
        """Config는 불변."""
        from apps.mcp.mcp.config import get_index_status_cache_config

        config = get_index_status_cache_config()

        with pytest.raises(Exception):  # FrozenInstanceError
            config.ttl_completed = 999  # type: ignore

    def test_indexing_timeout_positive(self):
        """indexing_timeout은 양수."""
        from apps.mcp.mcp.config import get_index_status_cache_config

        config = get_index_status_cache_config()

        assert config.indexing_timeout > 0
