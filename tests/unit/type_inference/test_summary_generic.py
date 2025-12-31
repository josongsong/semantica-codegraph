"""
RFC-034 Phase 3: ReturnTypeSummary Generic Support Tests

Tests for:
1. Domain model validation (ReturnTypeSummary)
2. Generic type parameter extraction (multi-language)
3. Summary building with generic info
4. Backward compatibility
"""

import pytest

from codegraph_engine.code_foundation.domain.type_inference.models import (
    InferSource,
    ReturnTypeSummary,
)
from codegraph_engine.code_foundation.infrastructure.ir.models import Node, NodeKind, Span
from codegraph_engine.code_foundation.infrastructure.type_inference.summary_builder import (
    ReturnTypeSummaryBuilder,
    SummaryBuilderConfig,
)


# ============================================================
# BASE CASES: Domain Model
# ============================================================


class TestReturnTypeSummaryDomain:
    """Test ReturnTypeSummary domain model."""

    def test_non_generic_function(self):
        """Base: Non-generic function summary"""
        summary = ReturnTypeSummary(
            function_id="add",
            return_type="int",
            confidence=1.0,
            source=InferSource.ANNOTATION,
            dependencies=frozenset(),
        )

        assert summary.function_id == "add"
        assert summary.return_type == "int"
        assert not summary.is_generic
        assert len(summary.type_parameters) == 0
        assert summary.is_resolved()

    def test_generic_function_single_typevar(self):
        """Base: Generic function with single TypeVar"""
        summary = ReturnTypeSummary(
            function_id="identity",
            return_type="T",
            confidence=1.0,
            source=InferSource.ANNOTATION,
            dependencies=frozenset(),
            type_parameters=("T",),
            is_generic=True,
        )

        assert summary.is_generic
        assert summary.type_parameters == ("T",)
        assert len(summary.type_constraints) == 0

    def test_generic_function_with_constraints(self):
        """Base: Generic with constraints (T extends Number)"""
        summary = ReturnTypeSummary(
            function_id="add_generic",
            return_type="T",
            confidence=1.0,
            source=InferSource.ANNOTATION,
            dependencies=frozenset(),
            type_parameters=("T",),
            is_generic=True,
            type_constraints=frozenset([("T", "Number")]),
        )

        assert summary.is_generic
        assert summary.type_parameters == ("T",)
        assert ("T", "Number") in summary.type_constraints

    def test_multiple_type_parameters(self):
        """Base: Multiple TypeVars (Dict[K, V])"""
        summary = ReturnTypeSummary(
            function_id="create_dict",
            return_type="Dict[K, V]",
            confidence=1.0,
            source=InferSource.ANNOTATION,
            dependencies=frozenset(),
            type_parameters=("K", "V"),
            is_generic=True,
        )

        assert summary.is_generic
        assert len(summary.type_parameters) == 2
        assert "K" in summary.type_parameters
        assert "V" in summary.type_parameters


# ============================================================
# EDGE CASES: Validation
# ============================================================


class TestSummaryValidation:
    """Test ReturnTypeSummary validation."""

    def test_is_generic_without_type_params_fails(self):
        """Edge: is_generic=True but no type_parameters"""
        with pytest.raises(ValueError, match="is_generic=True but type_parameters empty"):
            ReturnTypeSummary(
                function_id="invalid",
                return_type="T",
                confidence=1.0,
                source=InferSource.ANNOTATION,
                dependencies=frozenset(),
                is_generic=True,  # ❌ True
                type_parameters=(),  # ❌ Empty
            )

    def test_type_params_without_is_generic_fails(self):
        """Edge: type_parameters provided but is_generic=False"""
        with pytest.raises(ValueError, match="is_generic=False but type_parameters non-empty"):
            ReturnTypeSummary(
                function_id="invalid",
                return_type="int",
                confidence=1.0,
                source=InferSource.ANNOTATION,
                dependencies=frozenset(),
                is_generic=False,  # ❌ False
                type_parameters=("T",),  # ❌ Non-empty
            )

    def test_empty_type_parameter_fails(self):
        """Edge: Empty string in type_parameters"""
        with pytest.raises(ValueError, match="Empty type parameter"):
            ReturnTypeSummary(
                function_id="invalid",
                return_type="T",
                confidence=1.0,
                source=InferSource.ANNOTATION,
                dependencies=frozenset(),
                is_generic=True,
                type_parameters=("",),  # ❌ Empty string
            )

    def test_invalid_type_parameter_format_fails(self):
        """Edge: Invalid TypeVar format"""
        with pytest.raises(ValueError, match="Invalid type parameter"):
            ReturnTypeSummary(
                function_id="invalid",
                return_type="ABC",
                confidence=1.0,
                source=InferSource.ANNOTATION,
                dependencies=frozenset(),
                is_generic=True,
                type_parameters=("ABC",),  # ❌ Too long
            )

    def test_valid_type_parameter_formats(self):
        """Edge: Valid TypeVar formats"""
        # Single uppercase letter
        for name in ["T", "K", "V", "R"]:
            summary = ReturnTypeSummary(
                function_id=f"func_{name}",
                return_type=name,
                confidence=1.0,
                source=InferSource.ANNOTATION,
                dependencies=frozenset(),
                is_generic=True,
                type_parameters=(name,),
            )
            assert summary.is_generic

        # T with digit
        for name in ["T1", "T2"]:
            summary = ReturnTypeSummary(
                function_id=f"func_{name}",
                return_type=name,
                confidence=1.0,
                source=InferSource.ANNOTATION,
                dependencies=frozenset(),
                is_generic=True,
                type_parameters=(name,),
            )
            assert summary.is_generic


