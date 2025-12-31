"""
Unit Tests: Kotlin LSP Adapter (Async Version)

Tests KotlinAdapter with unified LSP models and async/await.
"""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest

from codegraph_engine.code_foundation.infrastructure.ir.lsp.adapter import (
    Diagnostic,
    Location,
    TypeInfo,
)
from codegraph_engine.code_foundation.infrastructure.ir.lsp.kotlin import KotlinAdapter


class TestKotlinAdapterTypeChecking:
    """Test type checking and validation"""

    @pytest.mark.skip(reason="Duck typing used - no isinstance check")
    def test_invalid_client_type(self):
        """Test that adapter rejects non-KotlinLSPClient"""
        # NOTE: KotlinAdapter now uses duck typing for testability
        # It accepts any object with hover/definition/references/diagnostics methods
        pass

    def test_valid_client_type(self):
        """Test that adapter accepts mock client (duck typing)"""
        mock_client = Mock()

        # Duck typing: Any object is accepted
        adapter = KotlinAdapter(mock_client)
        assert adapter.client == mock_client


class TestKotlinAdapterHover:
    """Test hover functionality with unified TypeInfo model"""

    @pytest.mark.asyncio
    @patch("src.contexts.code_foundation.infrastructure.ir.external_analyzers.kotlin_lsp.KotlinLSPClient")
    async def test_hover_success(self, mock_client_class):
        """Test successful hover returns TypeInfo with correct fields"""
        # Setup
        mock_client = Mock()
        mock_client.hover = AsyncMock(
            return_value={
                "contents": {
                    "kind": "markdown",
                    "value": "```kotlin\nval userName: String\n```\n\nA user's name",
                },
                "range": {
                    "start": {"line": 10, "character": 4},
                    "end": {"line": 10, "character": 12},
                },
            }
        )
        mock_client_class.return_value = mock_client

        adapter = KotlinAdapter(mock_client)

        # Execute
        result = await adapter.hover(Path("/project/Main.kt"), line=11, col=4)

        # Verify
        assert result is not None
        assert isinstance(result, TypeInfo)

        # Check unified TypeInfo fields
        assert result.type_string == "String"
        assert result.documentation == "A user's name"
        assert result.signature is None
        assert result.is_nullable is False
        assert result.is_union is False
        assert result.is_generic is False

        # Check definition_location
        assert result.definition_location is not None
        assert isinstance(result.definition_location, Location)
        assert result.definition_location.file_path == "/project/Main.kt"
        assert result.definition_location.line == 11  # 10 (LSP 0-indexed) + 1
        assert result.definition_location.column == 4

        # Verify client called with 0-indexed line
        mock_client.hover.assert_called_once_with(
            "/project/Main.kt",
            10,  # line - 1 (convert to 0-indexed)
            4,
        )

    @pytest.mark.asyncio
    @patch("src.contexts.code_foundation.infrastructure.ir.external_analyzers.kotlin_lsp.KotlinLSPClient")
    async def test_hover_nullable_type(self, mock_client_class):
        """Test hover with nullable type detection"""
        mock_client = Mock()
        mock_client.hover = AsyncMock(
            return_value={
                "contents": {
                    "value": "```kotlin\nval name: String?\n```",
                },
            }
        )
        mock_client_class.return_value = mock_client

        adapter = KotlinAdapter(mock_client)
        result = await adapter.hover(Path("/project/Main.kt"), line=5, col=0)

        assert result is not None
        assert result.type_string == "String?"
        assert result.is_nullable is True  # Should detect '?'

    @pytest.mark.asyncio
    @patch("src.contexts.code_foundation.infrastructure.ir.external_analyzers.kotlin_lsp.KotlinLSPClient")
    async def test_hover_generic_type(self, mock_client_class):
        """Test hover with generic type detection"""
        mock_client = Mock()
        mock_client.hover = AsyncMock(
            return_value={
                "contents": {
                    "value": "```kotlin\nval items: List<String>\n```",
                },
            }
        )
        mock_client_class.return_value = mock_client

        adapter = KotlinAdapter(mock_client)
        result = await adapter.hover(Path("/project/Main.kt"), line=5, col=0)

        assert result is not None
        assert result.type_string == "List<String>"
        assert result.is_generic is True  # Should detect '<' and '>'

    @pytest.mark.asyncio
    @patch("src.contexts.code_foundation.infrastructure.ir.external_analyzers.kotlin_lsp.KotlinLSPClient")
    async def test_hover_no_result(self, mock_client_class):
        """Test hover when no result available"""
        mock_client = Mock()
        mock_client.hover = AsyncMock(return_value=None)
        mock_client_class.return_value = mock_client

        adapter = KotlinAdapter(mock_client)
        result = await adapter.hover(Path("/project/Main.kt"), line=5, col=0)

        assert result is None

    @pytest.mark.asyncio
    @patch("src.contexts.code_foundation.infrastructure.ir.external_analyzers.kotlin_lsp.KotlinLSPClient")
    async def test_hover_error_handling(self, mock_client_class):
        """Test hover error handling"""
        mock_client = Mock()
        mock_client.hover = AsyncMock(side_effect=Exception("Connection lost"))
        mock_client_class.return_value = mock_client

        adapter = KotlinAdapter(mock_client)
        result = await adapter.hover(Path("/project/Main.kt"), line=5, col=0)

        # Should return None on error, not raise exception
        assert result is None


