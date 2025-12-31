"""
RFC-034 Phase 5: Generic Class Resolution Tests

Tests for:
1. Generic class constructor resolution
2. __init__ method finding
3. Argument-to-TypeVar matching
4. Integration with VariableTypeEnricher
"""

import pytest

from codegraph_engine.code_foundation.infrastructure.ir.models import (
    Edge,
    EdgeKind,
    IRDocument,
    Node,
    NodeKind,
    Span,
)
from codegraph_engine.code_foundation.infrastructure.type_inference.generic_class_resolver import (
    GenericClassResolver,
)
from codegraph_engine.code_foundation.infrastructure.type_inference.variable_type_enricher import (
    VariableTypeEnricher,
)


# ============================================================
# BASE CASES: Generic Class Resolution
# ============================================================


class TestGenericClassResolution:
    """Test GenericClassResolver basic functionality."""

    def test_box_with_int(self):
        """Base: Box<T>(value: T) with Box(42)"""
        # Create Box class
        box_class = Node(
            id="class::Box",
            kind=NodeKind.CLASS,
            name="Box",
            fqn="Box",
            span=Span(start_line=1, start_col=0, end_line=5, end_col=0),
            file_path="test.py",
            language="python",
            attrs={"type_parameters": [{"name": "T"}]},
        )

        # Create __init__ method
        init_method = Node(
            id="method::Box.__init__",
            kind=NodeKind.METHOD,
            name="__init__",
            fqn="Box.__init__",
            span=Span(start_line=2, start_col=4, end_line=3, end_col=0),
            file_path="test.py",
            language="python",
            attrs={
                "parameters": [
                    {"name": "self", "type": None},
                    {"name": "value", "type": "T"},
                ]
            },
        )

        # Create DEFINES edge
        defines_edge = Edge(
            id="edge::defines::Box::__init__",
            source_id="class::Box",
            target_id="method::Box.__init__",
            kind=EdgeKind.DEFINES,
        )

        # Create IR document
        ir_doc = IRDocument(
            repo_id="test",
            snapshot_id="test",
            nodes=[box_class, init_method],
            edges=[defines_edge],
        )

        # Resolve
        resolver = GenericClassResolver(ir_doc)
        result = resolver.resolve_constructor_call("Box", ["int"])

        assert result == "Box[int]"

    def test_pair_with_two_typevars(self):
        """Base: Pair<K, V>(key: K, val: V) with Pair("key", 42)"""
        pair_class = Node(
            id="class::Pair",
            kind=NodeKind.CLASS,
            name="Pair",
            fqn="Pair",
            span=Span(start_line=1, start_col=0, end_line=5, end_col=0),
            file_path="test.py",
            language="python",
            attrs={"type_parameters": [{"name": "K"}, {"name": "V"}]},
        )

        init_method = Node(
            id="method::Pair.__init__",
            kind=NodeKind.METHOD,
            name="__init__",
            fqn="Pair.__init__",
            span=Span(start_line=2, start_col=4, end_line=3, end_col=0),
            file_path="test.py",
            language="python",
            attrs={
                "parameters": [
                    {"name": "self", "type": None},
                    {"name": "key", "type": "K"},
                    {"name": "val", "type": "V"},
                ]
            },
        )

        defines_edge = Edge(
            id="edge::defines::Pair::__init__",
            source_id="class::Pair",
            target_id="method::Pair.__init__",
            kind=EdgeKind.DEFINES,
        )

        ir_doc = IRDocument(
            repo_id="test",
            snapshot_id="test",
            nodes=[pair_class, init_method],
            edges=[defines_edge],
        )

        resolver = GenericClassResolver(ir_doc)
        result = resolver.resolve_constructor_call("Pair", ["str", "int"])

        assert result == "Pair[str, int]"


# ============================================================
# EDGE CASES
# ============================================================


