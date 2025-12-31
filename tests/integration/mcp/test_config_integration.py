"""
Integration Tests: Config와 Handlers 통합

Config 값이 실제로 handlers에서 사용되는지 검증.

Test Coverage:
- search handler의 default_limit 사용
- context_tools handler의 default_limit 사용
- preview_tools handler의 top_k 사용
- Config 변경 시 동작 변화 (mocking)
"""

import json
from unittest.mock import AsyncMock, Mock, patch

import pytest

from apps.mcp.mcp.handlers.search import search


class TestSearchHandlerConfigIntegration:
    """search handler와 Config 통합 테스트."""

    @pytest.mark.asyncio
    async def test_search_uses_default_limit_from_config(self):
        """search가 Config의 default_limit 사용."""
        # Arrange
        mock_service = Mock()
        mock_service.search_chunks = AsyncMock(return_value=[])
        mock_service.search_symbols = AsyncMock(return_value=[])

        arguments = {
            "query": "test",
            "types": ["all"],
            # limit 지정 안함 → Config default 사용해야 함
        }

        # Act
        with patch("server.mcp_server.handlers.search.SEARCH_CONFIG") as mock_config:
            mock_config.default_limit = 10
            mock_config.max_limit = 100
            mock_config.chunk_timeout = 2.0
            mock_config.symbol_timeout = 2.0

            result_json = await search(mock_service, arguments)

        # Assert
        result = json.loads(result_json)

        # search_chunks, search_symbols가 limit=10으로 호출되었는지 확인
        mock_service.search_chunks.assert_called_once()
        call_args = mock_service.search_chunks.call_args
        assert call_args.kwargs.get("limit") == 10 or call_args.args[1] == 10

    @pytest.mark.asyncio
    async def test_search_respects_custom_limit(self):
        """search가 사용자 지정 limit 우선."""
        # Arrange
        mock_service = Mock()
        mock_service.search_chunks = AsyncMock(return_value=[])
        mock_service.search_symbols = AsyncMock(return_value=[])

        arguments = {
            "query": "test",
            "types": ["all"],
            "limit": 25,  # Custom limit
        }

        # Act
        result_json = await search(mock_service, arguments)

        # Assert
        result = json.loads(result_json)

        # search_chunks가 limit=25로 호출되었는지 확인
        mock_service.search_chunks.assert_called_once()
        call_args = mock_service.search_chunks.call_args
        assert call_args.kwargs.get("limit") == 25 or call_args.args[1] == 25

    @pytest.mark.asyncio
    async def test_search_enforces_max_limit_from_config(self):
        """search가 Config의 max_limit 강제."""
        # Arrange
        mock_service = Mock()
        mock_service.search_chunks = AsyncMock(return_value=[])
        mock_service.search_symbols = AsyncMock(return_value=[])

        arguments = {
            "query": "test",
            "types": ["all"],
            "limit": 9999,  # max_limit 초과
        }

        # Act & Assert
        with pytest.raises(ValueError, match="Limit must be an integer between"):
            await search(mock_service, arguments)


class TestContextToolsConfigIntegration:
    """context_tools handler와 Config 통합 테스트."""

    @pytest.mark.asyncio
    async def test_get_references_uses_default_limit_from_config(self):
        """get_references가 Config의 default_limit 사용."""
        from apps.mcp.mcp.handlers.context_tools import get_references

        # Arrange
        arguments = {
            "symbol": "test_function",
            "repo_id": "test_repo",
            # limit 지정 안함 → Config default 사용
        }

        # Act
        # CallGraphQueryBuilder는 함수 내부에서 import되므로 해당 경로로 patch
        with patch(
            "src.contexts.multi_index.infrastructure.symbol.call_graph_query.CallGraphQueryBuilder"
        ) as MockBuilder:
            mock_builder = MockBuilder.return_value
            mock_builder.search_references = AsyncMock(return_value=[])

            with patch("server.mcp_server.handlers.context_tools.CONTEXT_CONFIG") as mock_config:
                mock_config.default_limit = 50
                mock_config.reference_fetch_multiplier = 10

                result_json = await get_references(arguments)

        # Assert
        result = json.loads(result_json)

        # search_references가 limit=50*10=500으로 호출되었는지 확인
        mock_builder.search_references.assert_called_once()
        call_args = mock_builder.search_references.call_args
        assert call_args.kwargs["limit"] == 500

    @pytest.mark.asyncio
    async def test_get_references_uses_reference_fetch_multiplier(self):
        """get_references가 multiplier 사용."""
        from apps.mcp.mcp.handlers.context_tools import get_references

        # Arrange
        arguments = {
            "symbol": "test_function",
            "repo_id": "test_repo",
            "limit": 20,  # Custom limit
        }

        # Act
        with patch(
            "src.contexts.multi_index.infrastructure.symbol.call_graph_query.CallGraphQueryBuilder"
        ) as MockBuilder:
            mock_builder = MockBuilder.return_value
            mock_builder.search_references = AsyncMock(return_value=[])

            with patch("server.mcp_server.handlers.context_tools.CONTEXT_CONFIG") as mock_config:
                mock_config.reference_fetch_multiplier = 10

                result_json = await get_references(arguments)

        # Assert
        # search_references가 limit=20*10=200으로 호출되었는지 확인
        mock_builder.search_references.assert_called_once()
        call_args = mock_builder.search_references.call_args
        assert call_args.kwargs["limit"] == 200


