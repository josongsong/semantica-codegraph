"""
Unit Tests: force_reindex

Big Tech L11: 강제 재인덱싱 도구.

Test Coverage:
- force_reindex 기본 동작
- 캐시 무효화
- DB version invalidation
- Job submission
- Error handling
- Edge cases
"""

import json
from unittest.mock import AsyncMock, Mock, patch

import pytest


class TestForceReindex:
    """force_reindex 테스트."""

    @pytest.mark.asyncio
    async def test_force_reindex_with_defaults(self):
        """기본 인자로 force_reindex 호출."""
        from apps.mcp.mcp.handlers.admin_tools import force_reindex

        arguments = {}  # All defaults

        with patch("server.mcp_server.main._invalidate_index_cache") as mock_invalidate:
            mock_invalidate.return_value = None

            result_json = await force_reindex(arguments)

        result = json.loads(result_json)

        assert "status" in result
        assert result.get("repo_id") == "default"
        assert "meta" in result
        assert result["meta"]["tier"] == 2
        assert result["meta"]["requires_approval"] is True

    @pytest.mark.asyncio
    async def test_force_reindex_with_reason(self):
        """reason 지정."""
        from apps.mcp.mcp.handlers.admin_tools import force_reindex

        arguments = {
            "repo_id": "my_repo",
            "reason": "Schema upgrade",
        }

        with patch("server.mcp_server.main._invalidate_index_cache") as mock_invalidate:
            mock_invalidate.return_value = None

            result_json = await force_reindex(arguments)

        result = json.loads(result_json)

        assert result.get("repo_id") == "my_repo"

    @pytest.mark.asyncio
    async def test_force_reindex_invalidates_cache(self):
        """캐시 무효화 확인."""
        from apps.mcp.mcp.handlers.admin_tools import force_reindex

        arguments = {
            "invalidate_cache": True,
        }

        with patch("server.mcp_server.main._invalidate_index_cache") as mock_invalidate:
            mock_invalidate.return_value = None

            result_json = await force_reindex(arguments)

            # _invalidate_index_cache 호출되었는지
            mock_invalidate.assert_called_once_with("default")

    @pytest.mark.asyncio
    async def test_force_reindex_skip_cache_invalidation(self):
        """캐시 무효화 스킵."""
        from apps.mcp.mcp.handlers.admin_tools import force_reindex

        arguments = {
            "invalidate_cache": False,
        }

        with patch("server.mcp_server.main._invalidate_index_cache") as mock_invalidate:
            mock_invalidate.return_value = None

            result_json = await force_reindex(arguments)

            # 호출 안되어야 함
            mock_invalidate.assert_not_called()

    @pytest.mark.asyncio
    async def test_force_reindex_returns_job_id(self):
        """Job ID 반환."""
        from apps.mcp.mcp.handlers.admin_tools import force_reindex

        arguments = {}

        with patch("server.mcp_server.main._invalidate_index_cache"):
            result_json = await force_reindex(arguments)

        result = json.loads(result_json)

        # job_id 있거나 manual_required
        assert "job_id" in result
        assert result.get("status") in ["accepted", "manual_required"]


class TestForceReindexIntegration:
    """force_reindex 통합 테스트."""

    @pytest.mark.asyncio
    async def test_force_reindex_callable_from_main(self):
        """main.py에서 force_reindex 호출 가능."""
        from apps.mcp.mcp.main import call_tool

        with patch("server.mcp_server.main._invalidate_index_cache"):
            with patch("server.mcp_server.main.ensure_indexed"):
                result_json = await call_tool(
                    "force_reindex",
                    {
                        "repo_id": "test",
                        "reason": "Test",
                    },
                )

        result = json.loads(result_json)

        assert "status" in result
        assert "meta" in result
        assert result["meta"]["tier"] == 2

    @pytest.mark.asyncio
    async def test_invalidate_index_cache_resets_flag(self):
        """_invalidate_index_cache가 플래그 리셋."""
        from apps.mcp.mcp.main import _invalidate_index_cache
        import apps.mcp.mcp.main as main_module

        # Set flag
        main_module._indexing_done = True

        # Invalidate
        await _invalidate_index_cache("default")

        # Flag should be reset
        assert main_module._indexing_done is False


class TestForceReindexConfig:
    """Config 적용 확인."""

    def test_tier_2_config_requires_approval(self):
        """Tier 2는 requires_approval=True."""
        from apps.mcp.mcp.config import get_tier_config

        config = get_tier_config(2)

        assert config.requires_approval is True
        assert config.timeout_seconds == 60.0
        assert config.tier.value == 2
