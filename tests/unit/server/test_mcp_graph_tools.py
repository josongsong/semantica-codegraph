"""
MCP Graph Semantics Tools 테스트 (RFC-SEM-022)

Test Coverage:
- Base Case: 기본 동작
- Edge Case: 방향별 동작, 파라미터 조합
- Corner Case: 빈 값, 누락 값
- Extreme Case: 긴 심볼명, 깊은 탐색
"""

import json

import pytest


class TestGraphSliceTool:
    """graph_slice MCP 도구 테스트."""

    @pytest.mark.asyncio
    async def test_base_case_backward(self):
        """Base Case: backward slice."""
        from apps.mcp.mcp.handlers import graph_slice

        result = await graph_slice({"anchor": "MyClass.method"})
        data = json.loads(result)

        assert "anchor" in data
        assert data["anchor"] == "MyClass.method"
        assert "fragments" in data
        assert "total_lines" in data
        assert "total_nodes" in data

    @pytest.mark.asyncio
    async def test_base_case_forward(self):
        """Base Case: forward slice."""
        from apps.mcp.mcp.handlers import graph_slice

        result = await graph_slice({"anchor": "func", "direction": "forward"})
        data = json.loads(result)

        assert data.get("direction") == "forward" or "direction" not in data

    @pytest.mark.asyncio
    async def test_direction_both(self):
        """Edge Case: both direction."""
        from apps.mcp.mcp.handlers import graph_slice

        result = await graph_slice({"anchor": "func", "direction": "both"})
        data = json.loads(result)

        assert "error" not in data or data.get("fallback")

    @pytest.mark.asyncio
    async def test_empty_anchor(self):
        """Corner Case: 빈 anchor."""
        from apps.mcp.mcp.handlers import graph_slice

        result = await graph_slice({"anchor": ""})
        data = json.loads(result)

        assert "error" in data
        assert "anchor" in data["error"].lower()

    @pytest.mark.asyncio
    async def test_missing_anchor(self):
        """Corner Case: anchor 누락."""
        from apps.mcp.mcp.handlers import graph_slice

        result = await graph_slice({})
        data = json.loads(result)

        assert "error" in data

    @pytest.mark.asyncio
    async def test_custom_depth(self):
        """Edge Case: 커스텀 depth."""
        from apps.mcp.mcp.handlers import graph_slice

        result = await graph_slice({"anchor": "func", "max_depth": 10})
        data = json.loads(result)

        assert "error" not in data or data.get("fallback")

    @pytest.mark.asyncio
    async def test_custom_max_lines(self):
        """Edge Case: 커스텀 max_lines."""
        from apps.mcp.mcp.handlers import graph_slice

        result = await graph_slice({"anchor": "func", "max_lines": 200})
        data = json.loads(result)

        assert "error" not in data or data.get("fallback")

    @pytest.mark.asyncio
    async def test_long_symbol_name(self):
        """Extreme Case: 긴 심볼명."""
        from apps.mcp.mcp.handlers import graph_slice

        long_name = "Module.SubModule.Class.InnerClass." + "method" * 100
        result = await graph_slice({"anchor": long_name})
        data = json.loads(result)

        assert data["anchor"] == long_name

    @pytest.mark.asyncio
    async def test_unicode_symbol(self):
        """Edge Case: 유니코드 심볼."""
        from apps.mcp.mcp.handlers import graph_slice

        result = await graph_slice({"anchor": "클래스.메서드"})
        data = json.loads(result)

        assert data["anchor"] == "클래스.메서드"

    @pytest.mark.asyncio
    async def test_special_characters(self):
        """Edge Case: 특수문자."""
        from apps.mcp.mcp.handlers import graph_slice

        result = await graph_slice({"anchor": "__init__"})
        data = json.loads(result)

        assert "__init__" in data["anchor"]