class TestKotlinAdapterDefinition:
    """Test definition functionality with unified Location model"""

    @pytest.mark.asyncio
    @patch("src.contexts.code_foundation.infrastructure.ir.external_analyzers.kotlin_lsp.KotlinLSPClient")
    async def test_definition_success(self, mock_client_class):
        """Test successful definition returns Location with correct fields"""
        mock_client = Mock()
        mock_client.definition = AsyncMock(
            return_value=[
                {
                    "uri": "file:///project/src/Utils.kt",
                    "range": {
                        "start": {"line": 15, "character": 8},
                        "end": {"line": 15, "character": 20},
                    },
                }
            ]
        )
        mock_client_class.return_value = mock_client

        adapter = KotlinAdapter(mock_client)
        result = await adapter.definition(Path("/project/Main.kt"), line=20, col=10)

        # Verify
        assert result is not None
        assert isinstance(result, Location)

        # Check unified Location fields
        assert result.file_path == "/project/src/Utils.kt"
        assert result.line == 16  # 15 (LSP 0-indexed) + 1
        assert result.column == 8

        # Verify client called with 0-indexed line
        mock_client.definition.assert_called_once_with(
            "/project/Main.kt",
            19,  # line - 1
            10,
        )

    @pytest.mark.asyncio
    @patch("src.contexts.code_foundation.infrastructure.ir.external_analyzers.kotlin_lsp.KotlinLSPClient")
    async def test_definition_empty_result(self, mock_client_class):
        """Test definition when no result found"""
        mock_client = Mock()
        mock_client.definition = AsyncMock(return_value=[])
        mock_client_class.return_value = mock_client

        adapter = KotlinAdapter(mock_client)
        result = await adapter.definition(Path("/project/Main.kt"), line=5, col=0)

        assert result is None

    @pytest.mark.asyncio
    @patch("src.contexts.code_foundation.infrastructure.ir.external_analyzers.kotlin_lsp.KotlinLSPClient")
    async def test_definition_error_handling(self, mock_client_class):
        """Test definition error handling"""
        mock_client = Mock()
        mock_client.definition = AsyncMock(side_effect=RuntimeError("Server crashed"))
        mock_client_class.return_value = mock_client

        adapter = KotlinAdapter(mock_client)
        result = await adapter.definition(Path("/project/Main.kt"), line=5, col=0)

        assert result is None


