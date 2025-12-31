"""
Property-Based Tests: Kotlin LSP Adapter

Uses Hypothesis for edge case discovery and invariant testing.

Tests:
- Line number conversion (1-indexed ↔ 0-indexed)
- URI parsing and conversion
- Type detection (nullable, generic, union)
- Error handling invariants
"""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest
from hypothesis import given
from hypothesis import strategies as st

from codegraph_engine.code_foundation.infrastructure.ir.lsp.adapter import Location, TypeInfo
from codegraph_engine.code_foundation.infrastructure.ir.lsp.kotlin import KotlinAdapter

# ============================================================
# Strategies (Input Generation)
# ============================================================


@st.composite
def line_numbers(draw):
    """Generate valid line numbers (1-indexed, positive)"""
    return draw(st.integers(min_value=1, max_value=100000))


@st.composite
def column_numbers(draw):
    """Generate valid column numbers (0-indexed, non-negative)"""
    return draw(st.integers(min_value=0, max_value=1000))


@st.composite
def file_paths(draw):
    """Generate valid file paths"""
    # Simple paths without special characters
    parts = draw(
        st.lists(
            st.text(alphabet=st.characters(min_codepoint=97, max_codepoint=122), min_size=1, max_size=10),
            min_size=1,
            max_size=5,
        )
    )
    return Path("/".join(parts) + ".kt")


@st.composite
def uri_strings(draw):
    """Generate file:// URIs"""
    path = draw(file_paths())
    return f"file://{path}"


@st.composite
def kotlin_types(draw):
    """Generate Kotlin type strings"""
    base_types = ["String", "Int", "Boolean", "Long", "Double", "Float", "Char", "Byte"]
    base = draw(st.sampled_from(base_types))

    # Optionally make nullable
    if draw(st.booleans()):
        base += "?"

    # Optionally make generic
    if draw(st.booleans()):
        inner = draw(st.sampled_from(base_types))
        base = f"List<{inner}>"

    return base


# ============================================================
# Property Tests: Line Number Conversion
# ============================================================


class TestLineNumberConversion:
    """Property tests for line number conversion"""

    @given(line=line_numbers())
    @pytest.mark.asyncio
    async def test_line_number_roundtrip(self, line):
        """
        Property: Converting 1-indexed → 0-indexed → 1-indexed should be identity

        For any valid line number L (1-indexed):
        - LSP receives L-1 (0-indexed)
        - When returned, we add 1 to get back L
        """
        # Setup async mock
        mock_client = Mock()
        mock_client.hover = AsyncMock(
            return_value={
                "contents": {"value": "```kotlin\nval x: Int\n```"},
                "range": {
                    "start": {"line": line - 1, "character": 0},  # LSP returns 0-indexed
                },
            }
        )

        # No isinstance check needed (duck typing)
        adapter = KotlinAdapter(mock_client)
        result = await adapter.hover(Path("/test.kt"), line=line, col=0)

        # Verify: Client was called with 0-indexed
        mock_client.hover.assert_called_once()
        call_args = mock_client.hover.call_args
        assert call_args[0][1] == line - 1  # Second arg should be line - 1

        # Verify: Result has correct line (1-indexed)
        if result and result.definition_location:
            assert result.definition_location.line == line

    @given(line=line_numbers(), col=column_numbers())
    @pytest.mark.asyncio
    async def test_definition_line_conversion(self, line, col):
        """
        Property: Definition line numbers should be converted correctly
        """
        mock_client = Mock()
        mock_client.definition = AsyncMock(
            return_value=[
                {
                    "uri": "file:///test.kt",
                    "range": {
                        "start": {"line": line - 1, "character": col},  # LSP 0-indexed
                    },
                }
            ]
        )

        adapter = KotlinAdapter(mock_client)
        result = await adapter.definition(Path("/test.kt"), line=line, col=col)

        # Verify: Client called with 0-indexed
        assert mock_client.definition.call_args[0][1] == line - 1

        # Verify: Result has 1-indexed line
        assert result is not None
        assert result.line == line


# ============================================================
# Property Tests: URI Parsing
# ============================================================


class TestURIParsing:
    """Property tests for URI parsing"""

    @given(uri=uri_strings())
    @pytest.mark.asyncio
    async def test_uri_strip_prefix(self, uri):
        """
        Property: All file:// URIs should have prefix stripped

        For any URI starting with file://:
        - Resulting path should not contain file://
        - Should be a valid path
        """
        mock_client = Mock()
        mock_client.definition = AsyncMock(
            return_value=[
                {
                    "uri": uri,
                    "range": {"start": {"line": 0, "character": 0}},
                }
            ]
        )

        adapter = KotlinAdapter(mock_client)
        result = await adapter.definition(Path("/test.kt"), line=1, col=0)

        # Verify: file:// prefix removed
        assert result is not None
        assert not result.file_path.startswith("file://")

        # Verify: Path is what we expect
        expected_path = uri[7:]  # Remove "file://"
        assert result.file_path == expected_path