# ============================================================
# CORNER CASES: Type Parameter Extraction
# ============================================================


class TestTypeParameterExtraction:
    """Test _extract_type_params for different languages."""

    def test_python_explicit_type_parameters(self):
        """Corner: Python with explicit type_parameters attr"""
        node = Node(
            id="func::identity",
            kind=NodeKind.FUNCTION,
            name="identity",
            fqn="identity",
            span=Span(start_line=1, start_col=0, end_line=3, end_col=0),
            file_path="test.py",
            language="python",
            attrs={
                "type_parameters": [{"name": "T"}],
                "type_info": {"return_type": "T"},
            },
        )

        builder = ReturnTypeSummaryBuilder()
        type_params, constraints = builder._extract_type_params(node)

        assert type_params == ["T"]
        assert constraints == {}

    def test_python_inferred_from_hints(self):
        """Corner: Python TypeVar inferred from type hints"""
        node = Node(
            id="func::identity",
            kind=NodeKind.FUNCTION,
            name="identity",
            fqn="identity",
            span=Span(start_line=1, start_col=0, end_line=3, end_col=0),
            file_path="test.py",
            language="python",
            attrs={
                "parameters": [{"name": "x", "type": "T"}],
                "type_info": {"return_type": "T"},
            },
        )

        builder = ReturnTypeSummaryBuilder()
        type_params, constraints = builder._extract_type_params(node)

        assert "T" in type_params
        assert constraints == {}

    def test_typescript_generic_params(self):
        """Corner: TypeScript generic_params attr"""
        node = Node(
            id="func::identity",
            kind=NodeKind.FUNCTION,
            name="identity",
            fqn="identity",
            span=Span(start_line=1, start_col=0, end_line=3, end_col=0),
            file_path="test.ts",
            language="typescript",
            attrs={
                "generic_params": [{"name": "T", "constraint": "number"}],
                "type_info": {"return_type": "T"},
            },
        )

        builder = ReturnTypeSummaryBuilder()
        type_params, constraints = builder._extract_type_params(node)

        assert type_params == ["T"]
        assert constraints == {"T": "number"}

    def test_java_type_parameters_with_extends(self):
        """Corner: Java type_parameters with extends"""
        node = Node(
            id="func::identity",
            kind=NodeKind.FUNCTION,
            name="identity",
            fqn="identity",
            span=Span(start_line=1, start_col=0, end_line=3, end_col=0),
            file_path="Test.java",
            language="java",
            attrs={
                "type_parameters": ["T extends Number"],
                "type_info": {"return_type": "T"},
            },
        )

        builder = ReturnTypeSummaryBuilder()
        type_params, constraints = builder._extract_type_params(node)

        assert type_params == ["T"]
        assert constraints == {"T": "Number"}

    def test_kotlin_type_parameters_with_colon(self):
        """Corner: Kotlin type_parameters with colon"""
        node = Node(
            id="func::identity",
            kind=NodeKind.FUNCTION,
            name="identity",
            fqn="identity",
            span=Span(start_line=1, start_col=0, end_line=3, end_col=0),
            file_path="Test.kt",
            language="kotlin",
            attrs={
                "type_parameters": ["T : Any"],
                "type_info": {"return_type": "T"},
            },
        )

        builder = ReturnTypeSummaryBuilder()
        type_params, constraints = builder._extract_type_params(node)

        assert type_params == ["T"]
        assert constraints == {"T": "Any"}

    def test_unsupported_language_returns_empty(self):
        """Corner: Unsupported language returns empty"""
        node = Node(
            id="func::test",
            kind=NodeKind.FUNCTION,
            name="test",
            fqn="test",
            span=Span(start_line=1, start_col=0, end_line=3, end_col=0),
            file_path="test.rb",
            language="ruby",  # Unsupported
            attrs={},
        )

        builder = ReturnTypeSummaryBuilder()
        type_params, constraints = builder._extract_type_params(node)

        assert type_params == []
        assert constraints == {}


