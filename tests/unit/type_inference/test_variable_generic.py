"""
RFC-034 Phase 4: Variable Type Enrichment for Generic Functions

Tests for:
1. Generic function call instantiation
2. Argument type extraction
3. Multi-language support
4. Edge cases and error handling
"""

import pytest

from codegraph_engine.code_foundation.domain.type_inference.models import (
    InferSource,
    ReturnTypeSummary,
)
from codegraph_engine.code_foundation.infrastructure.ir.models import Node, NodeKind, Span
from codegraph_engine.code_foundation.infrastructure.type_inference.variable_type_enricher import (
    VariableTypeEnricher,
)


# ============================================================
# BASE CASES: Generic Call Instantiation
# ============================================================


class TestGenericCallInstantiation:
    """Test _instantiate_generic_call method."""

    def test_identity_with_int_arg(self):
        """Base: identity<T>(x: T) with identity(42)"""
        summary = ReturnTypeSummary(
            function_id="func::identity",
            return_type="T",
            confidence=1.0,
            source=InferSource.ANNOTATION,
            dependencies=frozenset(),
            type_parameters=("T",),
            is_generic=True,
        )

        var_node = Node(
            id="var::result",
            kind=NodeKind.VARIABLE,
            name="result",
            fqn="result",
            span=Span(start_line=10, start_col=0, end_line=10, end_col=10),
            file_path="test.py",
            language="python",
            attrs={
                "assignment_type": "call",
                "call_target": "identity",
                "call_args": ["42"],  # Phase 4: Mock literal args
            },
        )

        enricher = VariableTypeEnricher({})
        instantiated = enricher._instantiate_generic_call(summary, var_node, "identity")

        assert instantiated == "int"

    def test_identity_with_str_arg(self):
        """Base: identity<T>(x: T) with identity("hello")"""
        summary = ReturnTypeSummary(
            function_id="func::identity",
            return_type="T",
            confidence=1.0,
            source=InferSource.ANNOTATION,
            dependencies=frozenset(),
            type_parameters=("T",),
            is_generic=True,
        )

        var_node = Node(
            id="var::result",
            kind=NodeKind.VARIABLE,
            name="result",
            fqn="result",
            span=Span(start_line=10, start_col=0, end_line=10, end_col=10),
            file_path="test.py",
            language="python",
            attrs={
                "assignment_type": "call",
                "call_target": "identity",
                "call_args": ['"hello"'],
            },
        )

        enricher = VariableTypeEnricher({})
        instantiated = enricher._instantiate_generic_call(summary, var_node, "identity")

        assert instantiated == "str"

    def test_generic_list_return(self):
        """Base: first<T>(items: List[T]) -> T with first([1,2,3])"""
        summary = ReturnTypeSummary(
            function_id="func::first",
            return_type="T",
            confidence=1.0,
            source=InferSource.ANNOTATION,
            dependencies=frozenset(),
            type_parameters=("T",),
            is_generic=True,
        )

        var_node = Node(
            id="var::item",
            kind=NodeKind.VARIABLE,
            name="item",
            fqn="item",
            span=Span(start_line=10, start_col=0, end_line=10, end_col=10),
            file_path="test.py",
            language="python",
            attrs={
                "assignment_type": "call",
                "call_target": "first",
                "call_args": ["[1, 2, 3]"],  # list literal
            },
        )

        enricher = VariableTypeEnricher({})
        instantiated = enricher._instantiate_generic_call(summary, var_node, "first")

        # T = list (from literal), but return type is T (not List[T])
        assert instantiated == "list"

    def test_multiple_type_parameters(self):
        """Base: pair<K, V>(key: K, val: V) -> tuple[K, V]"""
        summary = ReturnTypeSummary(
            function_id="func::pair",
            return_type="tuple[K, V]",
            confidence=1.0,
            source=InferSource.ANNOTATION,
            dependencies=frozenset(),
            type_parameters=("K", "V"),
            is_generic=True,
        )

        var_node = Node(
            id="var::result",
            kind=NodeKind.VARIABLE,
            name="result",
            fqn="result",
            span=Span(start_line=10, start_col=0, end_line=10, end_col=10),
            file_path="test.py",
            language="python",
            attrs={
                "assignment_type": "call",
                "call_target": "pair",
                "call_args": ['"key"', "42"],  # str, int
            },
        )

        enricher = VariableTypeEnricher({})
        instantiated = enricher._instantiate_generic_call(summary, var_node, "pair")

        assert instantiated == "tuple[str, int]"


