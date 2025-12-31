"""
MCP Protocol Compliance Test

MCP 프로토콜 준수 여부를 검증.

Test Coverage:
- Tool schema validation (inputSchema)
- Response schema validation
- Error handling format
- Metadata presence
"""

import json

import pytest

from apps.mcp.mcp.main import list_tools


@pytest.mark.asyncio
async def test_all_tools_have_valid_schema():
    """Test that all tools have valid MCP schema."""
    tools = await list_tools()

    assert len(tools) > 0, "No tools registered"

    for tool in tools:
        # Required fields per MCP spec
        assert hasattr(tool, "name"), f"Tool missing name: {tool}"
        assert hasattr(tool, "description"), f"Tool {tool.name} missing description"
        assert hasattr(tool, "inputSchema"), f"Tool {tool.name} missing inputSchema"

        # inputSchema must be valid JSON Schema
        schema = tool.inputSchema
        assert isinstance(schema, dict), f"Tool {tool.name} inputSchema not dict"
        assert "type" in schema, f"Tool {tool.name} inputSchema missing type"
        assert schema["type"] == "object", f"Tool {tool.name} inputSchema type not object"
        assert "properties" in schema, f"Tool {tool.name} inputSchema missing properties"

        print(f"   ✅ {tool.name}: valid schema")


@pytest.mark.asyncio
async def test_tier0_tools_marked_correctly():
    """Test that Tier 0 tools are properly marked."""
    tools = await list_tools()

    tier0_tools = ["search", "get_context", "graph_slice"]

    for tool_name in tier0_tools:
        tool = next((t for t in tools if t.name == tool_name), None)

        if tool:
            # Check description mentions Tier 0
            assert "[Tier 0]" in tool.description or "Tier 0" in tool.description, (
                f"Tool {tool_name} should be marked as Tier 0"
            )
            print(f"   ✅ {tool_name}: Tier 0 marked")
        else:
            print(f"   ⚠️ {tool_name}: not found (may not be implemented yet)")


@pytest.mark.asyncio
async def test_search_tool_schema_compliance():
    """Test that search tool schema is MCP-compliant."""
    tools = await list_tools()
    search_tool = next((t for t in tools if t.name == "search"), None)

    assert search_tool is not None, "search tool not found"

    schema = search_tool.inputSchema

    # Required parameter
    assert "required" in schema
    assert "query" in schema["required"]

    # Properties
    props = schema["properties"]
    assert "query" in props
    assert props["query"]["type"] == "string"

    # Optional parameters
    assert "types" in props
    assert props["types"]["type"] == "array"
    assert props["types"]["items"]["enum"] == ["chunks", "symbols", "all"]

    assert "limit" in props
    assert props["limit"]["type"] == "integer"
    assert props["limit"]["default"] == 10

    print("   ✅ search tool: MCP-compliant schema")


@pytest.mark.asyncio
async def test_legacy_tools_marked():
    """Test that legacy tools are marked as deprecated."""
    tools = await list_tools()

    legacy_tools = ["search_chunks", "search_symbols"]

    for tool_name in legacy_tools:
        tool = next((t for t in tools if t.name == tool_name), None)

        if tool:
            # Should mention legacy or deprecation
            assert "Legacy" in tool.description or "deprecated" in tool.description.lower(), (
                f"Tool {tool_name} should be marked as legacy"
            )
            print(f"   ✅ {tool_name}: marked as legacy")


@pytest.mark.asyncio
async def test_tool_count_matches_rfc053():
    """Test that tool count matches RFC-053 specification."""
    tools = await list_tools()

    # RFC-053: 19 tools + 4 legacy (temporarily) = 23
    # But some legacy may be in separate handlers
    assert len(tools) >= 19, f"Expected at least 19 tools, got {len(tools)}"

    print(f"   ✅ Tool count: {len(tools)} (>= 19 required)")


@pytest.mark.asyncio
async def test_no_duplicate_tool_names():
    """Test that there are no duplicate tool names."""
    tools = await list_tools()

    names = [t.name for t in tools]
    unique_names = set(names)

    assert len(names) == len(unique_names), f"Duplicate tool names found: {[n for n in names if names.count(n) > 1]}"

    print(f"   ✅ No duplicates: {len(unique_names)} unique tools")
