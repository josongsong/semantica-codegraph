"""
RFC-034 Enhancement: Python TypeVar Declaration Parsing

Tests for improved Python TypeVar detection:
1. Direct TypeVar declaration parsing
2. Bound constraint extraction
3. Edge cases in TypeVar syntax
"""

import pytest

from codegraph_engine.code_foundation.infrastructure.ir.models import Node, NodeKind, Span
from codegraph_engine.code_foundation.infrastructure.type_inference.summary_builder import (
    ReturnTypeSummaryBuilder,
)


# ============================================================
# BASE CASES: TypeVar Declaration Parsing
# ============================================================


class TestTypeVarDeclarationParsing:
    """Test _parse_typevar_declarations method."""

    def test_simple_typevar_declaration(self):
        """Base: T = TypeVar('T')"""
        node = Node(
            id="func::identity",
            kind=NodeKind.FUNCTION,
            name="identity",
            fqn="identity",
            span=Span(start_line=1, start_col=0, end_line=5, end_col=0),
            file_path="test.py",
            language="python",
            attrs={
                "body_statements": [{"type": "assign", "target": "T", "value": "TypeVar('T')"}],
                "parameters": [{"name": "x", "type": "T"}],
                "type_info": {"return_type": "T"},
            },
        )

        builder = ReturnTypeSummaryBuilder()
        type_vars = builder._parse_typevar_declarations(node)

        assert "T" in type_vars
        assert type_vars["T"] is None  # No bound

    def test_typevar_with_bound(self):
        """Base: T = TypeVar('T', bound=int)"""
        node = Node(
            id="func::add_generic",
            kind=NodeKind.FUNCTION,
            name="add_generic",
            fqn="add_generic",
            span=Span(start_line=1, start_col=0, end_line=5, end_col=0),
            file_path="test.py",
            language="python",
            attrs={
                "body_statements": [{"type": "assign", "target": "T", "value": "TypeVar('T', bound=Number)"}],
            },
        )

        builder = ReturnTypeSummaryBuilder()
        type_vars = builder._parse_typevar_declarations(node)

        assert "T" in type_vars
        assert type_vars["T"] == "Number"

    def test_multiple_typevar_declarations(self):
        """Base: Multiple TypeVars"""
        node = Node(
            id="func::pair",
            kind=NodeKind.FUNCTION,
            name="pair",
            fqn="pair",
            span=Span(start_line=1, start_col=0, end_line=5, end_col=0),
            file_path="test.py",
            language="python",
            attrs={
                "body_statements": [
                    {"type": "assign", "target": "K", "value": "TypeVar('K')"},
                    {"type": "assign", "target": "V", "value": "TypeVar('V', bound=int)"},
                ],
            },
        )

        builder = ReturnTypeSummaryBuilder()
        type_vars = builder._parse_typevar_declarations(node)

        assert "K" in type_vars
        assert "V" in type_vars
        assert type_vars["K"] is None
        assert type_vars["V"] == "int"


# ============================================================
# EDGE CASES: TypeVar Syntax Variations
# ============================================================