class TestGraphDataflowTool:
    """graph_dataflow MCP 도구 테스트."""

    @pytest.mark.asyncio
    async def test_base_case(self):
        """Base Case: 기본 dataflow."""
        from apps.mcp.mcp.handlers import graph_dataflow

        result = await graph_dataflow({"source": "user_input", "sink": "db_query"})
        data = json.loads(result)

        assert data["source"] == "user_input"
        assert data["sink"] == "db_query"
        assert "reachable" in data
        assert "paths" in data

    @pytest.mark.asyncio
    async def test_with_policy(self):
        """Edge Case: policy 포함."""
        from apps.mcp.mcp.handlers import graph_dataflow

        result = await graph_dataflow(
            {
                "source": "input",
                "sink": "output",
                "policy": "sql_injection",
            }
        )
        data = json.loads(result)

        assert "policy" in data or data.get("fallback")

    @pytest.mark.asyncio
    async def test_missing_source(self):
        """Corner Case: source 누락."""
        from apps.mcp.mcp.handlers import graph_dataflow

        result = await graph_dataflow({"sink": "output"})
        data = json.loads(result)

        assert "error" in data

    @pytest.mark.asyncio
    async def test_missing_sink(self):
        """Corner Case: sink 누락."""
        from apps.mcp.mcp.handlers import graph_dataflow

        result = await graph_dataflow({"source": "input"})
        data = json.loads(result)

        assert "error" in data

    @pytest.mark.asyncio
    async def test_empty_source(self):
        """Corner Case: 빈 source."""
        from apps.mcp.mcp.handlers import graph_dataflow

        result = await graph_dataflow({"source": "", "sink": "output"})
        data = json.loads(result)

        assert "error" in data

    @pytest.mark.asyncio
    async def test_same_source_sink(self):
        """Edge Case: source == sink."""
        from apps.mcp.mcp.handlers import graph_dataflow

        result = await graph_dataflow({"source": "same", "sink": "same"})
        data = json.loads(result)

        # Should work, trivially reachable
        assert data["source"] == "same"
        assert data["sink"] == "same"


class TestVerifyNoNewFindingsTool:
    """verify_no_new_findings_introduced MCP 도구 테스트."""

    @pytest.mark.asyncio
    async def test_missing_baseline(self):
        """Corner Case: baseline 누락."""
        from apps.mcp.mcp.handlers import verify_no_new_findings_introduced

        result = await verify_no_new_findings_introduced({})
        data = json.loads(result)

        assert data["verdict"] == "unknown"
        assert "error" in data

    @pytest.mark.asyncio
    async def test_with_baseline_mock_mode(self):
        """Edge Case: Mock 모드."""
        import os

        from apps.mcp.mcp.handlers import verify_no_new_findings_introduced

        os.environ["SEMANTICA_ALLOW_MOCK_DATA"] = "true"
        try:
            result = await verify_no_new_findings_introduced(
                {
                    "baseline_execution_id": "exec_base",
                }
            )
            data = json.loads(result)

            # Should return some verdict
            assert "verdict" in data
        finally:
            del os.environ["SEMANTICA_ALLOW_MOCK_DATA"]

    @pytest.mark.asyncio
    async def test_with_current_execution(self):
        """Edge Case: current_execution_id 제공."""
        import os

        from apps.mcp.mcp.handlers import verify_no_new_findings_introduced

        os.environ["SEMANTICA_ALLOW_MOCK_DATA"] = "true"
        try:
            result = await verify_no_new_findings_introduced(
                {
                    "baseline_execution_id": "exec_base",
                    "current_execution_id": "exec_current",
                }
            )
            data = json.loads(result)

            assert "verdict" in data
        finally:
            del os.environ["SEMANTICA_ALLOW_MOCK_DATA"]

    @pytest.mark.asyncio
    async def test_with_ruleset_subset(self):
        """Edge Case: ruleset_subset 제공."""
        import os

        from apps.mcp.mcp.handlers import verify_no_new_findings_introduced

        os.environ["SEMANTICA_ALLOW_MOCK_DATA"] = "true"
        try:
            result = await verify_no_new_findings_introduced(
                {
                    "baseline_execution_id": "exec_base",
                    "ruleset_subset": ["sql_injection", "xss"],
                }
            )
            data = json.loads(result)

            assert "verdict" in data
        finally:
            del os.environ["SEMANTICA_ALLOW_MOCK_DATA"]