class TestKotlinAdapterReferences:
    """Test references functionality"""

    @pytest.mark.asyncio
    @patch("src.contexts.code_foundation.infrastructure.ir.external_analyzers.kotlin_lsp.KotlinLSPClient")
    async def test_references_success(self, mock_client_class):
        """Test successful references returns list of Locations"""
        mock_client = Mock()
        mock_client.references = AsyncMock(
            return_value=[
                {
                    "uri": "file:///project/Main.kt",
                    "range": {"start": {"line": 10, "character": 5}},
                },
                {
                    "uri": "file:///project/Utils.kt",
                    "range": {"start": {"line": 20, "character": 8}},
                },
            ]
        )
        mock_client_class.return_value = mock_client

        adapter = KotlinAdapter(mock_client)
        results = await adapter.references(Path("/project/Defs.kt"), line=5, col=0, include_declaration=True)

        # Verify
        assert len(results) == 2
        assert all(isinstance(loc, Location) for loc in results)

        # Check first location
        assert results[0].file_path == "/project/Main.kt"
        assert results[0].line == 11  # 10 + 1
        assert results[0].column == 5

        # Check second location
        assert results[1].file_path == "/project/Utils.kt"
        assert results[1].line == 21  # 20 + 1
        assert results[1].column == 8

    @pytest.mark.asyncio
    @patch("src.contexts.code_foundation.infrastructure.ir.external_analyzers.kotlin_lsp.KotlinLSPClient")
    async def test_references_empty(self, mock_client_class):
        """Test references when no results found"""
        mock_client = Mock()
        mock_client.references = AsyncMock(return_value=[])
        mock_client_class.return_value = mock_client

        adapter = KotlinAdapter(mock_client)
        results = await adapter.references(Path("/project/Main.kt"), line=5, col=0)

        assert results == []


class TestKotlinAdapterDiagnostics:
    """Test diagnostics functionality with unified Diagnostic model"""

    @pytest.mark.asyncio
    @patch("src.contexts.code_foundation.infrastructure.ir.external_analyzers.kotlin_lsp.KotlinLSPClient")
    async def test_diagnostics_success(self, mock_client_class):
        """Test successful diagnostics returns list of Diagnostics"""
        mock_client = Mock()
        mock_client.diagnostics = AsyncMock(
            return_value=[
                {
                    "severity": 1,  # ERROR
                    "message": "Type mismatch",
                    "range": {
                        "start": {"line": 10, "character": 5},
                        "end": {"line": 10, "character": 15},
                    },
                    "code": "TYPE_MISMATCH",
                    "source": "kotlin",
                }
            ]
        )
        mock_client_class.return_value = mock_client

        adapter = KotlinAdapter(mock_client)
        results = await adapter.diagnostics(Path("/project/Main.kt"))

        # Verify
        assert len(results) == 1
        assert isinstance(results[0], Diagnostic)

        # Check unified Diagnostic fields
        diag = results[0]
        assert diag.severity == "error"
        assert diag.message == "Type mismatch"
        assert diag.file_path == "/project/Main.kt"
        assert diag.start_line == 11  # 10 + 1
        assert diag.start_col == 5
        assert diag.end_line == 11  # 10 + 1
        assert diag.end_col == 15
        assert diag.code == "TYPE_MISMATCH"
        assert diag.source == "kotlin"

    @pytest.mark.asyncio
    @patch("src.contexts.code_foundation.infrastructure.ir.external_analyzers.kotlin_lsp.KotlinLSPClient")
    async def test_diagnostics_severity_mapping(self, mock_client_class):
        """Test correct severity mapping from LSP codes"""
        mock_client = Mock()
        mock_client.diagnostics = AsyncMock(
            return_value=[
                {"severity": 1, "message": "Error", "range": {"start": {}, "end": {}}},
                {"severity": 2, "message": "Warning", "range": {"start": {}, "end": {}}},
                {"severity": 3, "message": "Info", "range": {"start": {}, "end": {}}},
                {"severity": 4, "message": "Hint", "range": {"start": {}, "end": {}}},
            ]
        )
        mock_client_class.return_value = mock_client

        adapter = KotlinAdapter(mock_client)
        results = await adapter.diagnostics(Path("/project/Main.kt"))

        assert len(results) == 4
        assert results[0].severity == "error"
        assert results[1].severity == "warning"
        assert results[2].severity == "information"
        assert results[3].severity == "hint"