# ============================================================
# EXTREME CASES
# ============================================================


class TestExtremeCases:
    """Test extreme scenarios."""

    def test_looks_like_typevar_helper(self):
        """Extreme: _looks_like_typevar edge cases"""
        builder = ReturnTypeSummaryBuilder()

        # Valid TypeVars
        assert builder._looks_like_typevar("T")
        assert builder._looks_like_typevar("K")
        assert builder._looks_like_typevar("V")
        assert builder._looks_like_typevar("T1")
        assert builder._looks_like_typevar("T2")

        # Not TypeVars
        assert not builder._looks_like_typevar("int")
        assert not builder._looks_like_typevar("str")
        assert not builder._looks_like_typevar("List")
        assert not builder._looks_like_typevar("List[T]")  # Generic instantiation
        assert not builder._looks_like_typevar("Dict[K, V]")
        assert not builder._looks_like_typevar("")
        assert not builder._looks_like_typevar("  ")

    def test_many_type_parameters(self):
        """Extreme: Many type parameters"""
        type_params = tuple(f"T{i}" for i in range(10))

        summary = ReturnTypeSummary(
            function_id="complex",
            return_type="T0",
            confidence=1.0,
            source=InferSource.ANNOTATION,
            dependencies=frozenset(),
            is_generic=True,
            type_parameters=type_params,
        )

        assert summary.is_generic
        assert len(summary.type_parameters) == 10

    def test_many_constraints(self):
        """Extreme: Many type constraints"""
        constraints = frozenset((f"T{i}", f"Bound{i}") for i in range(10))

        summary = ReturnTypeSummary(
            function_id="complex",
            return_type="T0",
            confidence=1.0,
            source=InferSource.ANNOTATION,
            dependencies=frozenset(),
            is_generic=True,
            type_parameters=tuple(f"T{i}" for i in range(10)),
            type_constraints=constraints,
        )

        assert len(summary.type_constraints) == 10


# ============================================================
# INTEGRATION: Full Pipeline
# ============================================================


class TestSummaryBuilderIntegration:
    """Test full summary building pipeline with generic support."""

    def test_build_generic_function_summary(self):
        """Integration: Build summary for generic function"""
        node = Node(
            id="func::identity",
            kind=NodeKind.FUNCTION,
            name="identity",
            fqn="identity",
            span=Span(start_line=1, start_col=0, end_line=3, end_col=0),
            file_path="test.py",
            language="python",
            attrs={
                "type_parameters": [{"name": "T"}],
                "type_info": {"return_type": "T"},
            },
        )

        builder = ReturnTypeSummaryBuilder()
        summaries = builder.build([node], {})

        assert "func::identity" in summaries
        summary = summaries["func::identity"]

        assert summary.is_generic
        assert summary.type_parameters == ("T",)
        assert summary.return_type == "T"
        assert summary.source == InferSource.ANNOTATION

    def test_build_non_generic_function_summary(self):
        """Integration: Build summary for non-generic function"""
        node = Node(
            id="func::add",
            kind=NodeKind.FUNCTION,
            name="add",
            fqn="add",
            span=Span(start_line=1, start_col=0, end_line=3, end_col=0),
            file_path="test.py",
            language="python",
            attrs={
                "type_info": {"return_type": "int"},
            },
        )

        builder = ReturnTypeSummaryBuilder()
        summaries = builder.build([node], {})

        assert "func::add" in summaries
        summary = summaries["func::add"]

        assert not summary.is_generic
        assert len(summary.type_parameters) == 0
        assert summary.return_type == "int"

    def test_backward_compatibility_without_generic_info(self):
        """Integration: Backward compatibility - old code without generic info"""
        # Simulate old code that doesn't provide generic info
        node = Node(
            id="func::old_func",
            kind=NodeKind.FUNCTION,
            name="old_func",
            fqn="old_func",
            span=Span(start_line=1, start_col=0, end_line=3, end_col=0),
            file_path="test.py",
            language="python",
            attrs={
                "type_info": {"return_type": "str"},
            },
        )

        builder = ReturnTypeSummaryBuilder()
        summaries = builder.build([node], {})

        summary = summaries["func::old_func"]

        # Should work with defaults
        assert not summary.is_generic
        assert len(summary.type_parameters) == 0
        assert summary.return_type == "str"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