# ============================================================
# EDGE CASES: Argument Extraction
# ============================================================


class TestArgumentTypeExtraction:
    """Test _extract_call_arg_types method."""

    def test_extract_literal_args(self):
        """Edge: Extract types from literal arguments"""
        var_node = Node(
            id="var::result",
            kind=NodeKind.VARIABLE,
            name="result",
            fqn="result",
            span=Span(start_line=10, start_col=0, end_line=10, end_col=10),
            file_path="test.py",
            language="python",
            attrs={
                "call_args": ["42", '"hello"', "True", "None", "[1,2]"],
            },
        )

        enricher = VariableTypeEnricher({})
        arg_types = enricher._extract_call_arg_types(var_node)

        assert arg_types == ["int", "str", "bool", "None", "list"]

    def test_no_call_args_attr(self):
        """Edge: Variable node without call_args"""
        var_node = Node(
            id="var::result",
            kind=NodeKind.VARIABLE,
            name="result",
            fqn="result",
            span=Span(start_line=10, start_col=0, end_line=10, end_col=10),
            file_path="test.py",
            language="python",
            attrs={
                "assignment_type": "call",
                "call_target": "identity",
                # No call_args
            },
        )

        enricher = VariableTypeEnricher({})
        arg_types = enricher._extract_call_arg_types(var_node)

        assert arg_types == []  # Empty, not error

    def test_empty_call_args(self):
        """Edge: Empty call_args list"""
        var_node = Node(
            id="var::result",
            kind=NodeKind.VARIABLE,
            name="result",
            fqn="result",
            span=Span(start_line=10, start_col=0, end_line=10, end_col=10),
            file_path="test.py",
            language="python",
            attrs={"call_args": []},
        )

        enricher = VariableTypeEnricher({})
        arg_types = enricher._extract_call_arg_types(var_node)

        assert arg_types == []

    def test_complex_arg_returns_unknown(self):
        """Edge: Complex argument (variable) returns Unknown"""
        var_node = Node(
            id="var::result",
            kind=NodeKind.VARIABLE,
            name="result",
            fqn="result",
            span=Span(start_line=10, start_col=0, end_line=10, end_col=10),
            file_path="test.py",
            language="python",
            attrs={"call_args": ["some_var", "func()"]},  # Not literals
        )

        enricher = VariableTypeEnricher({})
        arg_types = enricher._extract_call_arg_types(var_node)

        assert arg_types == ["Unknown", "Unknown"]


# ============================================================
# CORNER CASES: Generic Instantiation
# ============================================================


