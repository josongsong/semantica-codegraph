"""
Unit Tests: 인덱싱 자동화

Big Tech L11급 인덱싱 상태 체크 및 캐시 활용.

Test Coverage:
- check_index_status() 각 상태별 동작
- ensure_indexed() 중복 호출 방지
- IndexCheckResult ENUM 사용
- 캐시 히트 확인
- 진행 중 스킵 확인
- Edge cases (DB 없음, 에러 등)
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch

from apps.mcp.mcp.main import IndexCheckResult, check_index_status, ensure_indexed


class TestIndexCheckResult:
    """IndexCheckResult ENUM 테스트."""

    def test_enum_values(self):
        """ENUM 값 확인 (내부 로직용)."""
        assert IndexCheckResult.COMPLETED.value == "completed"
        assert IndexCheckResult.IN_PROGRESS.value == "in_progress"
        assert IndexCheckResult.NOT_FOUND.value == "not_found"
        assert IndexCheckResult.ERROR.value == "error"

    def test_enum_comparison(self):
        """ENUM 비교."""
        assert IndexCheckResult.COMPLETED != IndexCheckResult.IN_PROGRESS
        assert IndexCheckResult.NOT_FOUND != IndexCheckResult.ERROR


class TestCheckIndexStatus:
    """check_index_status() 테스트."""

    @pytest.mark.asyncio
    async def test_check_index_status_completed(self):
        """COMPLETED 상태 반환."""
        with patch("src.config.settings") as mock_settings:
            mock_settings.postgres_enabled = True

            with patch("src.infra.storage.postgres.PostgresStore"):
                with patch("src.contexts.multi_index.infrastructure.version.store.IndexVersionStore") as MockStore:
                    mock_store = MockStore.return_value

                    # Mock latest version
                    mock_version = Mock()
                    mock_version.status = Mock()
                    mock_version.status.value = "completed"
                    mock_version.version_id = 1
                    mock_version.file_count = 100
                    mock_version.git_commit = "abc123def"

                    from codegraph_engine.multi_index.infrastructure.version.models import IndexVersionStatus

                    mock_version.status = IndexVersionStatus.COMPLETED

                    mock_store.get_latest_version = AsyncMock(return_value=mock_version)

                    result = await check_index_status("/test/repo")

                    assert result == IndexCheckResult.COMPLETED

    @pytest.mark.asyncio
    async def test_check_index_status_in_progress(self):
        """IN_PROGRESS 상태 반환."""
        with patch("src.config.settings") as mock_settings:
            mock_settings.postgres_enabled = True

            with patch("src.infra.storage.postgres.PostgresStore"):
                with patch("src.contexts.multi_index.infrastructure.version.store.IndexVersionStore") as MockStore:
                    mock_store = MockStore.return_value

                    # Mock indexing version
                    mock_version = Mock()
                    from codegraph_engine.multi_index.infrastructure.version.models import IndexVersionStatus

                    mock_version.status = IndexVersionStatus.INDEXING

                    mock_store.get_latest_version = AsyncMock(return_value=mock_version)

                    result = await check_index_status("/test/repo")

                    assert result == IndexCheckResult.IN_PROGRESS

    @pytest.mark.asyncio
    async def test_check_index_status_not_found(self):
        """NOT_FOUND 상태 반환 (인덱스 없음)."""
        with patch("src.config.settings") as mock_settings:
            mock_settings.postgres_enabled = True

            with patch("src.infra.storage.postgres.PostgresStore"):
                with patch("src.contexts.multi_index.infrastructure.version.store.IndexVersionStore") as MockStore:
                    mock_store = MockStore.return_value
                    mock_store.get_latest_version = AsyncMock(return_value=None)

                    result = await check_index_status("/test/repo")

                    assert result == IndexCheckResult.NOT_FOUND

    @pytest.mark.asyncio
    async def test_check_index_status_postgres_disabled(self):
        """PostgreSQL 비활성화 시 NOT_FOUND."""
        with patch("src.config.settings") as mock_settings:
            mock_settings.postgres_enabled = False

            result = await check_index_status("/test/repo")

            assert result == IndexCheckResult.NOT_FOUND

    @pytest.mark.asyncio
    async def test_check_index_status_error_handling(self):
        """예외 발생 시 ERROR 반환."""
        with patch("src.config.settings") as mock_settings:
            mock_settings.side_effect = Exception("DB connection failed")

            result = await check_index_status("/test/repo")

            assert result == IndexCheckResult.ERROR


class TestEnsureIndexed:
    """ensure_indexed() 테스트."""

    @pytest.mark.asyncio
    async def test_ensure_indexed_with_completed_cache(self):
        """COMPLETED 상태면 캐시 사용."""
        with patch("server.mcp_server.main.check_index_status") as mock_check:
            mock_check.return_value = IndexCheckResult.COMPLETED

            # Reset global flag
            import apps.mcp.mcp.main as main_module

            main_module._indexing_done = False

            await ensure_indexed()

            # Should set flag
            assert main_module._indexing_done is True

    @pytest.mark.asyncio
    async def test_ensure_indexed_with_in_progress(self):
        """IN_PROGRESS 상태면 스킵."""
        with patch("server.mcp_server.main.check_index_status") as mock_check:
            mock_check.return_value = IndexCheckResult.IN_PROGRESS

            import apps.mcp.mcp.main as main_module

            main_module._indexing_done = False

            await ensure_indexed()

            assert main_module._indexing_done is True

    @pytest.mark.asyncio
    async def test_ensure_indexed_prevents_duplicate_checks(self):
        """중복 호출 방지."""
        with patch("server.mcp_server.main.check_index_status") as mock_check:
            mock_check.return_value = IndexCheckResult.COMPLETED

            import apps.mcp.mcp.main as main_module

            main_module._indexing_done = False

            # 첫 호출
            await ensure_indexed()
            assert mock_check.call_count == 1

            # 두 번째 호출 (skip)
            await ensure_indexed()
            assert mock_check.call_count == 1  # 여전히 1

    @pytest.mark.asyncio
    async def test_ensure_indexed_with_error(self):
        """ERROR 상태도 graceful degradation."""
        with patch("server.mcp_server.main.check_index_status") as mock_check:
            mock_check.return_value = IndexCheckResult.ERROR

            import apps.mcp.mcp.main as main_module

            main_module._indexing_done = False

            # Should not raise
            await ensure_indexed()

            assert main_module._indexing_done is True


class TestIndexingIntegration:
    """call_tool과 ensure_indexed 통합 테스트."""

    @pytest.mark.asyncio
    async def test_call_tool_triggers_ensure_indexed(self):
        """call_tool이 ensure_indexed 호출."""
        from apps.mcp.mcp.main import call_tool

        with patch("server.mcp_server.main.ensure_indexed") as mock_ensure:
            mock_ensure.return_value = None

            with patch("server.mcp_server.main.search") as mock_search:
                mock_search.return_value = '{"status": "ok"}'

                # Reset flag
                import apps.mcp.mcp.main as main_module

                main_module._indexing_done = False

                await call_tool("search", {"query": "test"})

                # ensure_indexed가 호출되었는지
                mock_ensure.assert_called_once()