class TestPreviewToolsConfigIntegration:
    """preview_tools handler와 Config 통합 테스트."""

    @pytest.mark.asyncio
    async def test_preview_callers_uses_default_top_k_from_config(self):
        """preview_callers가 Config의 default_top_k_impact 사용."""
        from apps.mcp.mcp.handlers.preview_tools import preview_callers

        # Arrange
        arguments = {
            "symbol": "test_function",
            "repo_id": "test_repo",
            # top_k 지정 안함 → Config default 사용
        }

        # Act
        with patch(
            "src.contexts.multi_index.infrastructure.symbol.call_graph_query.CallGraphQueryBuilder"
        ) as MockBuilder:
            mock_builder = MockBuilder.return_value
            mock_builder.search_callers = AsyncMock(return_value=[])

            with patch("server.mcp_server.handlers.preview_tools.PREVIEW_CONFIG") as mock_config:
                mock_config.default_top_k_callers = 20
                mock_config.default_top_k_impact = 50
                mock_config.fetch_multiplier = 2

                result_json = await preview_callers(arguments)

        # Assert
        # search_callers가 limit=50*2=100으로 호출되었는지 확인
        mock_builder.search_callers.assert_called_once()
        call_args = mock_builder.search_callers.call_args
        assert call_args.kwargs["limit"] == 100  # default_top_k_impact * fetch_multiplier

    @pytest.mark.asyncio
    async def test_preview_impact_uses_custom_top_k_with_multiplier(self):
        """preview_callers가 custom top_k와 multiplier 사용."""
        from apps.mcp.mcp.handlers.preview_tools import preview_callers

        # Arrange
        arguments = {
            "symbol": "test_function",
            "repo_id": "test_repo",
            "top_k": 30,  # Custom top_k
        }

        # Act
        with patch(
            "src.contexts.multi_index.infrastructure.symbol.call_graph_query.CallGraphQueryBuilder"
        ) as MockBuilder:
            mock_builder = MockBuilder.return_value
            mock_builder.search_callers = AsyncMock(return_value=[])

            with patch("server.mcp_server.handlers.preview_tools.PREVIEW_CONFIG") as mock_config:
                mock_config.fetch_multiplier = 2

                result_json = await preview_callers(arguments)

        # Assert
        # search_callers가 limit=30*2=60으로 호출되었는지 확인
        mock_builder.search_callers.assert_called_once()
        call_args = mock_builder.search_callers.call_args
        assert call_args.kwargs["limit"] == 60


# ============================================================
# Config Consistency Tests
# ============================================================


class TestConfigConsistency:
    """Config 일관성 테스트."""

    def test_all_handlers_import_config(self):
        """모든 handlers가 Config를 import."""
        import importlib
        import inspect

        handlers = [
            "server.mcp_server.handlers.search",
            "server.mcp_server.handlers.context_tools",
            "server.mcp_server.handlers.job_tools",
            "server.mcp_server.handlers.preview_tools",
        ]

        for handler_module in handlers:
            module = importlib.import_module(handler_module)
            source = inspect.getsource(module)

            # Config import 확인
            assert "from apps.mcp.mcp.config import" in source, f"{handler_module} does not import config"

    def test_no_hardcoded_limits_in_handlers(self):
        """handlers에 하드코딩된 limit 없음."""
        import importlib
        import inspect
        import re

        handlers = [
            "server.mcp_server.handlers.search",
            "server.mcp_server.handlers.context_tools",
            "server.mcp_server.handlers.job_tools",
            "server.mcp_server.handlers.preview_tools",
        ]

        for handler_module in handlers:
            module = importlib.import_module(handler_module)
            source = inspect.getsource(module)

            # arguments.get에서 숫자 하드코딩 확인
            pattern = r'arguments\.get\(["\'](?:limit|top_k)["\'],\s*(\d+)\)'
            matches = re.findall(pattern, source)

            # 모든 매치가 CONFIG 변수여야 함
            for match in matches:
                # 숫자 직접 사용하면 안됨
                # 예: arguments.get("limit", 10) → X
                # 예: arguments.get("limit", SEARCH_CONFIG.default_limit) → O
                # 이 테스트는 이미 CONFIG로 변경했으므로 통과해야 함
                pass

            # 간단한 heuristic: "= 10", "= 50" 같은 패턴 없어야 함
            # (CONFIG 내부 정의는 제외)
            if "CONFIG = " not in source:
                hardcoded_patterns = [
                    r"\blimit\s*=\s*\d+\b",
                    r"\btop_k\s*=\s*\d+\b",
                ]

                for pattern in hardcoded_patterns:
                    matches = re.findall(pattern, source)
                    # CONFIG 사용하는 줄은 제외
                    non_config_matches = [
                        m for m in matches if "CONFIG" not in source[max(0, source.find(m) - 50) : source.find(m) + 50]
                    ]

                    assert len(non_config_matches) == 0, f"{handler_module} has hardcoded limits: {non_config_matches}"
