"""
Agent Tools Base Tests

Test Coverage:
- Enums: ToolCategory
- Models: ToolMetadata
- Edge cases: OpenAI/Anthropic compatibility
"""

import pytest

from apps.orchestrator.orchestrator.tools.code_foundation.base import (
    ToolCategory,
    ToolMetadata,
)


class TestToolCategory:
    """ToolCategory enum tests"""

    def test_all_categories(self):
        """All tool categories exist"""
        assert ToolCategory.CODE_UNDERSTANDING.value == "code_understanding"
        assert ToolCategory.IMPACT_ANALYSIS.value == "impact_analysis"
        assert ToolCategory.BUG_DETECTION.value == "bug_detection"
        assert ToolCategory.SECURITY_ANALYSIS.value == "security_analysis"

    def test_enum_count(self):
        """Expected number of categories"""
        assert len(ToolCategory) >= 10


class TestToolMetadata:
    """ToolMetadata model tests"""

    def test_create_basic_metadata(self):
        """Create basic tool metadata"""
        metadata = ToolMetadata(
            name="find_references",
            description="Find references to a symbol",
            category=ToolCategory.CODE_UNDERSTANDING,
            input_schema={"type": "object", "properties": {"symbol": {"type": "string"}}},
            output_schema={"type": "object", "properties": {"references": {"type": "array"}}},
        )
        assert metadata.name == "find_references"
        assert metadata.category == ToolCategory.CODE_UNDERSTANDING
        assert metadata.complexity == 1  # default

    def test_metadata_with_complexity(self):
        """Metadata with complexity"""
        metadata = ToolMetadata(
            name="impact_analysis",
            description="Analyze change impact",
            category=ToolCategory.IMPACT_ANALYSIS,
            input_schema={},
            output_schema={},
            complexity=4,
        )
        assert metadata.complexity == 4

    def test_metadata_with_dependencies(self):
        """Metadata with dependencies"""
        metadata = ToolMetadata(
            name="security_scan",
            description="Security scan",
            category=ToolCategory.SECURITY_ANALYSIS,
            input_schema={},
            output_schema={},
            dependencies=["find_references", "call_graph"],
        )
        assert len(metadata.dependencies) == 2

    def test_to_openai_function(self):
        """Convert to OpenAI function format"""
        metadata = ToolMetadata(
            name="test_tool",
            description="Test tool",
            category=ToolCategory.CODE_UNDERSTANDING,
            input_schema={"type": "object"},
            output_schema={"type": "object"},
        )
        openai_func = metadata.to_openai_function()
        # OpenAI format: {"type": "function", "function": {...}}
        assert "type" in openai_func
        assert openai_func["type"] == "function"
        assert "function" in openai_func
        assert "name" in openai_func["function"]
        assert "description" in openai_func["function"]


class TestEdgeCases:
    """Edge cases"""

    def test_empty_dependencies(self):
        """Empty dependencies list"""
        metadata = ToolMetadata(
            name="tool",
            description="desc",
            category=ToolCategory.CODE_UNDERSTANDING,
            input_schema={},
            output_schema={},
        )
        assert metadata.dependencies == []

    def test_stability_levels(self):
        """Different stability levels"""
        stable = ToolMetadata(
            name="tool1",
            description="desc",
            category=ToolCategory.CODE_UNDERSTANDING,
            input_schema={},
            output_schema={},
            stability="stable",
        )
        beta = ToolMetadata(
            name="tool2",
            description="desc",
            category=ToolCategory.CODE_UNDERSTANDING,
            input_schema={},
            output_schema={},
            stability="beta",
        )
        assert stable.stability == "stable"
        assert beta.stability == "beta"

    def test_version_string(self):
        """Version string format"""
        metadata = ToolMetadata(
            name="tool",
            description="desc",
            category=ToolCategory.CODE_UNDERSTANDING,
            input_schema={},
            output_schema={},
            version="2.1.0",
        )
        assert metadata.version == "2.1.0"

    def test_tags_list(self):
        """Tags list"""
        metadata = ToolMetadata(
            name="tool",
            description="desc",
            category=ToolCategory.CODE_UNDERSTANDING,
            input_schema={},
            output_schema={},
            tags=["fast", "experimental", "python"],
        )
        assert len(metadata.tags) == 3