class TestGenericClassEdgeCases:
    """Test edge cases in generic class resolution."""

    def test_class_not_found(self):
        """Edge: Class not in IR"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="test", nodes=[], edges=[])

        resolver = GenericClassResolver(ir_doc)
        result = resolver.resolve_constructor_call("MissingClass", ["int"])

        assert result is None

    def test_non_generic_class(self):
        """Edge: Non-generic class"""
        regular_class = Node(
            id="class::Regular",
            kind=NodeKind.CLASS,
            name="Regular",
            fqn="Regular",
            span=Span(start_line=1, start_col=0, end_line=3, end_col=0),
            file_path="test.py",
            language="python",
            attrs={},  # No type_parameters
        )

        ir_doc = IRDocument(
            repo_id="test",
            snapshot_id="test",
            nodes=[regular_class],
            edges=[],
        )

        resolver = GenericClassResolver(ir_doc)
        result = resolver.resolve_constructor_call("Regular", ["int"])

        assert result is None  # Not generic

    def test_init_not_found(self):
        """Edge: __init__ method missing"""
        box_class = Node(
            id="class::Box",
            kind=NodeKind.CLASS,
            name="Box",
            fqn="Box",
            span=Span(start_line=1, start_col=0, end_line=3, end_col=0),
            file_path="test.py",
            language="python",
            attrs={"type_parameters": [{"name": "T"}]},
        )

        ir_doc = IRDocument(
            repo_id="test",
            snapshot_id="test",
            nodes=[box_class],
            edges=[],  # No DEFINES edge
        )

        resolver = GenericClassResolver(ir_doc)
        result = resolver.resolve_constructor_call("Box", ["int"])

        assert result is None

    def test_no_args_provided(self):
        """Edge: No arguments → cannot instantiate"""
        box_class = Node(
            id="class::Box",
            kind=NodeKind.CLASS,
            name="Box",
            fqn="Box",
            span=Span(start_line=1, start_col=0, end_line=3, end_col=0),
            file_path="test.py",
            language="python",
            attrs={"type_parameters": [{"name": "T"}]},
        )

        init_method = Node(
            id="method::Box.__init__",
            kind=NodeKind.METHOD,
            name="__init__",
            fqn="Box.__init__",
            span=Span(start_line=2, start_col=4, end_line=3, end_col=0),
            file_path="test.py",
            language="python",
            attrs={"parameters": [{"name": "self"}, {"name": "value", "type": "T"}]},
        )

        defines_edge = Edge(
            id="edge::defines::Box::__init__2",
            source_id="class::Box",
            target_id="method::Box.__init__",
            kind=EdgeKind.DEFINES,
        )

        ir_doc = IRDocument(
            repo_id="test",
            snapshot_id="test",
            nodes=[box_class, init_method],
            edges=[defines_edge],
        )

        resolver = GenericClassResolver(ir_doc)
        result = resolver.resolve_constructor_call("Box", [])  # No args

        # Should return class name with unresolved TypeVars
        assert result == "Box[T]"  # Uninstantiated


# ============================================================
# INTEGRATION: With VariableTypeEnricher
# ============================================================


class TestIntegrationWithVariableEnricher:
    """Test integration with VariableTypeEnricher."""

    def test_enrich_generic_class_variable(self):
        """Integration: Enrich variable from generic class constructor"""
        # Create Box class
        box_class = Node(
            id="class::Box",
            kind=NodeKind.CLASS,
            name="Box",
            fqn="Box",
            span=Span(start_line=1, start_col=0, end_line=5, end_col=0),
            file_path="test.py",
            language="python",
            attrs={"type_parameters": [{"name": "T"}]},
        )

        init_method = Node(
            id="method::Box.__init__",
            kind=NodeKind.METHOD,
            name="__init__",
            fqn="Box.__init__",
            span=Span(start_line=2, start_col=4, end_line=3, end_col=0),
            file_path="test.py",
            language="python",
            attrs={
                "parameters": [
                    {"name": "self", "type": None},
                    {"name": "value", "type": "T"},
                ]
            },
        )

        defines_edge = Edge(
            id="edge::defines::Box::__init__3",
            source_id="class::Box",
            target_id="method::Box.__init__",
            kind=EdgeKind.DEFINES,
        )

        # Create variable
        var_node = Node(
            id="var::box",
            kind=NodeKind.VARIABLE,
            name="box",
            fqn="box",
            span=Span(start_line=10, start_col=0, end_line=10, end_col=10),
            file_path="test.py",
            language="python",
            attrs={
                "assignment_type": "call",
                "call_target": "Box",
                "call_args": ["42"],
            },
        )

        # Create IR document
        ir_doc = IRDocument(
            repo_id="test",
            snapshot_id="test",
            nodes=[box_class, init_method, var_node],
            edges=[defines_edge],
        )

        # Enrich
        enricher = VariableTypeEnricher({}, ir_doc)
        success = enricher._enrich_variable(var_node)

        assert success
        assert var_node.attrs["inferred_type"] == "Box[int]"
        assert var_node.attrs["type_source"] == "call:generic:class"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