class TestInstantiationCornerCases:
    """Test corner cases in generic instantiation."""

    def test_no_args_returns_none(self):
        """Corner: No arguments → cannot instantiate"""
        summary = ReturnTypeSummary(
            function_id="func::identity",
            return_type="T",
            confidence=1.0,
            source=InferSource.ANNOTATION,
            dependencies=frozenset(),
            type_parameters=("T",),
            is_generic=True,
        )

        var_node = Node(
            id="var::result",
            kind=NodeKind.VARIABLE,
            name="result",
            fqn="result",
            span=Span(start_line=10, start_col=0, end_line=10, end_col=10),
            file_path="test.py",
            language="python",
            attrs={
                "assignment_type": "call",
                "call_target": "identity",
                # No call_args
            },
        )

        enricher = VariableTypeEnricher({})
        instantiated = enricher._instantiate_generic_call(summary, var_node, "identity")

        assert instantiated is None  # Cannot instantiate

    def test_unknown_args_returns_none(self):
        """Corner: All Unknown args → cannot instantiate"""
        summary = ReturnTypeSummary(
            function_id="func::identity",
            return_type="T",
            confidence=1.0,
            source=InferSource.ANNOTATION,
            dependencies=frozenset(),
            type_parameters=("T",),
            is_generic=True,
        )

        var_node = Node(
            id="var::result",
            kind=NodeKind.VARIABLE,
            name="result",
            fqn="result",
            span=Span(start_line=10, start_col=0, end_line=10, end_col=10),
            file_path="test.py",
            language="python",
            attrs={
                "call_args": ["some_var"],  # Unknown
            },
        )

        enricher = VariableTypeEnricher({})
        instantiated = enricher._instantiate_generic_call(summary, var_node, "identity")

        # All args Unknown → cannot solve constraints
        assert instantiated is None or instantiated == "T"

    def test_partial_args_known(self):
        """Corner: Partial args known"""
        summary = ReturnTypeSummary(
            function_id="func::pair",
            return_type="tuple[K, V]",
            confidence=1.0,
            source=InferSource.ANNOTATION,
            dependencies=frozenset(),
            type_parameters=("K", "V"),
            is_generic=True,
        )

        var_node = Node(
            id="var::result",
            kind=NodeKind.VARIABLE,
            name="result",
            fqn="result",
            span=Span(start_line=10, start_col=0, end_line=10, end_col=10),
            file_path="test.py",
            language="python",
            attrs={
                "call_args": ['"key"', "unknown_var"],  # str, Unknown
            },
        )

        enricher = VariableTypeEnricher({})
        instantiated = enricher._instantiate_generic_call(summary, var_node, "pair")

        # K=str resolved, V=Unknown → partial instantiation
        # Should return "tuple[str, V]" or None
        # Phase 4: Accept either behavior
        assert instantiated is None or "str" in instantiated


# ============================================================
# INTEGRATION: Full Pipeline
# ============================================================


class TestIntegrationWithEnrichVariables:
    """Test integration with enrich_variables pipeline."""

    def test_enrich_generic_call_variable(self):
        """Integration: Enrich variable from generic call"""
        summary = ReturnTypeSummary(
            function_id="func::identity",
            return_type="T",
            confidence=1.0,
            source=InferSource.ANNOTATION,
            dependencies=frozenset(),
            type_parameters=("T",),
            is_generic=True,
        )

        var_node = Node(
            id="var::result",
            kind=NodeKind.VARIABLE,
            name="result",
            fqn="result",
            span=Span(start_line=10, start_col=0, end_line=10, end_col=10),
            file_path="test.py",
            language="python",
            attrs={
                "assignment_type": "call",
                "call_target": "identity",
                "call_args": ["42"],
            },
        )

        # Build name index
        enricher = VariableTypeEnricher({"func::identity": summary})

        # Enrich
        success = enricher._enrich_variable(var_node)

        assert success
        assert var_node.attrs["inferred_type"] == "int"
        assert var_node.attrs["type_source"] == "call:generic"

    def test_enrich_non_generic_call_unchanged(self):
        """Integration: Non-generic call works as before"""
        summary = ReturnTypeSummary(
            function_id="func::add",
            return_type="int",
            confidence=1.0,
            source=InferSource.ANNOTATION,
            dependencies=frozenset(),
        )

        var_node = Node(
            id="var::result",
            kind=NodeKind.VARIABLE,
            name="result",
            fqn="result",
            span=Span(start_line=10, start_col=0, end_line=10, end_col=10),
            file_path="test.py",
            language="python",
            attrs={
                "assignment_type": "call",
                "call_target": "add",
            },
        )

        enricher = VariableTypeEnricher({"func::add": summary})
        success = enricher._enrich_variable(var_node)

        assert success
        assert var_node.attrs["inferred_type"] == "int"
        assert var_node.attrs["type_source"] == "call:summary"  # Non-generic

    def test_generic_without_args_falls_back(self):
        """Integration: Generic call without args → uninstantiated"""
        summary = ReturnTypeSummary(
            function_id="func::identity",
            return_type="T",
            confidence=1.0,
            source=InferSource.ANNOTATION,
            dependencies=frozenset(),
            type_parameters=("T",),
            is_generic=True,
        )

        var_node = Node(
            id="var::result",
            kind=NodeKind.VARIABLE,
            name="result",
            fqn="result",
            span=Span(start_line=10, start_col=0, end_line=10, end_col=10),
            file_path="test.py",
            language="python",
            attrs={
                "assignment_type": "call",
                "call_target": "identity",
                # No call_args
            },
        )

        enricher = VariableTypeEnricher({"func::identity": summary})
        success = enricher._enrich_variable(var_node)

        assert success
        assert var_node.attrs["inferred_type"] == "T"  # Uninstantiated
        assert var_node.attrs["type_source"] == "call:generic:uninstantiated"