# ============================================================
# Property Tests: Type Detection
# ============================================================


class TestTypeDetection:
    """Property tests for type detection (nullable, generic, union)"""

    @given(type_str=kotlin_types())
    @pytest.mark.asyncio
    async def test_nullable_detection(self, type_str):
        """
        Property: Types ending with ? should be detected as nullable
        """
        mock_client = Mock()
        mock_client.hover = AsyncMock(
            return_value={
                "contents": {"value": f"```kotlin\nval x: {type_str}\n```"},
            }
        )

        adapter = KotlinAdapter(mock_client)
        result = await adapter.hover(Path("/test.kt"), line=1, col=0)

        # Verify: Nullable detection
        assert result is not None
        expected_nullable = "?" in type_str
        assert result.is_nullable == expected_nullable

    @given(type_str=kotlin_types())
    @pytest.mark.asyncio
    async def test_generic_detection(self, type_str):
        """
        Property: Types with <...> should be detected as generic
        """
        mock_client = Mock()
        mock_client.hover = AsyncMock(
            return_value={
                "contents": {"value": f"```kotlin\nval x: {type_str}\n```"},
            }
        )

        adapter = KotlinAdapter(mock_client)
        result = await adapter.hover(Path("/test.kt"), line=1, col=0)

        # Verify: Generic detection
        assert result is not None
        expected_generic = "<" in type_str and ">" in type_str
        assert result.is_generic == expected_generic


# ============================================================
# Property Tests: Error Handling Invariants
# ============================================================


class TestErrorHandlingInvariants:
    """Property tests for error handling invariants"""

    @given(line=line_numbers(), col=column_numbers())
    @pytest.mark.asyncio
    async def test_hover_never_raises(self, line, col):
        """
        Property: hover() should never raise exceptions (returns None on error)
        """
        mock_client = Mock()
        mock_client.hover = AsyncMock(side_effect=RuntimeError("Server crashed"))

        adapter = KotlinAdapter(mock_client)

        # Should not raise
        result = await adapter.hover(Path("/test.kt"), line=line, col=col)

        # Should return None
        assert result is None

    @given(line=line_numbers(), col=column_numbers())
    @pytest.mark.asyncio
    async def test_definition_never_raises(self, line, col):
        """
        Property: definition() should never raise exceptions
        """
        mock_client = Mock()
        mock_client.definition = AsyncMock(side_effect=Exception("Connection lost"))

        adapter = KotlinAdapter(mock_client)
        result = await adapter.definition(Path("/test.kt"), line=line, col=col)

        assert result is None

    @given(line=line_numbers(), col=column_numbers())
    @pytest.mark.asyncio
    async def test_references_never_raises(self, line, col):
        """
        Property: references() should never raise exceptions
        """
        mock_client = Mock()
        mock_client.references = AsyncMock(side_effect=TimeoutError("Timeout"))

        adapter = KotlinAdapter(mock_client)
        result = await adapter.references(Path("/test.kt"), line=line, col=col)

        assert result == []


# ============================================================
# Property Tests: Boundary Conditions
# ============================================================


class TestBoundaryConditions:
    """Property tests for boundary conditions"""

    @pytest.mark.asyncio
    async def test_line_1_converts_to_0(self):
        """
        Property: Line 1 (minimum valid) should convert to 0 (LSP minimum)
        """
        mock_client = Mock()
        mock_client.hover = AsyncMock(return_value=None)

        adapter = KotlinAdapter(mock_client)
        await adapter.hover(Path("/test.kt"), line=1, col=0)

        # Verify: Line 1 → 0
        assert mock_client.hover.call_args[0][1] == 0

    @pytest.mark.asyncio
    async def test_column_0_stays_0(self):
        """
        Property: Column 0 (minimum valid) should stay 0 (LSP minimum)
        """
        mock_client = Mock()
        mock_client.hover = AsyncMock(return_value=None)

        adapter = KotlinAdapter(mock_client)
        await adapter.hover(Path("/test.kt"), line=1, col=0)

        # Verify: Column unchanged
        assert mock_client.hover.call_args[0][2] == 0

    @given(line=st.integers(min_value=1, max_value=1000000))
    @pytest.mark.asyncio
    async def test_large_line_numbers(self, line):
        """
        Property: Large line numbers should be handled correctly
        """
        mock_client = Mock()
        mock_client.hover = AsyncMock(return_value=None)

        adapter = KotlinAdapter(mock_client)
        await adapter.hover(Path("/test.kt"), line=line, col=0)

        # Verify: Conversion correct even for large numbers
        assert mock_client.hover.call_args[0][1] == line - 1
