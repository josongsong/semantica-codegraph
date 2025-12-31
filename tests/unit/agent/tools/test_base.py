"""
Agent Tools Base Tests

Test Coverage:
- Enums: ToolCategory
- Models: ToolMetadata, ToolResult
- Format conversion: OpenAI, Anthropic
"""

import pytest

from apps.orchestrator.orchestrator.tools.code_foundation.base import (
    ToolCategory,
    ToolMetadata,
    ToolResult,
)


class TestToolCategory:
    """ToolCategory enum tests"""

    def test_all_categories_defined(self):
        """All tool categories exist"""
        assert ToolCategory.CODE_UNDERSTANDING.value == "code_understanding"
        assert ToolCategory.IMPACT_ANALYSIS.value == "impact_analysis"
        assert ToolCategory.BUG_DETECTION.value == "bug_detection"
        assert ToolCategory.SECURITY_ANALYSIS.value == "security_analysis"

    def test_additional_categories(self):
        """Additional categories exist"""
        assert ToolCategory.REFACTORING.value == "refactoring"
        assert ToolCategory.PERFORMANCE.value == "performance"
        assert ToolCategory.DEPENDENCY_ANALYSIS.value == "dependency_analysis"
        assert ToolCategory.TYPE_ANALYSIS.value == "type_analysis"


class TestToolMetadata:
    """ToolMetadata model tests"""

    def test_create_metadata(self):
        """Create tool metadata"""
        metadata = ToolMetadata(
            name="find_references",
            description="Find all references to a symbol",
            category=ToolCategory.CODE_UNDERSTANDING,
            input_schema={"type": "object", "properties": {"symbol": {"type": "string"}}},
            output_schema={"type": "array"},
        )
        assert metadata.name == "find_references"
        assert metadata.category == ToolCategory.CODE_UNDERSTANDING
        assert metadata.complexity == 1  # default
        assert metadata.stability == "stable"  # default

    def test_metadata_with_options(self):
        """Metadata with optional fields"""
        metadata = ToolMetadata(
            name="impact_analysis",
            description="Analyze code impact",
            category=ToolCategory.IMPACT_ANALYSIS,
            input_schema={},
            output_schema={},
            complexity=4,
            dependencies=["find_references", "call_graph"],
            tags=["expensive", "deep"],
            version="2.0.0",
            stability="beta",
        )
        assert metadata.complexity == 4
        assert len(metadata.dependencies) == 2
        assert metadata.stability == "beta"

    def test_to_openai_function(self):
        """Convert to OpenAI function format"""
        metadata = ToolMetadata(
            name="get_definition",
            description="Get symbol definition",
            category=ToolCategory.CODE_UNDERSTANDING,
            input_schema={
                "type": "object",
                "properties": {"symbol_name": {"type": "string"}},
                "required": ["symbol_name"],
            },
            output_schema={},
        )
        openai_func = metadata.to_openai_function()

        assert openai_func["type"] == "function"
        assert openai_func["function"]["name"] == "get_definition"
        assert "parameters" in openai_func["function"]

    def test_to_anthropic_tool(self):
        """Convert to Anthropic tool format"""
        metadata = ToolMetadata(
            name="vulnerability_scan",
            description="Scan for vulnerabilities",
            category=ToolCategory.SECURITY_ANALYSIS,
            input_schema={"type": "object"},
            output_schema={},
        )
        anthropic_tool = metadata.to_anthropic_tool()

        assert anthropic_tool["name"] == "vulnerability_scan"
        assert "description" in anthropic_tool
        assert "input_schema" in anthropic_tool


class TestToolResult:
    """ToolResult model tests"""

    def test_create_success_result(self):
        """Create successful result"""
        result = ToolResult(
            success=True,
            data={"references": ["file1.py:10", "file2.py:20"]},
        )
        assert result.success is True
        assert len(result.data["references"]) == 2

    def test_create_failure_result(self):
        """Create failure result"""
        result = ToolResult(
            success=False,
            data={},
            error="Symbol not found",
        )
        assert result.success is False
        assert result.error == "Symbol not found"

    def test_result_with_metadata(self):
        """Result with execution metadata"""
        result = ToolResult(
            success=True,
            data={"count": 5},
            metadata={"execution_time_ms": 150, "cache_hit": True},
        )
        assert result.metadata["execution_time_ms"] == 150


class TestEdgeCases:
    """Edge case tests"""

    def test_empty_input_schema(self):
        """Empty input schema"""
        metadata = ToolMetadata(
            name="simple_tool",
            description="No inputs",
            category=ToolCategory.DOCUMENTATION,
            input_schema={},
            output_schema={},
        )
        openai_func = metadata.to_openai_function()
        assert openai_func["function"]["parameters"] == {}

    def test_complex_input_schema(self):
        """Complex input schema"""
        metadata = ToolMetadata(
            name="complex_tool",
            description="Complex inputs",
            category=ToolCategory.REFACTORING,
            input_schema={
                "type": "object",
                "properties": {
                    "files": {"type": "array", "items": {"type": "string"}},
                    "options": {
                        "type": "object",
                        "properties": {"recursive": {"type": "boolean"}},
                    },
                },
            },
            output_schema={},
        )
        assert "properties" in metadata.input_schema

    def test_all_stability_levels(self):
        """All stability levels"""
        for stability in ["stable", "beta", "experimental"]:
            metadata = ToolMetadata(
                name=f"tool_{stability}",
                description="Test",
                category=ToolCategory.CODE_UNDERSTANDING,
                input_schema={},
                output_schema={},
                stability=stability,
            )
            assert metadata.stability == stability

    def test_high_complexity_tool(self):
        """High complexity tool"""
        metadata = ToolMetadata(
            name="deep_analysis",
            description="Deep code analysis",
            category=ToolCategory.IMPACT_ANALYSIS,
            input_schema={},
            output_schema={},
            complexity=5,
        )
        assert metadata.complexity == 5