class TestKotlinAdapterShutdown:
    """Test shutdown functionality"""

    @pytest.mark.asyncio
    @patch("src.contexts.code_foundation.infrastructure.ir.external_analyzers.kotlin_lsp.KotlinLSPClient")
    async def test_shutdown_success(self, mock_client_class):
        """Test successful shutdown"""
        mock_client = Mock()
        mock_client.stop = AsyncMock()
        mock_client_class.return_value = mock_client

        adapter = KotlinAdapter(mock_client)
        await adapter.shutdown()

        mock_client.stop.assert_called_once()

    @pytest.mark.asyncio
    @patch("src.contexts.code_foundation.infrastructure.ir.external_analyzers.kotlin_lsp.KotlinLSPClient")
    async def test_shutdown_error_handling(self, mock_client_class):
        """Test shutdown error handling"""
        mock_client = Mock()
        mock_client.stop = AsyncMock(side_effect=Exception("Already stopped"))
        mock_client_class.return_value = mock_client

        adapter = KotlinAdapter(mock_client)

        # Should not raise exception
        await adapter.shutdown()


class TestKotlinAdapterEdgeCases:
    """Test edge cases and boundary conditions"""

    @pytest.mark.asyncio
    @patch("src.contexts.code_foundation.infrastructure.ir.external_analyzers.kotlin_lsp.KotlinLSPClient")
    async def test_hover_empty_contents(self, mock_client_class):
        """Test hover with empty contents"""
        mock_client = Mock()
        mock_client.hover = AsyncMock(return_value={"contents": {}})
        mock_client_class.return_value = mock_client

        adapter = KotlinAdapter(mock_client)
        result = await adapter.hover(Path("/project/Main.kt"), line=5, col=0)

        # Should return None for empty contents
        assert result is None

    @pytest.mark.asyncio
    @patch("src.contexts.code_foundation.infrastructure.ir.external_analyzers.kotlin_lsp.KotlinLSPClient")
    async def test_hover_list_contents(self, mock_client_class):
        """Test hover with list-format contents"""
        mock_client = Mock()
        mock_client.hover = AsyncMock(return_value={"contents": ["```kotlin\nval x: Int\n```", "An integer"]})
        mock_client_class.return_value = mock_client

        adapter = KotlinAdapter(mock_client)
        result = await adapter.hover(Path("/project/Main.kt"), line=5, col=0)

        assert result is not None
        assert result.type_string == "Int"

    @pytest.mark.asyncio
    @patch("src.contexts.code_foundation.infrastructure.ir.external_analyzers.kotlin_lsp.KotlinLSPClient")
    async def test_path_conversion(self, mock_client_class):
        """Test Path to string conversion"""
        mock_client = Mock()
        mock_client.hover = AsyncMock(return_value=None)
        mock_client_class.return_value = mock_client

        adapter = KotlinAdapter(mock_client)

        # Should accept both string and Path
        await adapter.hover(Path("/project/Main.kt"), line=5, col=0)
        mock_client.hover.assert_called_with("/project/Main.kt", 4, 0)

    @pytest.mark.asyncio
    @patch("src.contexts.code_foundation.infrastructure.ir.external_analyzers.kotlin_lsp.KotlinLSPClient")
    async def test_line_number_conversion(self, mock_client_class):
        """Test 1-indexed to 0-indexed line number conversion"""
        mock_client = Mock()
        mock_client.hover = AsyncMock(return_value=None)
        mock_client_class.return_value = mock_client

        adapter = KotlinAdapter(mock_client)

        # Line 1 should become 0
        await adapter.hover(Path("/project/Main.kt"), line=1, col=0)
        mock_client.hover.assert_called_with("/project/Main.kt", 0, 0)

        # Line 100 should become 99
        await adapter.hover(Path("/project/Main.kt"), line=100, col=5)
        mock_client.hover.assert_called_with("/project/Main.kt", 99, 5)