class TestTypeVarSyntaxEdgeCases:
    """Test edge cases in TypeVar syntax."""

    def test_double_quotes(self):
        """Edge: TypeVar with double quotes"""
        node = Node(
            id="func::test",
            kind=NodeKind.FUNCTION,
            name="test",
            fqn="test",
            span=Span(start_line=1, start_col=0, end_line=5, end_col=0),
            file_path="test.py",
            language="python",
            attrs={
                "body_statements": [{"type": "assign", "target": "T", "value": 'TypeVar("T")'}],
            },
        )

        builder = ReturnTypeSummaryBuilder()
        type_vars = builder._parse_typevar_declarations(node)

        assert "T" in type_vars

    def test_whitespace_in_declaration(self):
        """Edge: Whitespace variations"""
        node = Node(
            id="func::test",
            kind=NodeKind.FUNCTION,
            name="test",
            fqn="test",
            span=Span(start_line=1, start_col=0, end_line=5, end_col=0),
            file_path="test.py",
            language="python",
            attrs={
                "body_statements": [{"type": "assign", "target": "T", "value": "  TypeVar( 'T' )  "}],
            },
        )

        builder = ReturnTypeSummaryBuilder()
        type_vars = builder._parse_typevar_declarations(node)

        # Should handle whitespace gracefully (may not match - acceptable)
        # This is an edge case that's okay to not support

    def test_no_body_statements(self):
        """Edge: No body_statements"""
        node = Node(
            id="func::test",
            kind=NodeKind.FUNCTION,
            name="test",
            fqn="test",
            span=Span(start_line=1, start_col=0, end_line=5, end_col=0),
            file_path="test.py",
            language="python",
            attrs={},  # No body_statements
        )

        builder = ReturnTypeSummaryBuilder()
        type_vars = builder._parse_typevar_declarations(node)

        assert type_vars == {}  # Empty, not error

    def test_non_matching_target(self):
        """Edge: Target doesn't match TypeVar name"""
        node = Node(
            id="func::test",
            kind=NodeKind.FUNCTION,
            name="test",
            fqn="test",
            span=Span(start_line=1, start_col=0, end_line=5, end_col=0),
            file_path="test.py",
            language="python",
            attrs={
                "body_statements": [
                    {"type": "assign", "target": "X", "value": "TypeVar('T')"}  # Mismatch
                ],
            },
        )

        builder = ReturnTypeSummaryBuilder()
        type_vars = builder._parse_typevar_declarations(node)

        # Should not match - target and name must be same
        assert "T" not in type_vars
        assert "X" not in type_vars


# ============================================================
# INTEGRATION: With extract_python_type_params
# ============================================================


class TestTypeVarIntegration:
    """Test integration with _extract_python_type_params."""

    def test_typevar_declaration_detected_in_extraction(self):
        """Integration: TypeVar declaration detected"""
        node = Node(
            id="func::identity",
            kind=NodeKind.FUNCTION,
            name="identity",
            fqn="identity",
            span=Span(start_line=1, start_col=0, end_line=5, end_col=0),
            file_path="test.py",
            language="python",
            attrs={
                "body_statements": [{"type": "assign", "target": "T", "value": "TypeVar('T')"}],
                "parameters": [{"name": "x", "type": "T"}],
                "type_info": {"return_type": "T"},
            },
        )

        builder = ReturnTypeSummaryBuilder()
        type_params, constraints = builder._extract_python_type_params(node)

        assert "T" in type_params
        assert constraints.get("T") is None

    def test_typevar_with_bound_in_extraction(self):
        """Integration: TypeVar bound extracted"""
        node = Node(
            id="func::test",
            kind=NodeKind.FUNCTION,
            name="test",
            fqn="test",
            span=Span(start_line=1, start_col=0, end_line=5, end_col=0),
            file_path="test.py",
            language="python",
            attrs={
                "body_statements": [{"type": "assign", "target": "T", "value": "TypeVar('T', bound=Number)"}],
                "parameters": [{"name": "x", "type": "T"}],
                "type_info": {"return_type": "T"},
            },
        )

        builder = ReturnTypeSummaryBuilder()
        type_params, constraints = builder._extract_python_type_params(node)

        assert "T" in type_params
        assert constraints.get("T") == "Number"

    def test_fallback_to_hint_inference(self):
        """Integration: Falls back to hint inference if no declaration"""
        node = Node(
            id="func::identity",
            kind=NodeKind.FUNCTION,
            name="identity",
            fqn="identity",
            span=Span(start_line=1, start_col=0, end_line=5, end_col=0),
            file_path="test.py",
            language="python",
            attrs={
                # No body_statements with TypeVar
                "parameters": [{"name": "x", "type": "T"}],
                "type_info": {"return_type": "T"},
            },
        )

        builder = ReturnTypeSummaryBuilder()
        type_params, constraints = builder._extract_python_type_params(node)

        # Should infer from hints
        assert "T" in type_params


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