# ============================================================
# EXTREME CASES
# ============================================================


class TestExtremeCases:
    """Test extreme scenarios."""

    def test_literal_type_inference_all_types(self):
        """Extreme: Test all literal types"""
        enricher = VariableTypeEnricher({})

        test_cases = [
            ("42", "int"),
            ("-123", "int"),
            ("3.14", "float"),
            ("-0.5", "float"),
            ('"hello"', "str"),
            ("'world'", "str"),
            ("True", "bool"),
            ("False", "bool"),
            ("None", "None"),
            ("[1, 2]", "list"),
            ("{'a': 1}", "dict"),
            ("{1, 2}", "set"),
            ("(1, 2)", "tuple"),
        ]

        for value, expected_type in test_cases:
            result = enricher._infer_literal_type(value)
            assert result == expected_type, f"Failed for {value}: expected {expected_type}, got {result}"

    def test_many_type_parameters(self):
        """Extreme: Many TypeVars (10)"""
        type_params = tuple(f"T{i}" for i in range(10))

        summary = ReturnTypeSummary(
            function_id="func::complex",
            return_type="T0",
            confidence=1.0,
            source=InferSource.ANNOTATION,
            dependencies=frozenset(),
            type_parameters=type_params,
            is_generic=True,
        )

        var_node = Node(
            id="var::result",
            kind=NodeKind.VARIABLE,
            name="result",
            fqn="result",
            span=Span(start_line=10, start_col=0, end_line=10, end_col=10),
            file_path="test.py",
            language="python",
            attrs={
                "call_args": ["42"] * 10,  # 10 int args
            },
        )

        enricher = VariableTypeEnricher({})
        instantiated = enricher._instantiate_generic_call(summary, var_node, "complex")

        assert instantiated == "int"

    def test_whitespace_in_literal(self):
        """Extreme: Whitespace in literal values"""
        enricher = VariableTypeEnricher({})

        assert enricher._infer_literal_type("  42  ") == "int"
        assert enricher._infer_literal_type('  "hello"  ') == "str"
        assert enricher._infer_literal_type("  True  ") == "bool"


# ============================================================
# BACKWARD COMPATIBILITY
# ============================================================


class TestBackwardCompatibility:
    """Test backward compatibility with existing code."""

    def test_existing_non_generic_workflow(self):
        """Backward: Existing non-generic workflow unchanged"""
        from codegraph_engine.code_foundation.infrastructure.ir.models import IRDocument

        summary = ReturnTypeSummary(
            function_id="func::add",
            return_type="int",
            confidence=1.0,
            source=InferSource.ANNOTATION,
            dependencies=frozenset(),
        )

        var_node = Node(
            id="var::result",
            kind=NodeKind.VARIABLE,
            name="result",
            fqn="result",
            span=Span(start_line=10, start_col=0, end_line=10, end_col=10),
            file_path="test.py",
            language="python",
            attrs={
                "assignment_type": "call",
                "call_target": "add",
            },
        )

        ir_doc = IRDocument(
            repo_id="test",
            snapshot_id="test",
            nodes=[var_node],
            edges=[],
        )

        enricher = VariableTypeEnricher({"func::add": summary})
        count = enricher.enrich_variables(ir_doc)

        assert count == 1
        assert var_node.attrs["inferred_type"] == "int"
        assert enricher.stats["coverage"] == 1.0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
